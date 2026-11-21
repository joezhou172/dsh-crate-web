import copy
import json
import shutil
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from test_size_preview import fixture, artifact, ENV, snapshot
from dsh_pack.export import export_profile, ExportOptions
from dsh_pack.pack import read, create
from dsh_pack.partial_import import compatible_pack, prune_plugins, restore_baseline, result_report
from dsh_pack.importer import ImportOptions, import_pack
from dsh_pack.preflight import inspect_pack, PreflightContext
from dsh_pack.errors import DshPackError


class PartialImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.profile = fixture(self.root)
        self.env = copy.deepcopy(ENV); self.env['dsh']['version'] = '0.2.0'
        with patch('dsh_pack.export._npm_command', return_value='unused'), patch('dsh_pack.export._npm_pack', side_effect=artifact):
            self.path = export_profile(self.profile, self.root/'source.dshcrate', options=ExportOptions(environment=self.env, export_mode='freeze')).path
        self.current = copy.deepcopy(self.env); self.current['dsh']['version'] = '0.2.9'

    def test_cross_version_is_warning_strict_still_blocks(self):
        strict = inspect_pack(self.path, context=PreflightContext(current_environment=self.current))
        self.assertTrue(strict.blockers)
        before = self.path.read_bytes()
        with compatible_pack(self.path, self.current) as (path, report):
            compatible = inspect_pack(path, context=PreflightContext(current_environment=self.current, allow_environment_difference=True))
            self.assertFalse(compatible.blockers)
            result = import_pack(path, self.root/'target', options=ImportOptions(current_environment=self.current, allow_environment_difference=True, allow_partial_plugins=True))
            self.assertEqual(result.installed_plugins[0]['name'], 'fixture-plugin')
            self.assertEqual(report['runtimeVerification'], 'UNTESTED')
        self.assertEqual(self.path.read_bytes(), before)

    def test_one_failed_reference_keeps_unrelated_embedded_plugin(self):
        data = read(self.path)
        row = copy.deepcopy(data.plugins_lock['plugins'][0]); row['name'] = 'broken-plugin'
        row['artifact'] = {'mode': 'reference-only'}; row['required'] = False
        data.plugins_lock['plugins'].append(row)
        pkg = json.loads(data.profile_files['package.json']); pkg['dependencies']['broken-plugin'] = '1.0.0'
        data.profile_files['package.json'] = json.dumps(pkg).encode()
        path = create(data, self.root/'mixed.dshcrate')
        def fail(*args): raise RuntimeError('fixture install failed')
        result = import_pack(path, self.root/'target', options=ImportOptions(current_environment=self.env, reference_installer=fail,
             reference_plugin_versions={'broken-plugin': '1.0.0'}, allow_partial_plugins=True, allow_network_reference_install=False))
        self.assertEqual([p['name'] for p in result.installed_plugins], ['fixture-plugin'])
        self.assertEqual(result.as_dict()['completionStatus'], 'DEGRADED')
        self.assertEqual(result.as_dict()['skippedPlugins'][0]['reason'], 'PLUGIN_INSTALL_FAILED')
        self.assertNotIn('broken-plugin', json.loads((result.profile_path/'package.json').read_bytes())['dependencies'])

    def test_strict_install_failure_remains_failure(self):
        data = read(self.path); row = data.plugins_lock['plugins'][0]
        row['artifact'] = {'mode': 'reference-only'}; data.plugin_artifacts = {}
        path = create(data, self.root/'reference.dshcrate')
        with self.assertRaises(DshPackError):
            import_pack(path, self.root/'target', options=ImportOptions(current_environment=self.env, reference_installer=lambda *a: (_ for _ in ()).throw(RuntimeError('failed')), reference_plugin_versions={'fixture-plugin': '1.0.0'}))
        self.assertFalse((self.root/'target/profiles/sample').exists())

    def test_fallback_preserves_old_artifact_and_configuration(self):
        baseline = read(self.path); baseline.profile_files['settings.json'] = b'{"old":true}'
        incoming = copy.deepcopy(baseline); incoming.profile_files['settings.json'] = b'{"old":false}'
        pruned, excluded = prune_plugins(incoming, {'fixture-plugin'})
        restored, names = restore_baseline(pruned, baseline, excluded)
        self.assertEqual(names, {'fixture-plugin'})
        self.assertEqual(restored.profile_files['settings.json'], baseline.profile_files['settings.json'])
        self.assertEqual(restored.plugin_artifacts, baseline.plugin_artifacts)
        self.assertEqual(restored.plugins_lock['plugins'], baseline.plugins_lock['plugins'])

    def test_corrupt_archive_never_downgraded(self):
        self.path.write_bytes(b'not a pack')
        with self.assertRaises(DshPackError), compatible_pack(self.path, self.current): pass

    def test_missing_nonessential_host_bundle_does_not_block_other_content(self):
        data = read(self.path)
        data.plugins_lock['plugins'][0]['runtime']['source'] = 'installation-anchor'
        path = create(data, self.root/'host-missing.dshcrate')
        with compatible_pack(path, self.current, {'other': {}}, self.root) as (prepared, report):
            self.assertEqual(report['skippedPlugins'][0]['reason'], 'HOST_BUNDLE_UNAVAILABLE')
            self.assertEqual(read(prepared).plugins_lock['plugins'], [])

    def test_missing_core_remains_fatal(self):
        from dsh_pack.partial_import import dependency_exclusions
        with self.assertRaisesRegex(DshPackError, '基础环境'):
            dependency_exclusions(read(self.path), {'@deepseek-ai/dsh-base'})

    def test_isolated_probe_includes_embedded_dependency_chain(self):
        from dsh_pack.partial_import import dependency_closure
        manifests = {'a': {'dependencies': {'b': '1'}}, 'b': {'dependencies': {'c':'1'}}, 'c': {},
                     'optional': {'peerDependencies': {'a':'1'}, 'peerDependenciesMeta': {'a': {'optional':True}}}}
        self.assertEqual(dependency_closure({'a'}, manifests), {'a','b','c'})
        self.assertEqual(dependency_closure({'optional'}, manifests), {'optional'})

    def test_failed_update_reinstates_old_files_in_prepared_profile(self):
        baseline = read(self.path); baseline.profile_files['settings.json'] = b'{"value":1}'
        baseline_path = create(baseline, self.root/'baseline.dshcrate')
        (self.profile/'node_modules/fixture-plugin/local-patch.txt').write_text('preserve me')
        incoming = copy.deepcopy(baseline)
        row = incoming.plugins_lock['plugins'][0]
        row['artifact'] = {'mode': 'reference-only'}; row['required'] = False
        row['runtime']['version'] = '2.0.0'; row['requested']['specifier'] = '2.0.0'
        row['resolved'] = {'version': 'unknown', 'locator': 'unknown'}
        incoming.plugin_artifacts = {}; incoming.profile_files['settings.json'] = b'{"value":2}'
        pkg=json.loads(incoming.profile_files['package.json']); pkg['dependencies']['fixture-plugin']='2.0.0'
        incoming.profile_files['package.json']=json.dumps(pkg).encode()
        source=create(incoming,self.root/'update.dshcrate')
        result=import_pack(source,self.root/'newhome',options=ImportOptions(current_environment=self.env,
            reference_installer=lambda *a: (_ for _ in ()).throw(RuntimeError('incoming version failed')),
            reference_plugin_versions={'fixture-plugin':'2.0.0'},allow_network_reference_install=False,
            allow_partial_plugins=True,fallback_pack=baseline_path,fallback_profile=self.profile))
        self.assertEqual((result.profile_path/'settings.json').read_bytes(),b'{"value":1}')
        self.assertEqual((result.profile_path/'node_modules/fixture-plugin/local-patch.txt').read_text(),'preserve me')
        self.assertEqual(result.installed_plugins[0]['version'],'1.0.0')
        self.assertTrue(result.as_dict()['skippedPlugins'][0]['retainedExisting'])

    def test_explicit_platform_exclusion_is_reported(self):
        package = self.profile/'node_modules/fixture-plugin/package.json'
        pkg=json.loads(package.read_text()); pkg['os']=['linux']; package.write_text(json.dumps(pkg))
        with patch('dsh_pack.export._npm_command', return_value='unused'), patch('dsh_pack.export._npm_pack', side_effect=artifact):
            export_profile(self.profile, self.path, options=ExportOptions(environment=self.env, export_mode='freeze'))
        self.current['os']['name'] = 'windows'
        with compatible_pack(self.path, self.current) as (path, report):
            self.assertEqual(read(path).plugins_lock['plugins'], [])
            self.assertEqual(report['skippedPlugins'][0]['reason'], 'PLUGIN_OS_UNSUPPORTED')
            self.assertEqual(result_report({}, report)['completionStatus'], 'DEGRADED')

    @unittest.skipUnless(os.environ.get('CRATE_PNPM_COMMAND'), 'requires existing pnpm; no installation')
    def test_real_manager_isolates_unavailable_offline_dependency(self):
        package=self.profile/'node_modules/broken-dependency-plugin'; package.mkdir()
        (package/'package.json').write_text(json.dumps({'name':'broken-dependency-plugin','version':'1.0.0',
            'dependencies':{'crate-intentionally-nonexistent-fixture-20261105':'9999.0.0'}}))
        manifest=json.loads((self.profile/'package.json').read_bytes());manifest['dependencies']['broken-dependency-plugin']='1.0.0'
        (self.profile/'package.json').write_text(json.dumps(manifest))
        with patch('dsh_pack.export._npm_command',return_value='unused'),patch('dsh_pack.export._npm_pack',side_effect=artifact):
            path=export_profile(self.profile,self.root/'manager.dshcrate',options=ExportOptions(environment=self.env,export_mode='freeze')).path
        with compatible_pack(path,self.env) as (prepared,report), patch.dict(os.environ, {
            'npm_config_store_dir':str(self.root/'pnpm-store'), 'XDG_CACHE_HOME':str(self.root/'cache'),
            'XDG_DATA_HOME':str(self.root/'data'), 'XDG_CONFIG_HOME':str(self.root/'config')}):
            result=import_pack(prepared,self.root/'target',options=ImportOptions(current_environment=self.env,
                allow_partial_plugins=True,allow_network_reference_install=False,pnpm_command=tuple(json.loads(os.environ['CRATE_PNPM_COMMAND']))))
        self.assertEqual([r['name'] for r in result.installed_plugins],['fixture-plugin'], str(result.network_installs)[-1000:])
        self.assertEqual(result.as_dict()['skippedPlugins'][0]['name'],'broken-dependency-plugin')
        self.assertTrue((result.profile_path/'pnpm-lock.yaml').is_file())

    @unittest.skipUnless(os.environ.get('CRATE_PNPM_COMMAND'), 'requires existing pnpm; no installation')
    def test_transient_download_failure_retries_then_real_install_completes(self):
        original = subprocess.run
        calls = []
        def run(args, **kwargs):
            if 'install' in args:
                calls.append(args)
                if len(calls) == 1:
                    return subprocess.CompletedProcess(args, 1, stdout='ERR_PNPM_META_FETCH_FAIL: fetch failed', stderr='')
            return original(args, **kwargs)
        with patch('dsh_pack.importer.subprocess.run', side_effect=run), patch.dict(os.environ, {
            'npm_config_store_dir':str(self.root/'pnpm-store'), 'XDG_CACHE_HOME':str(self.root/'cache'),
            'XDG_DATA_HOME':str(self.root/'data'), 'XDG_CONFIG_HOME':str(self.root/'config')}):
            result = import_pack(self.path,self.root/'retry-target',options=ImportOptions(current_environment=self.env,
                allow_network_reference_install=False,pnpm_command=tuple(json.loads(os.environ['CRATE_PNPM_COMMAND']))))
        self.assertEqual(len(calls), 2)
        self.assertEqual(result.network_installs[-1]['attempts'], 2)
        self.assertEqual(result.installed_plugins[0]['name'], 'fixture-plugin')


if __name__ == '__main__': unittest.main()
