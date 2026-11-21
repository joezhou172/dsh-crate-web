"""显式换版的制品、原件保护与失败边界；不等同于插件业务验收。"""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from test_size_preview import fixture, artifact, ENV, snapshot
from dsh_pack.export import export_profile, ExportOptions
from dsh_pack.pack import read, create
from dsh_pack.version_choices import prepare, check_existing, read_audit, AUDIT
from dsh_pack.errors import DshPackError


class VersionChoicesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.profile = fixture(self.root)
        self.source = self.root / 'original.dshcrate'
        self.output = self.root / 'chosen.dshcrate'
        with patch('dsh_pack.export._npm_pack', side_effect=artifact), patch('dsh_pack.export._npm_command', return_value='fixture-npm'):
            export_profile(self.profile, self.source, options=ExportOptions(environment=ENV, export_mode='freeze'))
        self.before = self.source.read_bytes()
        self.files = snapshot(self.profile)

    def fetch(self, profile, name, version, *args, **kwargs):
        self.assertTrue(kwargs['reject_deprecated'])
        folder = self.root / 'download'; folder.mkdir(exist_ok=True)
        manifest = {'name': name, 'version': version}
        (folder / 'package.json').write_text(json.dumps(manifest))
        (folder / 'index.js').write_text('export default {}')
        return manifest, artifact(folder), 'sha512-fixture', 'https://registry.npmjs.org/fixture.tgz'

    def choose(self, **overrides):
        choice = {'name': 'fixture-plugin', 'action': 'replace', 'version': '1.1.0', **overrides}
        return prepare(self.source, self.output, [choice], self.profile)

    def test_replacement_frozen_and_original_unchanged(self):
        with patch('dsh_pack.version_choices.fetch', side_effect=self.fetch) as download:
            record = self.choose()
        self.assertEqual(download.call_count, 1)
        chosen = read(self.output)
        self.assertEqual(chosen.plugins_lock['plugins'][0]['runtime']['version'], '1.1.0')
        self.assertEqual(json.loads(chosen.profile_files['package.json'])['dependencies']['fixture-plugin'], '1.1.0')
        self.assertEqual(read_audit(chosen)['choices'][0]['to'], '1.1.0')
        self.assertEqual(record['runtimeVerification'], 'UNTESTED')
        self.assertEqual(self.source.read_bytes(), self.before)
        self.assertEqual(snapshot(self.profile), self.files)

    def test_bad_choices_never_download(self):
        for overrides in [{'version': '0.9.0'}, {'name': '../bad'}, {'version': 'latest'}, {'name': 'absent'}, {'action': 'auto'}]:
            with self.subTest(overrides=overrides), patch('dsh_pack.version_choices.fetch') as download:
                with self.assertRaises(DshPackError): self.choose(**overrides)
                download.assert_not_called()

    def test_corrupt_pack_never_downloads(self):
        self.source.write_bytes(b'not a pack')
        with patch('dsh_pack.version_choices.fetch') as download:
            with self.assertRaises(DshPackError): self.choose()
            download.assert_not_called()

    def test_corrupt_inspect_keeps_structured_diagnostic(self):
        import io
        from contextlib import redirect_stdout
        from dsh_pack.cli import main
        self.source.write_bytes(b'broken')
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(['inspect', str(self.source), '--compatibility-policy', 'strict', '--json'])
        result = json.loads(output.getvalue())
        self.assertEqual(code, 1)
        self.assertFalse(result['canContinue'])
        self.assertTrue(result['findings'])

    def test_skip_records_choice_and_removes_dependency(self):
        self.choose(action='skip')
        data = read(self.output)
        self.assertEqual(data.plugins_lock['plugins'], [])
        self.assertEqual(data.manifest['completeness']['embedded'], [])
        self.assertEqual(read_audit(data)['choices'][0]['action'], 'skip')
        self.assertNotIn('fixture-plugin', json.loads(data.profile_files['package.json'])['dependencies'])

    def test_add_mode_and_target_downgrade_blocked(self):
        with patch('dsh_pack.version_choices.fetch', side_effect=self.fetch): self.choose()
        data = read(self.output)
        home = self.profile.parent.parent
        with self.assertRaises(DshPackError): check_existing(data, home, 'sample', 'add')
        check_existing(data, home, 'sample', 'update')
        installed = self.profile / 'node_modules/fixture-plugin/package.json'
        installed.write_text(json.dumps({'name': 'fixture-plugin', 'version': '2.0.0'}))
        with self.assertRaises(DshPackError): check_existing(data, home, 'sample', 'update')
        for target in ['..', '.', '../sample']:
            with self.assertRaises(DshPackError): check_existing(data, home, target, 'update')

    def test_derived_import_and_failed_overwrite_restore_real_files(self):
        from dsh_pack.importer import ImportOptions
        from dsh_pack.incremental import protected_import
        from dsh_pack.snapshot import Snapshot
        from dsh_pack.errors import PackImportError
        home = self.root / 'destination'
        protected_import(self.source, home, ImportOptions(current_environment=ENV))
        target = home / 'profiles/sample'
        before = snapshot(target)
        with patch('dsh_pack.version_choices.fetch', side_effect=self.fetch): self.choose()
        original_commit = Snapshot.commit
        def fail_after_profile_commit(saved, prepared):
            original_commit(saved, prepared)
            if saved.target == target:
                raise PackImportError('controlled post-commit failure', stage='commit', code='FIXTURE_FAILURE')
        with patch.object(Snapshot, 'commit', fail_after_profile_commit):
            with self.assertRaises(DshPackError):
                protected_import(self.output, home, ImportOptions(current_environment=ENV,
                    overwrite_existing_profile=True, overwrite_confirmation='OVERWRITE'))
        self.assertEqual(snapshot(target), before)
        protected_import(self.output, home, ImportOptions(current_environment=ENV,
            overwrite_existing_profile=True, overwrite_confirmation='OVERWRITE'))
        self.assertEqual(json.loads((target/'node_modules/fixture-plugin/package.json').read_bytes())['version'], '1.1.0')
        self.assertEqual(json.loads((home/'.dsh-pack/imports/sample/version-choices.json').read_bytes())['choices'][0]['to'], '1.1.0')
        self.assertEqual(self.source.read_bytes(), self.before)

    def test_explicit_skip_retains_existing_plugin_and_config_in_strict_update(self):
        from dsh_pack.importer import ImportOptions
        from dsh_pack.incremental import protected_import, locked_plan, locked_execute
        from dsh_pack.version_choices import choice_report
        home = self.root / 'destination'
        protected_import(self.source, home, ImportOptions(current_environment=ENV))
        target = home / 'profiles/sample'
        (target/'settings.json').write_text('{"existing":true}')
        data = read(self.source); data.profile_files['settings.json'] = b'{"existing":false}'
        create(data, self.source)
        self.choose(action='skip')
        options = ImportOptions(current_environment=ENV, compatibility_report=choice_report(read(self.output)))
        work = self.root/'incremental'; work.mkdir()
        with patch('dsh_pack.export._npm_command', return_value='fixture-npm'), patch('dsh_pack.export._npm_pack', side_effect=artifact):
            plan, _, _ = locked_plan(self.output, home, 'sample', 'update', options, work)
            locked_execute(self.output, home, 'sample', 'update', options, plan['planToken'], work)
        self.assertEqual(json.loads((target/'settings.json').read_bytes()), {'existing': True})
        self.assertEqual(json.loads((target/'node_modules/fixture-plugin/package.json').read_bytes())['version'], '1.0.0')
        self.assertTrue((home/'.dsh-pack/imports/sample/version-choices.json').is_file())

    def test_untrusted_audit_rejected(self):
        data = read(self.source)
        for value in [[], {'choices': [{}]}, {'choices': [{'action': 'replace', 'name': '../../outside', 'from': '1.0.0', 'to': '2.0.0'}]}]:
            data.profile_files[AUDIT] = json.dumps(value).encode()
            with self.assertRaises(DshPackError): read_audit(data)

    def test_schema4_missing_bundle_patch_is_not_silently_ready(self):
        from dsh_pack.preflight import inspect_pack
        data = read(self.source)
        data.plugins_lock['plugins'][0]['bundle'] = {'enabled': True, 'order': 0, 'patch': './missing.yml'}
        package = json.loads(data.profile_files['package.json'])
        package['dsh'] = {'profile': {'bundles': ['fixture-plugin']}}
        data.profile_files['package.json'] = json.dumps(package).encode()
        create(data, self.output, compression='fast')
        self.assertEqual(read(self.output).manifest['schemaVersion'], 4)
        result = inspect_pack(self.output).as_dict()
        self.assertTrue(any(f['code'] == 'BUNDLE_PATCH_INVALID' and f['evidence']['plugin'] == 'fixture-plugin' for f in result['findings']))

    def test_official_anchor_not_replaceable(self):
        data = read(self.source)
        data.plugins_lock['plugins'][0]['runtime']['source'] = 'installation-anchor'
        create(data, self.source, compression='fast')
        with patch('dsh_pack.version_choices.fetch') as download:
            with self.assertRaises(DshPackError): self.choose()
            download.assert_not_called()


if __name__ == '__main__': unittest.main()
