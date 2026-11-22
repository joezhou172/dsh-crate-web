import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_size_preview import ENV, artifact, fixture
from dsh_pack.export import ExportOptions, export_profile
from dsh_pack.user_cli import _invoke_core


class SnapshotStoragePreflightTests(unittest.TestCase):
    def test_plugin_storage_blocked_before_and_during_snapshot_import(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile = fixture(root)
            storage = root / "home/storages/sample.json"
            storage.parent.mkdir()
            storage.write_text('{"enabled":true}')
            selection = {"path": "storages/sample.json", "kind": "plugin-data", "owner": "fixture-plugin"}
            options = ExportOptions(environment=ENV, export_mode="freeze", data_selection=(selection,))
            pack = root / "sample.dshcrate"
            with patch("dsh_pack.export._npm_pack", side_effect=artifact):
                export_profile(profile, pack, options=options)
            target = root / "target"
            for policy in ("strict", "compatible"):
                with self.subTest(policy=policy):
                    args = [str(pack), "--compatibility-policy", policy]
                    exit_code, preview = _invoke_core(["inspect", *args])
                    self.assertNotEqual(exit_code, 0)
                    self.assertFalse(preview["canContinue"])
                    code = "SNAPSHOT_HOME_DATA_UNSUPPORTED"
                    finding = next(item for item in preview["findings"] if item["code"] == code)
                    self.assertEqual(finding["severity"], "BLOCKER")
                    self.assertEqual(finding["details"]["paths"], [selection["path"]])
                    for flags in (["--plan-only"], []):
                        exit_code, result = _invoke_core(["import", *args, "--dsh-home", str(target), *flags])
                        self.assertNotEqual(exit_code, 0)
                        self.assertEqual(result["error"]["code"], code)
                    self.assertFalse(target.exists())
