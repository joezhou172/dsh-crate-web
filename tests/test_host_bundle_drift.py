"""Pack 的环境标签不能代替官方 Bundle 的实际运行版本。"""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'core'))
from test_size_preview import ENV, artifact, fixture
from dsh_pack.compatibility import adapt_data
from dsh_pack.errors import PackImportError
from dsh_pack.export import ExportOptions, export_profile
from dsh_pack.pack import create, read, sha256_bytes
from dsh_pack.partial_import import compatible_pack


class HostBundleDriftTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        profile = fixture(self.root)
        self.environment = copy.deepcopy(ENV)
        self.environment['dsh']['version'] = '0.2.2-rc.3'
        with patch('dsh_pack.export._npm_command', return_value='fixture-npm'), patch('dsh_pack.export._npm_pack', side_effect=artifact):
            baseline = export_profile(profile, self.root/'baseline.dshcrate', options=ExportOptions(environment=self.environment, export_mode='freeze')).data
        self.name = '@deepseek-ai/dsh-web-app'
        package = self.root/'old-web'; package.mkdir()
        (package/'package.json').write_text(json.dumps({'name': self.name, 'version': '0.2.2-rc.1'}))
        content = artifact(package)
        row = copy.deepcopy(baseline.plugins_lock['plugins'][0])
        row.update(name=self.name, required=True)
        row['requested']['specifier'] = '0.2.2-rc.1'
        row['resolved'] = {'version': 'unknown', 'locator': 'unknown'}
        row['runtime'] = {'entry': self.name, 'source': 'installation-anchor', 'version': '0.2.2-rc.1'}
        row['artifact'] = {'mode': 'embedded', 'path': 'plugins/old-web.tgz', 'sha256': sha256_bytes(content)}
        baseline.plugins_lock['plugins'].append(row)
        baseline.plugin_artifacts['old-web.tgz'] = content
        manifest = json.loads(baseline.profile_files['package.json'])
        manifest['dependencies'][self.name] = '0.2.2-rc.1'
        baseline.profile_files['package.json'] = json.dumps(manifest).encode()
        self.data = baseline
        self.source = create(baseline, self.root/'source.dshcrate')
        self.modules = self.root/'modules'
        host_root = self.modules/self.name; host_root.mkdir(parents=True)
        manifest = {'name': self.name, 'version': '0.2.2-rc.3'}
        payload = json.dumps(manifest).encode()
        (host_root/'package.json').write_bytes(payload)
        self.host = {self.name: {'manifest': manifest, 'files': {'package.json': sha256_bytes(payload)}}}

    def test_same_environment_tag_still_adapts_old_anchor(self):
        before = copy.deepcopy(self.data)
        result, report = adapt_data(self.data, '0.2.2-rc.3', self.host, self.modules)
        self.assertEqual(result.plugins_lock['plugins'][1]['runtime']['version'], '0.2.2-rc.3')
        self.assertEqual(result.plugins_lock['plugins'][0], before.plugins_lock['plugins'][0])
        self.assertEqual(self.data, before)
        self.assertEqual(report['changes'][0]['from'], '0.2.2-rc.1')
        self.assertEqual(report['runtimeVerification'], 'UNTESTED')

    def test_compatible_entrypoint_checks_runtime_identity(self):
        before = self.source.read_bytes()
        with compatible_pack(self.source, self.environment, self.host, self.modules) as (path, report):
            restored = read(path)
            self.assertEqual(restored.plugins_lock['plugins'][1]['runtime']['version'], '0.2.2-rc.3')
            self.assertIsNotNone(report['hostAdaptation'])
        self.assertEqual(self.source.read_bytes(), before)

    def test_mismatched_anchor_requires_verified_host_files(self):
        (self.modules/self.name/'package.json').write_bytes(b'{}')
        with self.assertRaises(PackImportError):
            adapt_data(self.data, '0.2.2-rc.3', self.host, self.modules)

    def test_same_environment_does_not_rewrite_third_party_only_pack(self):
        data = copy.deepcopy(self.data)
        data.plugins_lock['plugins'][1]['runtime']['source'] = 'profile-dependency'
        result, report = adapt_data(data, '0.2.2-rc.3', self.host, self.modules)
        self.assertIs(result, data)
        self.assertIsNone(report)


if __name__ == '__main__': unittest.main()
