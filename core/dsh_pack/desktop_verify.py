"""随包独立桌面执行器。Core保留步骤顺序、required约束及最终状态裁决。"""
from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import re
import subprocess
import threading
import time
import uuid

from .verify import VerifyStep
from .windows_verify import OwnedJob, WindowsCounters, process_tree, summarize_resources, tcp_rows


def _write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


class DesktopVerifyAdapter:
    """Only controls processes created by its own stdio controller and Windows Job."""

    def __init__(self, config):
        if os.name != 'nt' or config.get('mode') != 'web':
            raise ValueError('Bundled desktop Verify supports Windows web mode only')
        if config.get('modelRequests') != 0 or config.get('automaticRetries') != 0:
            raise ValueError('Bundled desktop Verify requires zero model requests and zero retries')
        maximum = config.get('maximumBoots')
        if type(maximum) is not int or not 1 <= maximum <= 2:
            raise ValueError('maximumBoots must be 1 or 2')
        self.config = dict(config)
        for name in ['desktopExecutable', 'controllerScript']:
            path = Path(config[name])
            if not path.is_absolute() or not path.is_file() or path.is_symlink() or path.is_junction():
                raise ValueError(f'{name} must be an absolute regular file')
        self.process = None
        self.job = None
        self.directory = None
        self.owned = {}
        self.endpoints = {}
        self.events = []
        self.rows = []
        self.observation_errors = []
        self.stop = threading.Event()
        self.lock = threading.RLock()
        self.responses = queue.Queue()
        self.closed = None
        self.generation = 0
        self.counter = WindowsCounters()

    def _bind(self, pid, role):
        with self.lock:
            if pid in self.owned:
                return
            handle, image = self.counter.open(pid)
            executable = Path(image)
            bundled_python = getattr(self, 'child_home', Path(self.config['desktopExecutable']).parent)/'profiles/desktop/node_modules/dsh-crate-web/runtime/python/python.exe'
            if not executable.is_relative_to(Path(self.config['desktopExecutable']).parent) and executable != bundled_python:
                self.counter.k.CloseHandle(handle)
                raise ValueError(f'Verify child executable escaped its declared runtime: pid={pid}, image={image}')
            self.owned[pid] = (handle, image, role)

    def _event(self, value):
        self.events.append(value)
        if value.get('event') == 'desktop.spawned':
            self.generation = value['generation']
            self.root_pid = value['pid']
            self.child_home = Path(value['home'])
            self._bind(self.root_pid, 'desktop')
            self.endpoints.update({f'cdp-{self.generation}': value['cdpPort'], f'inspector-{self.generation}': value['inspectorPort']})

    def _read(self):
        try:
            for line in self.process.stdout:
                value = json.loads(line)
                if 'event' in value:
                    self._event(value)
                else:
                    self.responses.put(value)
        except Exception as error:
            self.responses.put({'error': {'type': type(error).__name__, 'message': str(error)}})
        finally:
            self.responses.put({'error': {'type': 'EOF', 'message': 'Desktop controller pipe closed'}})

    def _rpc(self, operation, timeout=65):
        if not self.process or self.process.poll() is not None:
            raise RuntimeError('Desktop controller is not running')
        self.process.stdin.write(json.dumps({'operation': operation}) + '\n')
        self.process.stdin.flush()
        try:
            result = self.responses.get(timeout=timeout)
        except queue.Empty:
            raise TimeoutError('Desktop controller deadline: ' + operation) from None
        if 'error' in result:
            error = result['error']
            raise RuntimeError(f"{error['type']}: {error['message']}")
        return result['value']

    def _sample(self):
        while not self.stop.is_set():
            try:
                # Only the known controller's descendants are observed. Nothing is killed here.
                for pid in process_tree(self.process.pid):
                    try:
                        self._bind(pid, 'controller' if pid == self.process.pid else 'desktop-descendant')
                    except OSError as error:
                        if getattr(error, 'winerror', None) not in (87, 6) and error.errno not in (87, 6):
                            raise
                    except ValueError as error:
                        item = {'type': type(error).__name__, 'message': str(error)}
                        if item not in self.observation_errors:
                            self.observation_errors.append(item)
                with self.lock:
                    processes = [self.counter.process(pid, h, role, image) for pid, (h, image, role) in self.owned.items()]
                row = {'atUtc': time.time(), 'monotonicNs': time.monotonic_ns(), 'system': self.counter.system(), 'processes': processes}
                self.rows.append(row)
                with (self.directory/'resources.jsonl').open('a', encoding='utf-8') as stream:
                    stream.write(json.dumps(row) + '\n')
            except Exception as error:
                self.observation_errors.append({'type': type(error).__name__, 'message': str(error)})
            self.stop.wait(.2)

    def _start(self, context):
        parent = context.dsh_home/'.dsh-pack/verify-jobs'
        parent.mkdir(parents=True, exist_ok=True)
        if parent.is_symlink() or parent.is_junction():
            raise ValueError('Verify jobs directory is a reparse link')
        self.directory = parent/uuid.uuid4().hex
        self.directory.mkdir()
        config = {**self.config, 'sourceHome': str(context.dsh_home), 'sourceProfile': context.profile_name,
                  'job': str(self.directory), 'observe': True}
        _write(self.directory/'controller-config.json', config)
        env = {k: v for k, v in os.environ.items() if not re.search(r'secret|token|password|credential|authorization|api.?key|^(NODE_|ELECTRON_|PYTHONPATH$|PYTHONHOME$)', k, re.I)}
        env['ELECTRON_RUN_AS_NODE'] = '1'
        self.job = OwnedJob()
        self.error_log = (self.directory/'controller.stderr.log').open('x', encoding='utf-8')
        self.process = subprocess.Popen([config['desktopExecutable'], config['controllerScript'], str(self.directory/'controller-config.json')],
            cwd=self.directory, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.error_log,
            text=True, encoding='utf-8', creationflags=subprocess.CREATE_NO_WINDOW)
        # Controller waits for stdin; no desktop can be created before assignment succeeds.
        try:
            self.job.assign(self.process)
        except Exception:
            self.process.stdin.close()
            self.process.wait(timeout=10)
            raise
        self._bind(self.process.pid, 'controller')
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()
        self.sampler = threading.Thread(target=self._sample, daemon=True)
        self.sampler.start()

    def _surface(self):
        value = self._rpc('surface')
        self.endpoints[f'web-{self.generation}'] = value['webPort']
        table = tcp_rows()
        with self.lock:
            pids = set(self.owned)
        # Snapshot after discovering the listeners, before granting ready.
        pids.update(process_tree(self.process.pid))
        evidence = []
        for name, port in self.endpoints.items():
            if not name.endswith('-' + str(self.generation)):
                continue
            listeners = [row for row in table if row['localPort'] == port and row['state'] == 'LISTEN']
            if not listeners or not all(row['pid'] in pids for row in listeners):
                raise RuntimeError('Owned endpoint listener not confirmed: ' + name)
            for row in listeners:
                self._bind(row['pid'], 'endpoint-owner')
            if name.startswith('web-') and not any(row['pid'] == value['runtimePid'] for row in listeners):
                raise RuntimeError('Authenticated backend PID does not own its Web listener')
            evidence.append({'name': name, 'port': port, 'listeners': listeners})
        return {**value, 'endpoints': evidence}

    def _new_session(self):
        directory = self.child_home/'sessions'
        before = set(directory.rglob('*.zstd')) if directory.exists() else set()
        action = self._rpc('new_session')
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            paths = set(directory.rglob('*.zstd')) if directory.exists() else set()
            added = paths - before
            selected = action['selectedAfter'][0]
            for path in sorted(p for p in paths if p.parent.name == selected):
                try:
                    from compression import zstd
                    text = zstd.decompress(path.read_bytes()).decode('utf-8')
                    lines = [json.loads(line) for line in text.splitlines() if line.strip()]
                except (OSError, ValueError, EOFError):
                    continue  # A bounded wait for the one requested write; no second click.
                header = next((row for row in lines if row.get('type') == 'session'), None)
                if not header:
                    continue
                cwd = header.get('cwd')
                if not cwd or not Path(cwd).resolve().is_relative_to((self.directory/'documents').resolve()):
                    raise RuntimeError('New session workspace escaped Verify isolation')
                if header.get('id') != selected or any(row.get('type') == 'turn/start' for row in lines):
                    raise RuntimeError('New session identity or zero-model boundary mismatch')
                workspace = json.loads((self.child_home/'storages/workspace.json').read_text('utf-8'))
                matches = [(key, row) for key, row in workspace['tables']['workspaces'].items() if selected in row['sessionIds']]
                if len(matches) != 1 or Path(matches[0][1]['path']).resolve() != Path(cwd).resolve():
                    raise RuntimeError('Selected session does not belong to its persisted workspace')
                return {**action, 'persistedSession': str(path), 'header': header, 'newFiles': len(added),
                        'mode': 'created-new-session' if path in added else 'reused-existing-blank', 'workspaceId': matches[0][0]}
            time.sleep(.15)
        raise TimeoutError('Official New session action did not persist an isolated session')

    def run_step(self, name, context):
        evidence = {'modelRequests': 0, 'automaticRetries': 0}
        if name in ('boot', 'restart') and self.generation >= self.config['maximumBoots']:
            return VerifyStep(name, 'UNTESTED', '桌面启动额度已用完；未关闭当前实例或请求额外启动',
                              evidence={**evidence, 'reason': 'desktop-start-budget-exhausted',
                                        'maximumBoots': self.config['maximumBoots'],
                                        'observedBoots': self.generation})
        if name == 'boot':
            if self.process is None:
                self._start(context)
            value = self._rpc('boot')
            evidence.update(value)
            evidence['jobDirectory'] = str(self.directory)
            evidence['surface'] = self._surface()
        elif name in ('surface_ready', 'restart_surface_ready'):
            evidence.update(self._surface())
        elif name == 'new_session':
            evidence.update(self._new_session())
        elif name in ('basic_response', 'core_tool'):
            return VerifyStep(name, 'UNTESTED', '模型调用预算为0；未请求模型或依赖模型的工具', evidence=evidence)
        elif name == 'restart':
            evidence['closedGeneration'] = self._rpc('close', 30)
            evidence['newGeneration'] = self._rpc('boot')
            evidence['surface'] = self._surface()
        else:
            return VerifyStep(name, 'UNTESTED', '随包运行器未实现该能力', evidence=evidence)
        return VerifyStep(name, 'PASS', '独立桌面真实动作及所属资源已核查', evidence=evidence)

    def run_plugin_test(self, plugin, test_name, context):
        return VerifyStep(f'{plugin}:{test_name}', 'UNTESTED', '插件专用能力尚未由随包运行器实际执行',
                          evidence={'plugin': plugin, 'test': test_name, 'modelRequests': 0})

    def close(self):
        if self.closed is not None:
            return self.closed
        if self.process is None:
            self.closed = {'processExited': True, 'portApplicable': False, 'endpointsApplicable': False,
                           'reason': 'adapter did not create a process'}
            if self.job:
                self.job.close()
            return self.closed
        errors = []
        close = None
        try:
            close = self._rpc('close', 35)
        except Exception as error:
            errors.append({'stage': 'desktop-close', 'type': type(error).__name__, 'message': str(error)})
        try:
            self.process.stdin.close()
            self.process.wait(timeout=10)
        except Exception as error:
            errors.append({'stage': 'controller-close', 'type': type(error).__name__, 'message': str(error)})
        # Give already-exiting descendants a bounded passive tail before fallback.
        deadline = time.monotonic() + 3
        accounting = self.job.active_processes()
        while accounting['activeProcesses'] and time.monotonic() < deadline:
            time.sleep(.1)
            accounting = self.job.active_processes()
        forced = accounting['activeProcesses'] != 0
        if forced:
            errors.append({'stage': 'owned-job', 'message': 'Owned descendants remained; closed KILL_ON_JOB_CLOSE job', 'before': accounting})
        self.job.close()
        if forced:
            self.process.wait(timeout=5)
        self.stop.set()
        self.sampler.join(timeout=5)
        with self.lock:
            processes = [self.counter.process(pid, h, role, image) for pid, (h, image, role) in self.owned.items()]
        table = tcp_rows()
        active_states = {'LISTEN', 'ESTABLISHED', 'SYN_SENT', 'SYN_RCVD', 'CLOSE_WAIT'}
        pids = set(self.owned)
        endpoints = []
        for name, port in self.endpoints.items():
            remaining = [row for row in table if row['localPort'] == port and row['state'] in active_states]
            endpoints.append({'name': name, 'port': port, 'checked': True, 'released': not remaining, 'remaining': remaining,
                              'foreignOwnerRows': [row for row in remaining if row['pid'] not in pids],
                              'method': 'passive IPv4+IPv6 TCP owner table; no connection probes'})
        process_exited = all(row['exited'] for row in processes) and accounting['activeProcesses'] == 0
        unexpected_exit = [row for row in processes if row['exited'] and row['exitCode'] != 0]
        if unexpected_exit:
            errors.append({'stage': 'process-exit', 'message': 'Observed owned processes exited nonzero', 'processes': unexpected_exit})
        self.closed = {'processExited': process_exited, 'processes': processes, 'jobAccountingBeforeClose': accounting,
            'portApplicable': bool(endpoints), 'portReleased': all(row['released'] for row in endpoints),
            'portEvidence': {'checked': True, 'method': 'GetExtendedTcpTable IPv4+IPv6'},
            'endpointsApplicable': bool(endpoints), 'endpoints': endpoints, 'errors': errors,
            'normalClose': 'PASS' if not errors and close and close['exitCode'] == 0 and self.process.returncode == 0 and process_exited else 'FAIL',
            'desktopClose': close, 'controllerExitCode': self.process.returncode, 'forcedJobClose': forced,
            'jobDirectory': str(self.directory), 'resourceSamples': len(self.rows), 'observationErrors': self.observation_errors}
        _write(self.directory/'cleanup.json', self.closed)
        _write(self.directory/'resource-summary.json', summarize_resources(self.rows))
        _write(self.directory/'controller-progress.json', self.events)
        self.error_log.close()
        for handle, _, _ in self.owned.values():
            self.counter.k.CloseHandle(handle)
        return self.closed
