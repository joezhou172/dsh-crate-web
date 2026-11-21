"""独立于插件进程，等待用户正常退出后应用已校验组件；不强杀、不抢占窗口。"""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import ctypes
from ctypes import wintypes


def restart_arguments(root):
    """只保留实际主进程的窗口数据目录与已有调试端点；不猜测启动参数。"""
    shell = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    query = "$ErrorActionPreference='Stop'; $owned=@(Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -eq $env:CRATE_PATCH_EXE }); @($owned | Where-Object { $owned.ProcessId -notcontains $_.ParentProcessId -and $_.CommandLine -notmatch '--type[= ]' } | Select-Object -ExpandProperty CommandLine) | ConvertTo-Json -Compress"
    result = subprocess.run([str(shell), '-NoProfile', '-NonInteractive', '-Command', query],
                            env=dict(os.environ, CRATE_PATCH_EXE=str(root / 'DeepSeek Harness.exe')),
                            capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=30)
    if result.returncode:
        raise RuntimeError('无法确认桌面启动参数，未修改程序')
    lines = json.loads(result.stdout.strip() or '[]')
    if isinstance(lines, str): lines = [lines]
    if len(lines) > 1: raise RuntimeError('同一安装有多个桌面主进程；请先正常退出多余实例')
    if not lines: raise RuntimeError('原桌面已退出，无法确认原启动参数；未修改程序，请重新打开后再启用')
    shell32 = ctypes.WinDLL('shell32', use_last_error=True)
    shell32.CommandLineToArgvW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_int)]
    shell32.CommandLineToArgvW.restype = ctypes.POINTER(wintypes.LPWSTR)
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    count = ctypes.c_int()
    argv = shell32.CommandLineToArgvW(lines[0], ctypes.byref(count))
    if not argv: raise ctypes.WinError(ctypes.get_last_error())
    try:
        return [argv[i] for i in range(1, count.value) if argv[i].startswith(('--user-data-dir=', '--remote-debugging-address=', '--remote-debugging-port='))]
    finally: kernel32.LocalFree(argv)


def execute(job_path):
    job_path = Path(job_path).resolve(strict=True)
    job = json.loads(job_path.read_text(encoding='utf-8'))
    base = job_path.parent
    report = Path(job['report'])
    root = Path(job['root'])

    def save(status, **values):
        data = {**job, 'status': status, **values}
        tmp = report.with_suffix('.tmp-' + job['id'])
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        tmp.replace(report)

    lock = root / '.crate-setup.lock'
    owned = False
    try:
        for path in [root, *root.absolute().parents, lock, report]:
            if path.is_symlink() or path.is_junction():
                raise RuntimeError('拒绝链接安装目录或任务路径')
        with lock.open('x', encoding='utf-8') as stream:
            json.dump({'pid': os.getpid(), 'job': job['id']}, stream)
        owned = True
        spec = importlib.util.spec_from_file_location('launcher', base / 'scripts/desktop-patch-launcher.py')
        launcher = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(launcher)
        restart_args = restart_arguments(root)
        job['preservedUserData'] = any(arg.startswith('--user-data-dir=') for arg in restart_args)
        save('waiting-exit')
        launcher.wait_for_exit(root, 120)
        save('applying')
        with (base / 'apply.log').open('wb') as log:
            process = subprocess.run([sys.executable, '-B', str(base / 'scripts/desktop-patch-launcher.py'),
                                      'apply', '--root', str(root), '--yes'], cwd=base,
                                     stdout=log, stderr=subprocess.STDOUT,
                                     creationflags=subprocess.CREATE_NO_WINDOW, timeout=120)
        if process.returncode:
            raise RuntimeError((base / 'apply.log').read_text(encoding='utf-8', errors='replace'))
        receipt = root / 'resources/crate-profile-patch.json'
        value = json.loads(receipt.read_text(encoding='utf-8'))
        value['componentId'] = job['componentId']
        receipt.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
        # Applied is not the same as a verified running UI. The plugin acknowledges on next load.
        save('applied', appliedAt=time.time())
        restart_env = dict(os.environ)
        restart_env.pop('ELECTRON_RUN_AS_NODE', None)
        restart_env.pop('NODE_OPTIONS', None)
        subprocess.Popen([str(root / 'DeepSeek Harness.exe'), *restart_args], cwd=root, env=restart_env)
    except Exception as error:
        save('failed', error=str(error), log=str(base / 'apply.log'))
        return 1
    finally:
        if owned:
            lock.unlink(missing_ok=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(execute(sys.argv[1]))
