"""退役官方 Bundle 的基线归一化不能改写日用目录或删除制品。"""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'core'))
from test_size_preview import ENV, artifact
from dsh_pack.export import export_profile, ExportOptions
from dsh_pack.importer import ImportOptions
from dsh_pack.incremental import plan_incremental
from dsh_pack.pack import read, create
from dsh_pack.snapshot import inventory
from dsh_pack.errors import PackImportError, ExportError


class RetiredBundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.home = self.root/'home'
        self.target = self.home/'profiles/target'; self.target.mkdir(parents=True)
        self.retired = '@deepseek-ai/dsh-experimental-agent-team-profile'
        self.current = '@deepseek-ai/dsh-web-app'
        names = ['@deepseek-ai/dsh-base', self.current, self.retired, 'third-party']
        manifest = {'name': 'target', 'dependencies': {n: '0.2.2-rc.3' for n in names}, 'dsh': {'profile': {'bundles': names}}}
        (self.target/'package.json').write_text(json.dumps(manifest))
        for name in names:
            folder = self.target/'node_modules'/name; folder.mkdir(parents=True)
            (folder/'package.json').write_text(json.dumps({'name': name, 'version': '0.2.2-rc.3', 'dsh': {'bundle': {'patch': './cordis.patch.yml'}}}))
            ids = {'@deepseek-ai/dsh-base': ['agent-team', 'tool-agent-team'], self.current: ['ui-agent-team'],
                   self.retired: ['agent-team', 'tool-agent-team', 'ui-agent-team'], 'third-party': ['third-row']}[name]
            (folder/'cordis.patch.yml').write_text('- insert:\n' + ''.join('  - id: '+row+'\n    name: '+name+'\n' for row in ids))
        self.env = copy.deepcopy(ENV); self.env['dsh']['version'] = '0.2.2-rc.3'
        self.evidence = {'source': 'official-retired-bundles', 'runtimeVersion': '0.2.2-rc.3', 'catalogSha256': 'a'*64, 'bootSha256': 'b'*64, 'retiredBundles': [self.retired]}
        self.options = ImportOptions(current_environment=self.env, allow_environment_difference=True,
            patch_adapter_command=(sys.executable, 'unused-adapter'))
        self.npm = patch('dsh_pack.export._npm_command', return_value='fixture-npm'); self.npm.start(); self.addCleanup(self.npm.stop)
        self.pack = patch('dsh_pack.export._npm_pack', side_effect=artifact); self.pack.start(); self.addCleanup(self.pack.stop)
        # 输入包已按当前宿主清掉退役激活项；目标目录仍保留它。
        source_root = self.root/'source'; source_root.mkdir()
        data = None
        with patch('dsh_pack.export._assert_no_duplicate_loader_rows'):
            data = export_profile(self.target, self.root/'raw.dshcrate', options=ExportOptions(environment=self.env, export_mode='freeze')).data
        pkg = json.loads(data.profile_files['package.json']); pkg['dsh']['profile']['bundles'].remove(self.retired)
        data.profile_files['package.json'] = json.dumps(pkg).encode()
        for row in data.plugins_lock['plugins']:
            if row['name'] == self.retired: row['bundle'] = {'enabled': False, 'order': None, 'patch': None}
            elif row['bundle']['enabled']: row['bundle']['order'] = pkg['dsh']['profile']['bundles'].index(row['name'])
        self.source = create(data, self.root/'source.dshcrate')

    def test_normal_export_still_rejects_duplicate_rows(self):
        with self.assertRaises(ExportError):
            export_profile(self.target, self.root/'bad.dshcrate', options=ExportOptions(environment=self.env, export_mode='freeze'))

    def test_add_and_update_disable_only_verified_retired_bundle(self):
        before = inventory(self.target)
        for mode in ('add', 'update'):
            with self.subTest(mode=mode):
                directory = self.root/mode; directory.mkdir()
                with patch('dsh_pack.incremental.subprocess.run', return_value=type('Run', (), {'returncode': 0, 'stdout': json.dumps(self.evidence).encode()})()):
                    preview, path, _ = plan_incremental(self.source, self.home, 'target', mode, self.options, directory)
                data = read(path); pkg = json.loads(data.profile_files['package.json'])
                self.assertNotIn(self.retired, pkg['dsh']['profile']['bundles'])
                self.assertIn('third-party', pkg['dsh']['profile']['bundles'])
                self.assertIn(self.retired, pkg['dependencies'])
                self.assertIn(self.retired, [r['name'] for r in data.plugins_lock['plugins']])
                self.assertEqual(preview['retiredBundles'][0]['name'], self.retired)
                self.assertEqual(preview['retiredBundles'][0]['action'], 'disable')
                self.assertEqual(inventory(self.target), before)

    def test_missing_catalog_cannot_guess_retirement(self):
        self.evidence['retiredBundles'] = []
        directory = self.root/'missing'; directory.mkdir()
        with patch('dsh_pack.incremental.subprocess.run', return_value=type('Run', (), {'returncode': 0, 'stdout': json.dumps(self.evidence).encode()})()), self.assertRaises(PackImportError):
            plan_incremental(self.source, self.home, 'target', 'add', self.options, directory)

    def test_bad_host_evidence_and_third_party_retirement_are_rejected(self):
        for field, value in [('runtimeVersion', '0.2.2-rc.1'), ('retiredBundles', ['third-party']),
                             ('catalogSha256', 'bad'), ('retiredBundles', ['@deepseek-ai/dsh-base'])]:
            with self.subTest(field=field, value=value):
                evidence = {**self.evidence, field: value}
                with patch('dsh_pack.incremental.subprocess.run', return_value=type('Run', (), {'returncode': 0, 'stdout': json.dumps(evidence).encode()})()), self.assertRaises(PackImportError) as caught:
                    plan_incremental(self.source, self.home, 'target', 'add', self.options, self.root/'unused')
                self.assertEqual(caught.exception.code, 'HOST_RETIREMENT_EVIDENCE_INVALID')

    def test_retired_bundle_without_dependency_still_keeps_artifact(self):
        manifest = json.loads((self.target/'package.json').read_bytes())
        del manifest['dependencies'][self.retired]
        (self.target/'package.json').write_text(json.dumps(manifest))
        before = inventory(self.target)
        result = export_profile(self.target, self.root/'retained.dshcrate', options=ExportOptions(
            environment=self.env, export_mode='freeze', retired_bundles=(self.retired,)))
        row = next(row for row in result.data.plugins_lock['plugins'] if row['name'] == self.retired)
        self.assertFalse(row['bundle']['enabled'])
        self.assertIn(row['artifact']['path'][len('plugins/'):], result.data.plugin_artifacts)
        self.assertEqual(inventory(self.target), before)

    def test_plan_token_binds_actual_host_catalog_hash(self):
        tokens = []
        for index in range(2):
            directory = self.root/('plan-'+str(index)); directory.mkdir()
            evidence = {**self.evidence, 'catalogSha256': str(index)*64}
            with patch('dsh_pack.incremental.subprocess.run', return_value=type('Run', (), {'returncode': 0, 'stdout': json.dumps(evidence).encode()})()):
                preview, _, _ = plan_incremental(self.source, self.home, 'target', 'add', self.options, directory)
            tokens.append(preview['planToken'])
        self.assertNotEqual(*tokens)


if __name__ == '__main__': unittest.main()
