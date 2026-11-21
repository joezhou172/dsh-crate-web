"""pnpm 制品重封装必须绑定内容，而非生成时间。"""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from test_size_preview import artifact
from dsh_pack.export import _npm_pack


class PnpmIdentityTests(unittest.TestCase):
    def test_repacked_artifact_is_stable_across_clock_changes_and_detects_content_change(self):
        with tempfile.TemporaryDirectory() as directory:
            package=Path(directory)/'package';package.mkdir()
            (package/'package.json').write_text(json.dumps({'name':'identity-fixture','version':'1.0.0','dsh':{'bundle':{'patch':'./patch.yml'}}}))
            (package/'patch.yml').write_text('[]\n')
            def run(command,**kwargs):
                destination=Path(command[command.index('--pack-destination')+1])
                (destination/'fixture.tgz').write_bytes(artifact(package))
                return subprocess.CompletedProcess(command,0,'','')
            with patch('dsh_pack.export.subprocess.run',side_effect=run):
                with patch('time.time',return_value=1000):
                    first=_npm_pack(package,'identity-fixture',('fixture-pnpm',))
                with patch('time.time',return_value=2000):
                    second=_npm_pack(package,'identity-fixture',('fixture-pnpm',))
                    (package/'patch.yml').write_text('[{}]\n')
                    changed=_npm_pack(package,'identity-fixture',('fixture-pnpm',))
            self.assertEqual(first,second)
            self.assertNotEqual(second,changed)
            self.assertEqual(int.from_bytes(first[4:8],'little'),0)


if __name__=='__main__':unittest.main()
