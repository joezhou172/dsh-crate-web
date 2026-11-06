import importlib.util
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
spec = importlib.util.spec_from_file_location('manual_release', ROOT / 'scripts/manual-release.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)

class ManualReleaseTests(unittest.TestCase):
    def test_preview_only_and_no_shell_input(self):
        for version in ['1.2.3', '../preview', '0.1.2-preview.14;echo x', '0.1.2-preview.14\n']:
            with self.subTest(version=version), patch.dict(os.environ, {'RELEASE_VERSION': version, 'EXPECTED_SHA256': 'a' * 64}):
                with self.assertRaises(ValueError):
                    release.release_inputs()

    def test_valid_identity(self):
        with patch.dict(os.environ, {'RELEASE_VERSION': '0.1.2-preview.14', 'EXPECTED_SHA256': 'a' * 64}):
            self.assertEqual(release.release_inputs(), ('0.1.2-preview.14', 'a' * 64))

    def test_hash_mismatch_stops_before_archive_read(self):
        with patch.dict(os.environ, {'RELEASE_VERSION': '0.1.2-preview.14', 'EXPECTED_SHA256': 'a' * 64}), patch.object(Path, 'read_bytes', return_value=b'changed'), patch.object(release, 'inspect_tarball') as inspect:
            with self.assertRaisesRegex(ValueError, '不一致'):
                release.audit()
            inspect.assert_not_called()

if __name__ == '__main__':
    unittest.main()
