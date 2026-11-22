import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_size_preview import ENV, artifact, fixture
from dsh_pack.errors import PackImportError
from dsh_pack.export import ExportOptions, export_profile
from dsh_pack.importer import ImportOptions
from dsh_pack.incremental import merge_packs, protected_import
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

    def test_storage_preflight_new_only(self):
        for policy in ("strict", "compatible"):
            with self.subTest(policy=policy):
                code, preview = _invoke_core(["inspect", str(self.pack), "--compatibility-policy", policy])
                self.assertEqual(code, 0, preview)
                self.assertTrue(preview["canContinue"])
        data = read(self.pack)
        for mode in ("add", "update"):
            with self.assertRaises(PackImportError) as raised:
                merge_packs(data, data, mode)
            self.assertEqual(raised.exception.code, "INCREMENTAL_HOME_DATA_UNSUPPORTED")
        code, rejected = _invoke_core(["import", str(self.pack), "--overwrite", "--confirm-overwrite",
                                       "--target-profile", "moved", "--dsh-home", str(self.home), "--plan-only"])
        self.assertNotEqual(code, 0)
        self.assertEqual(rejected["error"]["code"], "PORTABLE_DATA_OVERWRITE_FORBIDDEN")

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
