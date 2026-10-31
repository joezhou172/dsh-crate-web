"""桌面未安装系统 npm 时，复用显式随包 pnpm；不启动桌面或调用模型。"""
from pathlib import Path
import io
import json
import os
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'core'))
from dsh_pack import export
from dsh_pack.errors import ExportError
from dsh_pack.user_cli import _invoke_core


class DesktopExportTests(unittest.TestCase):
    def test_no_system_npm_selects_explicit_host_argv(self):
        argv = ['desktop.exe', '--expose-internals', 'pnpm.cjs']
        with patch.dict(os.environ, {'DSH_PACK_PNPM_COMMAND': json.dumps(argv)}, clear=True), patch.object(export.shutil, 'which', return_value=None):
            self.assertEqual(export._npm_command(None), tuple(argv))

    def test_existing_or_configured_npm_keeps_precedence(self):
        with patch.dict(os.environ, {'DSH_PACK_PNPM_COMMAND': '["host.exe"]'}, clear=True), patch.object(export.shutil, 'which', return_value='npm-from-path'):
            self.assertEqual(export._npm_command(None), 'npm-from-path')
            self.assertEqual(export._npm_command('explicit-npm'), 'explicit-npm')

    def test_invalid_host_argv_is_actionable(self):
        for value in ['oops', '[]', '[""]', '[4]', '["x\\u0000y"]']:
            with self.subTest(value=value), patch.dict(os.environ, {'DSH_PACK_PNPM_COMMAND': value}, clear=True), patch.object(export.shutil, 'which', return_value=None):
                with self.assertRaises(ExportError) as caught:
                    export._npm_command(None)
                self.assertEqual(caught.exception.as_dict()['code'], 'EXPORT_PACK_COMMAND_INVALID')

    def test_missing_executable_keeps_native_error_and_stage(self):
        with tempfile.TemporaryDirectory() as path, patch.object(export.subprocess, 'run', side_effect=FileNotFoundError(2, 'fixture missing executable')):
            with self.assertRaises(ExportError) as caught:
                export._npm_pack(Path(path), 'fixture', 'missing-npm')
            error = caught.exception.as_dict()
            self.assertEqual(error['stage'], 'package-artifact')
            self.assertEqual(error['code'], 'EXPORT_PACK_START_FAILED')
            self.assertEqual(error['details']['command'][0], 'missing-npm')
            self.assertIn('fixture missing executable', error['details']['originalError'])

    def test_user_cli_retains_structured_export_error(self):
        error = ExportError('native failure', stage='package-artifact', code='EXPORT_PACK_START_FAILED',
                            details={'command': ['missing-npm'], 'originalError': '[WinError 2]'})
        with patch('dsh_pack.cli.export_profile', side_effect=error):
            code, result = _invoke_core(['export', '--profile', 'fixture', '--output', 'fixture.dshcrate'])
        self.assertEqual(code, 2)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['error'], error.as_dict())

    def test_failed_npm_is_not_retried_with_another_tool(self):
        result = type('Result', (), {'returncode': 7, 'stderr': 'native pack failure', 'stdout': ''})()
        with tempfile.TemporaryDirectory() as path, patch.object(export.subprocess, 'run', return_value=result) as run:
            with self.assertRaises(ExportError) as caught:
                export._npm_pack(Path(path), 'fixture', 'selected-npm')
            run.assert_called_once()
            self.assertEqual(caught.exception.as_dict()['details']['exitCode'], 7)
            self.assertEqual(caught.exception.as_dict()['details']['stderr'], 'native pack failure')

    def test_pnpm_does_not_silently_remove_manifest_fields(self):
        with tempfile.TemporaryDirectory() as path:
            root = Path(path)
            original = b'{"name":"fixture","version":"1.0.0","pnpm":{"overrides":{"x":"1"}}}'
            (root / 'package.json').write_bytes(original)
            def packed(command, **kwargs):
                self.assertEqual(kwargs['cwd'], root)
                self.assertEqual(kwargs['env']['ELECTRON_RUN_AS_NODE'], '1')
                self.assertIn('--config.ignore-scripts=true', command)
                self.assertIn('--config.ignore-pnpmfile=true', command)
                self.assertIn('--config.pm-on-fail=ignore', command)
                destination = Path(command[command.index('--pack-destination') + 1])
                with tarfile.open(destination / 'fixture.tgz', 'w:gz') as tar:
                    for name, data in [('package/package.json', b'{"name":"fixture","version":"1.0.0"}'), ('package/cordis.patch.yml', b'[]')]:
                        member = tarfile.TarInfo(name); member.size = len(data)
                        tar.addfile(member, io.BytesIO(data))
                return type('Result', (), {'returncode': 0})()
            with patch.object(export.subprocess, 'run', side_effect=packed):
                content = export._npm_pack(root, 'fixture', ('host.exe', 'pnpm.cjs'), required_file='cordis.patch.yml')
            with tarfile.open(fileobj=io.BytesIO(content), mode='r:gz') as tar:
                self.assertEqual(tar.extractfile('package/package.json').read(), original)
                self.assertEqual(tar.extractfile('package/cordis.patch.yml').read(), b'[]')


if __name__ == '__main__':
    unittest.main()
