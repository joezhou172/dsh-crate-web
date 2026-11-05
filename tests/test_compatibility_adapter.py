import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'core'))
from dsh_pack.compatibility import adapt_data
from dsh_pack.pack import PackData, sha256_bytes
from dsh_pack.errors import PackImportError


class CompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.modules = Path(self.temp.name)
        name = '@deepseek-ai/fixture'
        root = self.modules / name; root.mkdir(parents=True)
        package = {'name': name, 'version': '0.2.2-rc.1', 'dsh': {'bundle': {'patch': ['a.yml']}}}
        payload = json.dumps(package).encode(); (root / 'package.json').write_bytes(payload)
        self.host = {name: {'manifest': package, 'files': {'package.json': sha256_bytes(payload)}}}
        row = {'name': name, 'runtime': {'source': 'installation-anchor', 'version': '0.2.1-rc.5'},
               'bundle': {'enabled': True}, 'artifact': {'mode': 'reference-only'}}
        third = {'name': 'third-party', 'runtime': {'source': 'profile', 'version': '1.0.0'}, 'bundle': {'enabled': False}}
        self.data = PackData({'schemaVersion': 2, 'environment': {'dsh': {'version': '0.2.1-rc.5'}}},
                             {'package.json': json.dumps({'dependencies': {name: '0.2.1-rc.5'}}).encode()},
                             {'schemaVersion': 1, 'plugins': [row, third]}, {})

    def test_adapts_only_verified_official_artifacts(self):
        original = copy.deepcopy(self.data)
        result, report = adapt_data(self.data, '0.2.2-rc.1', self.host, self.modules)
        self.assertEqual(result.plugins_lock['plugins'][1], original.plugins_lock['plugins'][1])
        self.assertEqual(self.data, original)
        self.assertEqual(report['runtimeVerification'], 'UNTESTED')
        self.assertEqual(result.plugins_lock['schemaVersion'], 2)
        again, _ = adapt_data(self.data, '0.2.2-rc.1', self.host, self.modules)
        self.assertEqual(again.plugin_artifacts, result.plugin_artifacts)

    def test_tamper_is_blocked(self):
        (self.modules / '@deepseek-ai/fixture/package.json').write_text('{}')
        with self.assertRaises(PackImportError):
            adapt_data(self.data, '0.2.2-rc.1', self.host, self.modules)

    def test_unknown_path_is_blocked(self):
        with self.assertRaises(PackImportError):
            adapt_data(self.data, '0.2.3', self.host, self.modules)

    def test_same_version_no_rewrite(self):
        result, report = adapt_data(self.data, '0.2.1-rc.5', {}, None)
        self.assertIs(result, self.data)
        self.assertIsNone(report)
