import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'core'))
from dsh_pack.importer import _validate_profile_name
from dsh_pack.errors import PackImportError


class ProfileNameTests(unittest.TestCase):
    def test_shared_portable_names(self):
        cases = json.loads(Path(__file__).with_name('profile_names.json').read_text('utf-8'))
        for name in cases['valid']:
            with self.subTest(name=name):
                self.assertEqual(_validate_profile_name(name), name)
        for name in cases['invalid'] + [None, 1]:
            with self.subTest(name=name):
                with self.assertRaises(PackImportError):
                    _validate_profile_name(name)


if __name__ == '__main__':
    unittest.main()
