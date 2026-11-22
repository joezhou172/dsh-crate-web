import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_size_preview import ENV, artifact, fixture
from dsh_pack.errors import PackImportError
from dsh_pack.export import ExportOptions, export_profile
from dsh_pack.importer import ImportOptions
from dsh_pack.incremental import execute_incremental, merge_packs, plan_incremental, protected_import
from dsh_pack.pack import read
from dsh_pack.snapshot import Snapshot
from dsh_pack.user_cli import _invoke_core


class SnapshotStoragePreflightTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        profile = fixture(root)
        self.home = root / "target"
        self.pack = root / "storage.dshcrate"
        self.options = ImportOptions(target_profile_name="moved", current_environment=ENV)
        self.files = {}
        selections = []
        for kind in ("plugin-data", "plugin-config", "plugin-workflow"):
            path = f"storages/{kind}.json"
            content = ('{ "kind" : "' + kind + '", "label" : "测试" }\r\n').encode("utf-8")
            source = root / "home" / path
            source.parent.mkdir(exist_ok=True)
            source.write_bytes(content)
            self.files[path] = content
            selections.append({"path": path, "kind": kind, "owner": "fixture-plugin"})
        options = ExportOptions(environment=ENV, export_mode="freeze", data_selection=tuple(selections))
        with patch("dsh_pack.export._npm_pack", side_effect=artifact):
            export_profile(profile, self.pack, options=options)

    def test_storage_preflight_and_unsupported_modes(self):
        for policy in ("strict", "compatible"):
            with self.subTest(policy=policy):
                code, preview = _invoke_core(["inspect", str(self.pack), "--compatibility-policy", policy])
                self.assertEqual(code, 0, preview)
                self.assertTrue(preview["canContinue"])
        data = read(self.pack)
        merged, preview = merge_packs(data, data, 'add', storage_to_add=self.files)
        self.assertEqual(merged.user_data, self.files)
        self.assertTrue(all(row['action'] == 'add' for row in preview['storage']))
        merged, preview = merge_packs(data, data, 'update')
        self.assertTrue(all(row['action'] == 'keep' for row in preview['storage']))
        self.assertEqual(merged.user_data, self.files)
        code, rejected = _invoke_core(["import", str(self.pack), "--overwrite", "--confirm-overwrite",
                                       "--target-profile", "moved", "--dsh-home", str(self.home), "--plan-only"])
        self.assertNotEqual(code, 0)
        self.assertEqual(rejected["error"]["code"], "PORTABLE_DATA_OVERWRITE_FORBIDDEN")

    def test_incremental_mixed_storage_and_stale_plan(self):
        from dataclasses import replace
        profile = self.home / "profiles/moved"
        import shutil
        shutil.copytree(self.pack.parent / "home/profiles/sample", profile)
        stored, appeared, missing = (self.home / path for path in self.files)
        stored.parent.mkdir()
        stored.write_bytes(b'{"local":true}\r\n')
        options = replace(self.options, current_environment={"os": ENV["os"], "node": ENV["node"]})
        with tempfile.TemporaryDirectory() as work, patch("dsh_pack.export._npm_pack", side_effect=artifact):
            args = (self.pack, self.home, "moved", "add", options)
            preview, _, _ = plan_incremental(*args, work)
            appeared.write_bytes(b'{"concurrent":true}')
            with self.assertRaises(PackImportError) as raised:
                execute_incremental(*args, preview["planToken"], work)
            self.assertEqual(raised.exception.code, "IMPORT_PLAN_CHANGED")
            self.assertFalse(missing.exists())
            preview, _, _ = plan_incremental(*args, work)
            self.assertEqual({item["path"]: item["action"] for item in preview["storage"]},
                             {path: ("add" if self.home / path == missing else "keep") for path in self.files})
            execute_incremental(*args, preview["planToken"], work)
        self.assertEqual(stored.read_bytes(), b'{"local":true}\r\n')
        self.assertEqual(appeared.read_bytes(), b'{"concurrent":true}')
        self.assertEqual(missing.read_bytes(), self.files[missing.relative_to(self.home).as_posix()])

    def test_recursive_storage_update_preserves_target_fields_and_types(self):
        import json
        from copy import deepcopy
        from dsh_pack.pack import sha256_bytes
        source = read(self.pack)
        target = deepcopy(source)
        path = next(iter(self.files))
        target.user_data[path] = b'{"nest":{"local":1,"switch":true},"list":[0,1],"only":false}\r\n'
        source.user_data[path] = b'{"nest":{"switch":1,"new":null},"list":[2]}'
        for item in source.manifest['dataInventory']:
            if item.get('path') == path:
                item.update(sha256=sha256_bytes(source.user_data[path]), bytes=len(source.user_data[path]))
        merged, preview = merge_packs(target, source, 'update')
        value = json.loads(merged.user_data[path])
        self.assertIs(type(value['nest']['switch']), int)
        self.assertEqual(value, {'nest': {'local': 1, 'switch': 1, 'new': None}, 'list': [2], 'only': False})
        self.assertEqual(next(row['action'] for row in preview['storage'] if row['path'] == path), 'update')
        again, preview = merge_packs(merged, source, 'update')
        self.assertEqual(again.user_data, merged.user_data)
        self.assertTrue(all(row['action'] == 'keep' for row in preview['storage']))
        for invalid in (b'[]', b'bad', b'{"x":1,"x":2}', b'{"value":1e999}', b'{"password":"private-test"}'):
            with self.subTest(invalid=invalid):
                target.user_data[path] = invalid
                with self.assertRaises(PackImportError) as raised:
                    merge_packs(target, source, 'update')
                self.assertEqual(raised.exception.code, 'STORAGE_MERGE_UNSAFE')

    def test_interruption_after_original_is_moved_can_restore_it(self):
        from dsh_pack.incremental import _publish_portable_files, _rollback_portable_files
        from dsh_pack.pack import sha256_bytes
        journal = self.home / '.dsh-pack/snapshots/test/transaction.json'
        path = 'storages/example.json'
        original = b'{ "x": 1 }\r\n'
        updated = b'{"x":2}'
        dest = self.home / path
        stage = journal.parent / 'session-stage' / path
        for file, data in [(dest, original), (stage, updated)]:
            file.parent.mkdir(parents=True)
            file.write_bytes(data)
        transaction = {'storageUpdates': {path: {'before': sha256_bytes(original), 'after': sha256_bytes(updated)}}}
        with patch('dsh_pack.incremental.os.link', side_effect=KeyboardInterrupt), self.assertRaises(KeyboardInterrupt):
            _publish_portable_files(self.home, journal, transaction)
        self.assertFalse(dest.exists())
        _rollback_portable_files(self.home, journal, transaction)
        _rollback_portable_files(self.home, journal, transaction)
        self.assertEqual(dest.read_bytes(), original)

    def test_storage_update_detects_stale_plan_and_recovers_interruption(self):
        import shutil
        from dsh_pack.incremental import recover_interrupted
        profile = self.home / 'profiles/moved'
        shutil.copytree(self.pack.parent / 'home/profiles/sample', profile)
        stored, second, missing = (self.home / path for path in self.files)
        stored.parent.mkdir()
        original = b'{ "kind" : "before", "local" : true }\r\n'
        second.write_bytes(original)
        stored.write_bytes(b'{}')
        args = (self.pack, self.home, 'moved', 'update', self.options)
        with tempfile.TemporaryDirectory() as work, patch('dsh_pack.export._npm_pack', side_effect=artifact):
            plan, _, _ = plan_incremental(*args, work)
            stored.write_bytes(original)
            with self.assertRaises(PackImportError) as raised:
                execute_incremental(*args, plan['planToken'], work)
            self.assertEqual(raised.exception.code, 'IMPORT_PLAN_CHANGED')
            plan, _, _ = plan_incremental(*args, work)
            commit = Snapshot.commit
            def interrupt(saved, prepared):
                commit(saved, prepared)
                if saved.target.parent.name == 'imports':
                    self.assertNotEqual(stored.read_bytes(), original)
                    self.assertTrue(missing.is_file())
                    raise KeyboardInterrupt()
            with patch.object(Snapshot, 'commit', interrupt), self.assertRaises(KeyboardInterrupt):
                execute_incremental(*args, plan['planToken'], work)
            recover_interrupted(self.home, 'moved')
            self.assertEqual(stored.read_bytes(), original)
            self.assertEqual(second.read_bytes(), original)
            self.assertFalse(missing.exists())
            plan, _, _ = plan_incremental(*args, work)
            execute_incremental(*args, plan['planToken'], work)
            self.assertEqual(missing.read_bytes(), self.files[missing.relative_to(self.home).as_posix()])

    def test_post_commit_rollback_and_retry(self):
        metadata = self.home / ".dsh-pack/imports/moved"
        original = Snapshot.commit
        def fail_after_commit(snapshot, prepared):
            original(snapshot, prepared)
            if snapshot.target == metadata:
                for path, content in self.files.items():
                    self.assertEqual((self.home / path).read_bytes(), content)
                raise OSError("after all storage and metadata writes")
        with patch.object(Snapshot, "commit", fail_after_commit), self.assertRaises(PackImportError) as raised:
            protected_import(self.pack, self.home, self.options)
        self.assertEqual(raised.exception.code, "IMPORT_ROLLED_BACK")
        self.assertFalse((self.home / "storages").exists())
        for parent in ("profiles", ".dsh-pack/imports"):
            self.assertEqual(list((self.home / parent).iterdir()), [])
        for snapshot in (self.home / ".dsh-pack/snapshots").iterdir():
            self.assertLessEqual({p.name for p in snapshot.iterdir()}, {"journal.json", "transaction.json"})
        protected_import(self.pack, self.home, self.options)
        for path, content in self.files.items():
            self.assertEqual((self.home / path).read_bytes(), content)

    def test_interrupted_publication_is_recovered_on_retry(self):
        import os
        import subprocess
        import sys
        from dsh_pack import __file__ as core_module

        program = """
import os, sys
from pathlib import Path
from dsh_pack.importer import ImportOptions
from dsh_pack.incremental import protected_import
from dsh_pack.snapshot import Snapshot
commit = Snapshot.commit
def interrupt(snapshot, prepared):
    commit(snapshot, prepared)
    if snapshot.target.parent.name == 'imports':
        os._exit(73)
Snapshot.commit = interrupt
protected_import(sys.argv[1], sys.argv[2], ImportOptions(target_profile_name='moved'))
"""
        env = {**os.environ, "PYTHONPATH": str(Path(core_module).resolve().parents[1])}
        process = subprocess.run([sys.executable, "-B", "-c", program, str(self.pack), str(self.home)],
                                 capture_output=True, env=env, timeout=40)
        self.assertEqual(process.returncode, 73, process.stderr)
        for path, content in self.files.items():
            self.assertEqual((self.home / path).read_bytes(), content)
        protected_import(self.pack, self.home, self.options)
        self.assertEqual([p.name for p in (self.home / "profiles").iterdir()], ["moved"])
        self.assertEqual([p.name for p in (self.home / ".dsh-pack/imports").iterdir()], ["moved"])
        for path, content in self.files.items():
            self.assertEqual((self.home / path).read_bytes(), content)
        for snapshot in (self.home / ".dsh-pack/snapshots").iterdir():
            self.assertLessEqual({p.name for p in snapshot.iterdir()}, {"journal.json", "transaction.json"})

    def test_target_created_during_publication_is_preserved(self):
        import os
        link = os.link
        wrote = []
        def concurrent_write(staged, target):
            if wrote:
                target.write_bytes(b'{"local":true}')
            link(staged, target)
            wrote.append(target)
        storage = self.home / "storages"
        storage.mkdir(parents=True)
        marker = storage / "untouched.json"
        marker.write_bytes(b'{"keep":true}')
        with patch("dsh_pack.incremental.os.link", side_effect=concurrent_write), self.assertRaises(PackImportError) as raised:
            protected_import(self.pack, self.home, self.options)
        self.assertEqual(raised.exception.code, "IMPORT_ROLLED_BACK")
        self.assertEqual(len(wrote), 1)
        self.assertFalse(wrote[0].exists())
        self.assertEqual(marker.read_bytes(), b'{"keep":true}')
        survivors = [p for p in storage.iterdir() if p != marker]
        self.assertEqual(len(survivors), 1)
        self.assertEqual(survivors[0].read_bytes(), b'{"local":true}')
