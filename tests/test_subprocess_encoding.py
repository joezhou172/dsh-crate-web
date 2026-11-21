"""中文 Windows 默认 GBK 下，实际子进程 UTF-8 输出不能丢失或杀死读线程。"""
import importlib
import json
import subprocess
import sys
import tempfile
import threading
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'core'))
export = importlib.import_module('dsh_pack.export')
importer = importlib.import_module('dsh_pack.importer')
verify = importlib.import_module('dsh_pack.verify')
from dsh_pack.pack import PackData
from dsh_pack.errors import PackImportError

OUT = '✅ 中文路径、安装输出 ®\n'
ERR = '✅ 中文错误、完整诊断 ®\n'
REAL_RUN = subprocess.run


class SubprocessEncodingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='crate-encoding-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.profile = self.root / 'profile'
        self.profile.mkdir()
        (self.profile / 'package.json').write_text('{"name":"fixture","private":true}', encoding='utf-8')
        self.context = verify.VerifyContext(self.root, 'profile', self.profile, 'headless', {}, frozenset(), self.root / 'metadata.json', {})

    @contextmanager
    def command_output(self, out=OUT.encode(), err=ERR.encode(), code=17):
        """替换外部业务命令，保留真实 subprocess 管道和调用方解码参数。"""
        errors = []
        script = 'import os,sys;os.write(1,bytes.fromhex(sys.argv[1]));os.write(2,bytes.fromhex(sys.argv[2]));sys.exit(int(sys.argv[3]))'
        def launch(command, **kwargs):
            return REAL_RUN([sys.executable, '-c', script, out.hex(), err.hex(), str(code)], **kwargs)
        with patch('subprocess._text_encoding', return_value='gbk'), patch('threading.excepthook', side_effect=lambda event: errors.append(event.exc_value)), patch('subprocess.run', side_effect=launch):
            yield
        self.assertEqual(errors, [], '子进程读取线程发生异常')

    def assert_diagnostic(self, value, stripped=False):
        self.assertEqual(value['exitCode'], 17)
        self.assertEqual(value['stdout'], OUT.strip() if stripped else OUT)
        self.assertEqual(value['stderr'], ERR.strip() if stripped else ERR)

    def test_export_preserves_exit_and_utf8_diagnostic(self):
        with self.command_output(), self.assertRaises(export.ExportError) as raised:
            export._npm_pack(self.profile, 'fixture', (sys.executable,))
        self.assertEqual(raised.exception.code, 'EXPORT_PACK_FAILED')
        self.assert_diagnostic(raised.exception.details)

    def test_network_import_preserves_exit_and_utf8_diagnostic(self):
        row = {'name':'fixture','requested':{'sourceType':'registry','specifier':'1.0.0'},'runtime':{'version':'1.0.0'}}
        with self.command_output(), self.assertRaises(PackImportError) as raised:
            importer._install_network_reference(self.profile, row, importer.ImportOptions(npm_command=sys.executable))
        self.assert_diagnostic(raised.exception.details, stripped=True)

    def test_pnpm_rebuild_preserves_exit_and_utf8_diagnostic(self):
        data = PackData({}, {'package.json':b'{"name":"fixture","private":true}'}, {'plugins':[]}, {})
        with patch.object(importer, '_host_dependency_overrides', return_value=({}, [])), self.command_output(), self.assertRaises(PackImportError) as raised:
            importer._pnpm_rebuild(self.profile, data, [], importer.ImportOptions(pnpm_command=(sys.executable,)))
        self.assertEqual(raised.exception.code, 'PACKAGE_MANAGER_FAILED')
        self.assert_diagnostic(raised.exception.details, stripped=True)

    def test_patch_adapter_reads_utf8_json(self):
        payload = json.dumps({'changed':False,'reason':OUT}, ensure_ascii=False).encode()
        with self.command_output(payload, b'', 0):
            result = importer._adapt_profile_patch(self.profile, importer.ImportOptions(patch_adapter_command=(sys.executable,)))
        self.assertEqual(result['reason'], OUT)

    def test_patch_adapter_rejects_invalid_utf8_without_reader_crash(self):
        with self.command_output(b'{"changed":false,"reason":"\xae"}', b'detail\xae\n', 0), self.assertRaises(PackImportError) as raised:
            importer._adapt_profile_patch(self.profile, importer.ImportOptions(patch_adapter_command=(sys.executable,)))
        self.assertEqual(raised.exception.code, 'PROFILE_PATCH_ADAPTATION_FAILED')
        self.assertIn('\\xae', raised.exception.details['stderr'])

    def test_verify_headless_probe_and_plugin_preserve_utf8(self):
        adapter = verify.SubprocessVerifyAdapter({'mode':'headless','command':['fixture'], 'probes':{'core_tool':['fixture']},'pluginTests':{'fixture':{'smoke':['fixture']}}})
        for call in [lambda:adapter._run_headless(self.context), lambda:adapter._probe('core_tool',self.context), lambda:adapter.run_plugin_test('fixture','smoke',self.context)]:
            with self.subTest(call=call), self.command_output():
                result = call()
                self.assertEqual(result.status, 'FAIL')
                self.assert_diagnostic(result.evidence)

    def test_verify_log_invalid_bytes_remain_visible(self):
        adapter = verify.SubprocessVerifyAdapter({'mode':'headless','command':['fixture']})
        with self.command_output(b'legacy\xae\n', b'error\xff\n'):
            result = adapter._run_headless(self.context)
        self.assertEqual(result.evidence['stdout'], 'legacy\\xae\n')
        self.assertEqual(result.evidence['stderr'], 'error\\xff\n')
        self.assertEqual(result.evidence['exitCode'], 17)

    def test_web_stream_does_not_lose_unicode_ready_output(self):
        script = self.root / 'web.py'
        script.write_text('import os,time\nos.write(1,'+repr(OUT.encode()+b'dsh web: http://127.0.0.1:12345\n')+')\nos.write(2,'+repr(ERR.encode())+')\ntime.sleep(1)\n',encoding='utf-8')
        adapter = verify.SubprocessVerifyAdapter({'mode':'web','command':[sys.executable,str(script)],'timeoutSeconds':2})
        errors=[]
        try:
            with patch('subprocess._text_encoding',return_value='gbk'), patch('threading.excepthook',side_effect=lambda event:errors.append(event.exc_value)):
                result=adapter._spawn_web(self.context)
                adapter.process.wait(timeout=5)
                for thread in adapter._threads:thread.join(timeout=2)
            self.assertEqual(errors,[])
            self.assertEqual(result.status,'PASS')
            self.assertEqual(adapter._logs_evidence()['stdout'],OUT+'dsh web: http://127.0.0.1:12345\n')
            self.assertEqual(adapter._logs_evidence()['stderr'],ERR)
        finally:adapter.close()

    @unittest.skipUnless(sys.platform=='win32','Windows netstat 输出解析')
    def test_netstat_ascii_rows_survive_localized_header(self):
        data='活动连接\n'.encode('gbk')+b'  TCP  127.0.0.1:12345  0.0.0.0:0  LISTENING  4242\r\n'
        with self.command_output(data,b'',0):
            result=verify.SubprocessVerifyAdapter._port_owner_for('http://127.0.0.1:12345',4242)
        self.assertTrue(result['portBelongsToProcess'])


if __name__=='__main__':unittest.main()
