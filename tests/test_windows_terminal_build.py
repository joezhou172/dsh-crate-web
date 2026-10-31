"""终端宿主修复：精确 diff、路径和完整性边界；不启动桌面。"""
from pathlib import Path
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'packaging/windows-terminal'
spec = importlib.util.spec_from_file_location('windows_terminal_build', ASSETS / 'build.py')
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


class BuildContract(unittest.TestCase):
    @unittest.skipUnless(os.name == 'nt', 'Windows x64 新隔离目录权限夹具')
    def test_owned_directory_is_exclusive_and_scoped(self):
        from windows_terminal_directory import prepare_directory, OWNER_ACCESS
        with tempfile.TemporaryDirectory() as tmp:
            scope = Path(tmp)
            result = prepare_directory(scope / 'new', scope)
            self.assertEqual(result['ownerOnlyMask'], hex(OWNER_ACCESS))
            self.assertFalse(result['otherPrincipalsGranted'])
            with self.assertRaises(ValueError):
                prepare_directory(scope / 'new', scope)
            with self.assertRaises(ValueError):
                prepare_directory(scope.parent / 'escaped', scope)

    def test_exact_patch_and_context_rejection(self):
        patch = '--- a/test\n+++ b/test\n@@ -1,2 +1,2 @@\n a\n-b\n+c\n'
        self.assertEqual(build.apply_patch('a\nb\n', patch), 'a\nc\n')
        with self.assertRaisesRegex(ValueError, '上下文'):
            build.apply_patch('a\nwrong\n', patch)
        with self.assertRaises(ValueError):
            build.apply_patch('a\nb\n', patch.replace('-1,2', '-1,3'))

    def test_resource_paths(self):
        for name in ['/escape', '../escape', 'a/../b', 'a\\b', 'C:/escape', 'a//b', '.', '']:
            with self.subTest(name=name), self.assertRaises(ValueError):
                build.safe_name(name)
        self.assertEqual(build.safe_name('node_modules/pkg/index.js'), 'node_modules/pkg/index.js')

    def test_manifest_patch_hashes(self):
        manifest = json.loads((ASSETS / 'manifest.json').read_text('utf8'))
        self.assertEqual(len(manifest['patches']), 5)
        for row in manifest['patches']:
            patch = (ASSETS / row['patch']).read_bytes()
            self.assertEqual(build.digest(patch), row['patchSha256'])
            self.assertNotIn(b'CRATE_TERMINAL_DIAG_TRACE', patch)
        self.assertNotIn('sourceDirectory', manifest)

    def test_existing_and_nested_destinations_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'source'
            source.mkdir()
            for destination in [source, source / 'nested', Path(tmp)]:
                with self.subTest(destination=str(destination)), self.assertRaises(ValueError):
                    build.materialize(source, destination)

    def test_integrity_changes_only_expected_resource(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / 'fixture.exe'
            old, new = 'a' * 64, 'b' * 64
            exe.write_bytes(b'PREFIX' + old.encode() + b'SUFFIX')
            data = {'resourceOffset': 6, 'resourceBytes': 64, 'oldHeaderSha256': old}
            build.patch_integrity(exe, data, new)
            self.assertEqual(exe.read_bytes(), b'PREFIX' + new.encode() + b'SUFFIX')
            with self.assertRaises(ValueError):
                build.patch_integrity(exe, data, new)

    @unittest.skipUnless(os.environ.get('DSH_CRATE_TEST_DESKTOP'), '需要指定本地精确桌面输入；CI 不携带官方二进制')
    def test_actual_official_modules_and_event_regression(self):
        desktop = Path(os.environ['DSH_CRATE_TEST_DESKTOP'])
        manifest = json.loads((ASSETS / 'manifest.json').read_text('utf8'))
        self.assertEqual(build.file_hash(desktop / 'DeepSeek Harness.exe'), manifest['inputExeSha256'])
        reader = build.Asar(desktop / 'resources/app.asar')
        try:
            changed = build.patched_modules(reader, manifest)
            names = ['windowsTerminal.js', 'terminal.js', 'eventEmitter2.js']
            modules = {n: reader.read('dsh/node_modules/node-pty/lib/' + n).decode() for n in names}
            fixture = {'original': modules, 'fixedTerminal': changed['dsh/node_modules/node-pty/lib/windowsTerminal.js'].decode(),
                       'subprocess': changed['dsh/node_modules/@deepseek-ai/dsh-subprocess-local/lib/index.js'].decode(),
                       'bash': changed['dsh/node_modules/@deepseek-ai/dsh-terminal-bash/lib/index.js'].decode()}
        finally:
            reader.close()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'modules.json'
            path.write_text(json.dumps(fixture), 'utf8')
            node = os.environ.get('DSH_CRATE_TEST_NODE') or shutil.which('node')
            self.assertIsNotNone(node)
            result = subprocess.run([node, str(ROOT / 'tests/windows_terminal_events.cjs'), str(path)], capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['cases'], 14)


if __name__ == '__main__':
    unittest.main()
