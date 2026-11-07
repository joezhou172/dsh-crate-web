import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from release_guard import inspect_tarball


class DesktopReleaseManifestTests(unittest.TestCase):
    def test_only_exact_manifest_path_is_allowed(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'sample.tgz'
            with tarfile.open(path, 'w:gz') as archive:
                for name in ['packaging/desktop-bootstrap/manifest.json', 'packaging/desktop-bootstrap/local.json']:
                    data = b'{}'
                    entry = tarfile.TarInfo('package/' + name)
                    entry.size = len(data)
                    archive.addfile(entry, io.BytesIO(data))
            findings = inspect_tarball(path)['findings']
            rejected = [v['path'] for v in findings if v['rule'] == 'unnecessary-package-file']
            self.assertEqual(rejected, ['packaging/desktop-bootstrap/local.json'])


if __name__ == '__main__':
    unittest.main()
