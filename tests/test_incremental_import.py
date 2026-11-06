import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'core'))
from dsh_pack.incremental import merge_json, merge_packs, recover_interrupted, preserve_local_files, preserve_kept_plugins, finalize_metadata, execute_incremental
from dsh_pack.snapshot import Snapshot, inventory, save_json
from dsh_pack.pack import PackData
from dsh_pack.errors import PackImportError


def data(version, plugins=('one',), config=None):
    rows = [{'name': name, 'runtime': {'version': version}, 'artifact': {'mode': 'reference-only'},
             'bundle': {'enabled': True, 'order': i, 'patch': 'cordis.patch.yml'}} for i, name in enumerate(plugins)]
    package = {'name': 'target', 'dependencies': {name: version for name in plugins}, 'dsh': {'profile': {'bundles': list(plugins)}}}
    return PackData({'schemaVersion': 2, 'requiredSecrets': []}, {'package.json': json.dumps(package).encode(),
                    'settings.json': json.dumps(config or {}).encode()}, {'schemaVersion': 1, 'plugins': rows}, {})


class MergeTests(unittest.TestCase):
    def test_add_preserves_and_appends(self):
        original = data('1', ('one', 'keep'), {'a': 1, 'keep': True})
        merged, preview = merge_packs(original, data('2', ('one', 'new'), {'a': 2, 'b': 3}), 'add')
        self.assertEqual(json.loads(merged.profile_files['settings.json']), {'a': 1, 'keep': True, 'b': 3})
        self.assertEqual(json.loads(merged.profile_files['package.json'])['dependencies'], {'one': '1', 'keep': '1', 'new': '2'})
        self.assertEqual([p['action'] for p in preview['plugins']], ['keep', 'add'])

    def test_update_preserves_absent_items(self):
        merged, _ = merge_packs(data('1', ('one', 'keep'), {'a': 1, 'keep': True}), data('2', ('one', 'new'), {'a': 2}), 'update')
        self.assertEqual(json.loads(merged.profile_files['settings.json']), {'a': 2, 'keep': True})
        self.assertEqual(json.loads(merged.profile_files['package.json'])['dsh']['profile']['bundles'], ['one', 'keep', 'new'])

    def test_nested_merge_no_mutation(self):
        target = {'a': {'x': 1, 'y': 2}}
        self.assertEqual(merge_json(target, {'a': {'x': 4}}, 'update'), {'a': {'x': 4, 'y': 2}})
        self.assertEqual(target['a']['x'], 1)


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.target = self.home / 'profiles' / 'target'; self.target.mkdir(parents=True)
        (self.target / 'config.json').write_text('original')
        self.prepared = self.target.parent / 'prepared'; self.prepared.mkdir()
        (self.prepared / 'config.json').write_text('updated')

    def test_commit_then_restore_bytes(self):
        saved = Snapshot(self.home, self.target); before = inventory(self.target)
        saved.commit(self.prepared)
        self.assertEqual((self.target / 'config.json').read_text(), 'updated')
        saved.rollback()
        self.assertEqual(inventory(self.target), before)
        self.assertEqual(saved.state['status'], 'restored')

    def test_failed_commit_restores(self):
        saved = Snapshot(self.home, self.target)
        original = Path.rename
        def rename(path, destination):
            if path == self.prepared:
                raise PermissionError('fixture: locked commit')
            return original(path, destination)
        with patch.object(Path, 'rename', rename), self.assertRaises(PackImportError) as caught:
            saved.commit(self.prepared)
        self.assertEqual(caught.exception.code, 'IMPORT_ROLLED_BACK')
        self.assertEqual((self.target / 'config.json').read_text(), 'original')

    def test_changed_target_blocks(self):
        saved = Snapshot(self.home, self.target)
        (self.target / 'config.json').write_text('changed elsewhere')
        with self.assertRaises(PackImportError) as caught:
            saved.commit(self.prepared)
        self.assertEqual(caught.exception.code, 'TARGET_CHANGED')
        self.assertEqual((self.target / 'config.json').read_text(), 'changed elsewhere')

    def test_recovery_failure_not_success(self):
        saved = Snapshot(self.home, self.target); saved.commit(self.prepared)
        with patch.object(Path, 'rename', side_effect=PermissionError('fixture: restore locked')):
            with self.assertRaises(PackImportError) as caught:
                saved.rollback()
        self.assertEqual(caught.exception.code, 'ROLLBACK_FAILED')
        self.assertTrue((saved.root / 'original').exists())

    def test_interrupted_commit_journal(self):
        saved = Snapshot(self.home, self.target)
        save_json(saved.root / 'transaction.json', {'status': 'active', 'target': 'target', 'snapshots': [str(saved.root)]})
        self.target.rename(saved.root / 'original')
        recover_interrupted(self.home, 'target')
        self.assertEqual((self.target / 'config.json').read_text(), 'original')

    def test_unowned_new_target_is_not_removed(self):
        absent = self.home / 'profiles' / 'other'
        saved = Snapshot(self.home, absent)
        absent.mkdir(); (absent / 'keep').write_text('external')
        with self.assertRaises(PackImportError):
            saved.rollback()
        self.assertEqual((absent / 'keep').read_text(), 'external')

    def test_local_files_preserved_without_replacing_merged_config(self):
        (self.target / '.env').write_text('fixture-only')
        preserve_local_files(self.target, self.prepared)
        self.assertEqual((self.prepared / '.env').read_text(), 'fixture-only')
        self.assertEqual((self.prepared / 'config.json').read_text(), 'updated')

    def test_metadata_refers_to_final_target(self):
        (self.prepared / 'prepared.json').write_text(json.dumps({'profile': {'name': 'stage'}, 'plugins': []}))
        finalize_metadata(self.prepared, self.target)
        self.assertEqual(json.loads((self.prepared / 'prepared.json').read_text())['profile'], {'name': 'target', 'path': str(self.target)})

    def test_kept_plugin_preserves_files_excluded_by_npm_pack(self):
        for base in (self.target, self.prepared):
            for name in ('keep', 'update'):
                (base / 'node_modules' / name).mkdir(parents=True)
                (base / 'node_modules' / name / 'index.js').write_text('old' if base == self.target else 'new')
        (self.target / 'node_modules/keep/DSH22-COMPATIBILITY.json').write_text('{"forkMode":"inherit"}')
        preserve_kept_plugins(self.target, self.prepared, ['keep'])
        self.assertEqual(inventory(self.target / 'node_modules/keep'), inventory(self.prepared / 'node_modules/keep'))
        self.assertEqual((self.prepared / 'node_modules/update/index.js').read_text(), 'new')

    def test_kept_plugin_rejects_escaping_path(self):
        with self.assertRaises(PackImportError):
            preserve_kept_plugins(self.target, self.prepared, ['../../outside'])

    def test_metadata_commit_failure_restores_both_trees(self):
        from types import SimpleNamespace
        from dsh_pack.importer import ImportOptions
        metadata = self.home / '.dsh-pack/imports/target'; metadata.mkdir(parents=True)
        (metadata / 'prepared.json').write_text('{"old": true}')
        stage_meta = metadata.parent / 'stage'; stage_meta.mkdir()
        (stage_meta / 'prepared.json').write_text('{"profile": {}}')
        before, before_meta = inventory(self.target), inventory(metadata)
        result = SimpleNamespace(profile_path=self.prepared, metadata_path=stage_meta)
        commit = Snapshot.commit
        def fail_metadata(saved, prepared):
            if saved.target == metadata:
                raise PackImportError('提交失败', stage='commit', code='IMPORT_ROLLED_BACK',
                                      details={'originalError': 'fixture: metadata locked'})
            return commit(saved, prepared)
        with patch('dsh_pack.incremental.plan_incremental', return_value=({'planToken': 'token'}, Path('fixture'), 'stage')), \
             patch('dsh_pack.importer.import_pack', return_value=result), \
             patch.object(Snapshot, 'commit', fail_metadata):
            with self.assertRaises(PackImportError) as caught:
                execute_incremental('fixture', self.home, 'target', 'update', ImportOptions(), 'token', self.home)
        self.assertEqual(caught.exception.code, 'IMPORT_ROLLED_BACK')
        self.assertEqual(inventory(self.target), before)
        self.assertEqual(inventory(metadata), before_meta)
        diagnostic = caught.exception.as_dict()['details']['originalError']
        self.assertEqual(diagnostic['stage'], 'commit')
        self.assertEqual(diagnostic['details']['originalError'], 'fixture: metadata locked')


if __name__ == '__main__':
    unittest.main()
