"""Windows 长目录 npm 打包回归：启动目录不应阻断实际存在的包。"""
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"core"))
from dsh_pack.export import _npm_pack

@unittest.skipUnless(os.name == "nt" and shutil.which("npm"), "requires Windows and existing npm")
class LongPackagePathTests(unittest.TestCase):
    def test_pack_existing_package_beyond_windows_cwd_limit(self):
        with tempfile.TemporaryDirectory(prefix="crate-long-cwd-") as directory:
            package=Path(directory)
            while len(str(package)) < 270:
                package=package/("nested-"+"x"*30)
            package.mkdir(parents=True)
            (package/"package.json").write_text(json.dumps({"name":"long-path-fixture","version":"1.0.0","scripts":{"prepack":"node -e \"process.exit(9)\""}}))
            (package/"index.js").write_text("export default 42")
            data=_npm_pack(package,"long-path-fixture",shutil.which("npm"))
            import io,tarfile
            with tarfile.open(fileobj=io.BytesIO(data),mode="r:gz") as archive:
                self.assertEqual(archive.extractfile("package/index.js").read(),b"export default 42")
