import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('desktop_patch', ROOT / 'scripts/desktop-profile-patch.py')
patcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patcher)

class DesktopPatchBoundaryTests(unittest.TestCase):
    def test_installed_requires_confirmation(self):
        with self.assertRaisesRegex(ValueError, '明确确认'):
            patcher.patch(Path('unused'), installed=True)

    def fixture(self, marked):
        path = Path(tempfile.mkdtemp(prefix='desktop-patch-guard-', dir=ROOT / 'work'))
        (path / 'resources').mkdir()
        (path / 'resources/app.asar').write_bytes(b'unknown-official-build')
        if marked: (path / '.crate-isolated-desktop').write_text('test only')
        return path

    def test_unmarked_copy_rejected(self):
        path = self.fixture(False)
        with self.assertRaisesRegex(ValueError, '独立桌面副本'):
            patcher.patch(path)
        self.assertEqual((path / 'resources/app.asar').read_bytes(), b'unknown-official-build')

    def test_unknown_build_rejected_without_writes(self):
        path = self.fixture(True)
        with self.assertRaisesRegex(ValueError, '未知版本'):
            patcher.patch(path)
        self.assertEqual((path / 'resources/app.asar').read_bytes(), b'unknown-official-build')
        self.assertFalse((path / 'resources/app.asar.crate-original').exists())

if __name__ == '__main__':
    unittest.main()
