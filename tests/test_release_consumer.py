"""防止发布包在空 Profile 中自动拉入旧 DSH；真实安装由发布制品门槛执行。"""
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ConsumerDependencyTests(unittest.TestCase):
    def test_host_provided_peers_do_not_auto_install_another_dsh(self):
        package = json.loads((ROOT / 'package.json').read_text(encoding='utf8'))
        peers = package['peerDependencies']
        metadata = package.get('peerDependenciesMeta', {})
        for name in peers:
            with self.subTest(peer=name):
                self.assertTrue(metadata.get(name, {}).get('optional'),
                                f'{name} 由 DSH 宿主提供，空环境不应自动下载另一套宿主')

    def test_compiled_client_externals_are_declared_as_host_peers(self):
        package = json.loads((ROOT / 'package.json').read_text(encoding='utf8'))
        compiled = (ROOT / 'lib/client.js').read_text(encoding='utf8')
        for name in re.findall(r'require\(["\']([^"\']+)["\']\)', compiled):
            root = '/'.join(name.split('/')[:2]) if name.startswith('@') else name.split('/')[0]
            self.assertIn(root, package['peerDependencies'])


if __name__ == '__main__':
    unittest.main()
