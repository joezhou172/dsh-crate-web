"""随包适配器的授权、会话语义及清理错误保留；不启动桌面。"""
from pathlib import Path
import json
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'core'))
from dsh_pack.desktop_verify import DesktopVerifyAdapter
from dsh_pack.verify import _cleanup_status, VerifyOptions, VerifyStep, verify_profile


class BundledVerifyTests(unittest.TestCase):
    def test_real_core_zero_model_flow_cannot_start_a_second_verifier(self):
        # Core intentionally keeps independent checks after an untested model step.
        # Exercise that real dispatch order, rather than assuming it stops there.
        with tempfile.TemporaryDirectory() as path:
            adapter = object.__new__(DesktopVerifyAdapter)
            adapter.config = {'maximumBoots': 1}
            adapter.generation = 0
            adapter.process = None
            adapter.directory = Path(path)
            operations = []
            def started(context):
                adapter.process = object()
            def rpc(operation, *args):
                operations.append(operation)
                if operation == 'boot':
                    adapter.generation += 1
                return {'exitCode': 0}
            adapter._start = Mock(side_effect=started)
            adapter._rpc = Mock(side_effect=rpc)
            adapter._surface = Mock(return_value={'verified': True})
            adapter._new_session = Mock(return_value={'selectedAfter': ['isolated-session']})
            adapter.close = Mock(return_value={'processExited': True, 'portApplicable': False,
                                              'endpointsApplicable': False})
            options = VerifyOptions(dsh_home=Path(path), profile_name='desktop', mode='web',
                                    current_environment={}, available_secret_names=frozenset(), adapter=adapter)
            with patch('dsh_pack.verify._composition_step', return_value=VerifyStep('composition', 'PASS', 'fixture composition')):
                result = verify_profile(options)
            steps = {step.name: step for step in result.steps}
            self.assertEqual(steps['basic_response'].status, 'UNTESTED')
            self.assertEqual(steps['restart'].status, 'UNTESTED')
            self.assertEqual(steps['restart'].evidence['reason'], 'desktop-start-budget-exhausted')
            self.assertEqual(steps['restart_surface_ready'].evidence['blockedBy'], 'restart')
            self.assertEqual(steps['cleanup'].status, 'PASS')
            self.assertEqual(result.status, 'UNTESTED')
            self.assertEqual(operations, ['boot'])
            self.assertEqual(adapter.generation, 1)
            adapter.close.assert_called_once()

    def test_boot_limit_is_checked_before_any_controller_request(self):
        adapter = object.__new__(DesktopVerifyAdapter)
        adapter.config = {'maximumBoots': 1}
        adapter.generation = 1
        adapter.process = object()
        adapter._rpc = Mock(side_effect=AssertionError('budget must be checked first'))
        result = adapter.run_step('boot', None)
        self.assertEqual(result.status, 'UNTESTED')
        self.assertEqual(result.evidence['reason'], 'desktop-start-budget-exhausted')
        adapter._rpc.assert_not_called()

    def test_explicit_two_boot_config_keeps_planned_restart(self):
        adapter = object.__new__(DesktopVerifyAdapter)
        adapter.config = {'maximumBoots': 2}
        adapter.generation = 1
        adapter._rpc = Mock(side_effect=[{'exitCode': 0}, {'generation': 2}])
        adapter._surface = Mock(return_value={'verified': True})
        result = adapter.run_step('restart', None)
        self.assertEqual(result.status, 'PASS')
        self.assertEqual([call.args[0] for call in adapter._rpc.call_args_list], ['close', 'boot'])

    def test_zero_budget_does_not_touch_runtime(self):
        adapter = object.__new__(DesktopVerifyAdapter)
        adapter._rpc = Mock(side_effect=AssertionError('must not execute'))
        for name in ['basic_response', 'core_tool']:
            result = adapter.run_step(name, None)
            self.assertEqual(result.status, 'UNTESTED')
            self.assertEqual(result.evidence['modelRequests'], 0)
        adapter._rpc.assert_not_called()

    def test_paid_or_retry_config_rejected_before_process_creation(self):
        # 仅选择被测模块的 Windows 校验分支；不修改全局平台，也不调用原生 API。
        with patch('dsh_pack.desktop_verify.os', SimpleNamespace(name='nt')):
            for config in [dict(modelRequests=1, automaticRetries=0), dict(modelRequests=0, automaticRetries=1)]:
                with self.assertRaisesRegex(ValueError, 'zero model'):
                    DesktopVerifyAdapter({'mode': 'web', **config})

    def test_boot_cap_rejected(self):
        with patch('dsh_pack.desktop_verify.os', SimpleNamespace(name='nt')):
            for value in [0, 3, True]:
                with self.assertRaisesRegex(ValueError, 'maximumBoots'):
                    DesktopVerifyAdapter(dict(mode='web', modelRequests=0, automaticRetries=0, maximumBoots=value))

    def test_blank_session_reuse_is_real_official_semantics(self):
        from compression import zstd
        with tempfile.TemporaryDirectory() as path:
            root = Path(path)
            home = root/'home'
            documents = root/'documents'
            documents.mkdir()
            session = home/'sessions/day/sid/session.v4.jsonl.zstd'
            session.parent.mkdir(parents=True)
            session.write_bytes(zstd.compress(json.dumps({'type': 'session', 'version': 4, 'id': 'sid', 'cwd': str(documents)}).encode() + b'\n'))
            (home/'storages').mkdir()
            (home/'storages/workspace.json').write_text(json.dumps({'tables': {'workspaces': {'wid': {'path': str(documents), 'sessionIds': ['sid']}}}}))
            adapter = object.__new__(DesktopVerifyAdapter)
            adapter.child_home = home
            adapter.directory = root
            adapter._rpc = Mock(return_value={'officialButtonClicks': 1, 'selectedBefore': ['sid'], 'selectedAfter': ['sid']})
            result = adapter._new_session()
            self.assertEqual(result['mode'], 'reused-existing-blank')
            self.assertEqual(result['workspaceId'], 'wid')
            self.assertEqual(result['newFiles'], 0)
            adapter._rpc.assert_called_once_with('new_session')

    def test_close_retains_original_close_error_and_foreign_port_owner(self):
        import threading
        with tempfile.TemporaryDirectory() as path:
            adapter = object.__new__(DesktopVerifyAdapter)
            adapter.closed = None
            adapter.directory = Path(path)
            adapter.process = Mock(returncode=0)
            adapter.job = Mock()
            adapter.job.active_processes.return_value = {'activeProcesses': 0}
            adapter._rpc = Mock(side_effect=RuntimeError('ORIGINAL_CLOSE_ERROR'))
            adapter.stop = threading.Event()
            adapter.sampler = Mock()
            adapter.lock = threading.RLock()
            adapter.counter = Mock()
            adapter.counter.process.return_value = {'pid': 11, 'exited': True, 'exitCode': 0}
            adapter.owned = {11: (123, 'owned.exe', 'desktop')}
            adapter.endpoints = {'web': 100}
            adapter.rows = []
            adapter.events = []
            adapter.observation_errors = []
            adapter.error_log = Mock()
            with patch('dsh_pack.desktop_verify.tcp_rows', return_value=[{'localPort': 100, 'state': 'LISTEN', 'pid': 999}]):
                result = adapter.close()
            self.assertEqual(_cleanup_status(result), 'FAIL')
            self.assertEqual(result['errors'][0]['message'], 'ORIGINAL_CLOSE_ERROR')
            self.assertFalse(result['portReleased'])
            self.assertEqual(result['endpoints'][0]['foreignOwnerRows'][0]['pid'], 999)
            adapter.job.close.assert_called_once()
            self.assertIs(adapter.close(), result)

    def test_bundled_child_python_is_owned_but_foreign_image_is_rejected(self):
        import threading
        adapter = object.__new__(DesktopVerifyAdapter)
        adapter.config = {'desktopExecutable': str(Path('C:/isolated/runtime/app.exe'))}
        adapter.child_home = Path('C:/isolated/job/home')
        adapter.owned = {}
        adapter.lock = threading.RLock()
        adapter.counter = Mock()
        image = adapter.child_home/'profiles/desktop/node_modules/dsh-crate-web/runtime/python/python.exe'
        adapter.counter.open.return_value = (123, str(image))
        adapter._bind(11, 'bundled-core')
        self.assertIn(11, adapter.owned)
        adapter.counter.open.return_value = (456, 'C:/foreign/outside.exe')
        with self.assertRaisesRegex(ValueError, 'pid=12, image='):
            adapter._bind(12, 'foreign')
        adapter.counter.k.CloseHandle.assert_called_once_with(456)


if __name__ == '__main__':
    unittest.main()
