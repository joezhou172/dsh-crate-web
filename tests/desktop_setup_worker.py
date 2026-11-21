"""实际 ASAR 应用/撤销在隔离目录；不会启动 Electron 窗口。"""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('worker', ROOT / 'scripts/desktop-setup-worker.py')
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


class SetupWorker(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix='setup-worker-', dir=ROOT / 'work'))
        self.target = self.base / 'desktop'
        (self.target / 'resources').mkdir(parents=True)
        (self.target / 'DeepSeek Harness.exe').write_bytes(b'not executed')
        self.job = self.base / 'job'
        self.job.mkdir()
        for file in ['desktop-profile-adapter.mjs', 'desktop-instances.mjs', 'desktop-maintenance.mjs', 'scripts/desktop-profile-patch.py', 'scripts/desktop-patch-launcher.py']:
            dest = self.job / file
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / file, dest)
        self.report = self.base / 'task.json'
        self.config = self.job / 'job.json'
        self.config.write_text(json.dumps({'id': 'test', 'root': str(self.target), 'report': str(self.report), 'componentId': 'test', 'startedAt': 0}))

    def test_unknown_archive_preserved(self):
        archive = self.target / 'resources/app.asar'
        archive.write_bytes(b'unknown')
        self.assertEqual(worker.execute(self.config), 1)
        self.assertEqual(archive.read_bytes(), b'unknown')
        self.assertEqual(json.loads(self.report.read_text())['status'], 'failed')
        self.assertFalse((self.target / '.crate-setup.lock').exists())

    def test_busy_worker_refused(self):
        (self.target / '.crate-setup.lock').write_text('another worker')
        self.assertEqual(worker.execute(self.config), 1)
        self.assertEqual((self.target / '.crate-setup.lock').read_text(), 'another worker')

    def test_real_apply_and_restore_no_desktop_launch(self):
        original = ROOT / 'work/desktop-profile-isolated/resources/app.asar.crate-original'
        if not original.exists(): self.skipTest('Exact official Desktop fixture not available')
        archive = self.target / 'resources/app.asar'
        shutil.copyfile(original, archive)
        # Launcher and process-state probes run for real. Only the final Electron start is suppressed.
        actual_popen = subprocess.Popen
        launches = []
        def popen(args, *rest, **kw):
            if args[0] == str(self.target / 'DeepSeek Harness.exe'):
                launches.append(args); return None
            return actual_popen(args, *rest, **kw)
        with patch.object(worker.subprocess, 'Popen', side_effect=popen), patch.object(worker, 'restart_arguments', return_value=[]):
            self.assertEqual(worker.execute(self.config), 0)
        self.assertEqual(len(launches), 1)
        state = json.loads(self.report.read_text())
        self.assertEqual(state['status'], 'applied')
        receipt = json.loads((self.target / 'resources/crate-profile-patch.json').read_text())
        self.assertEqual(receipt['componentId'], 'test')
        self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(), receipt['patchedSha256'])
        restored = subprocess.run([sys.executable, '-B', str(self.job / 'scripts/desktop-patch-launcher.py'), 'restore', '--root', str(self.target), '--yes'], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        self.assertEqual(restored.returncode, 0, restored.stdout.decode(errors='replace'))
        self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(), receipt['originalSha256'])
        (self.base / 'verification.json').write_text(json.dumps({'status': 'PASS', 'actualAsarApplyRestore': True, 'desktopRestart': 'UNTESTED', 'desktopWindowsOpened': 0}))


if __name__ == '__main__': unittest.main()
