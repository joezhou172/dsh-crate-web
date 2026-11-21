"""Reference-size integration checks against actual archives, without real DSH data."""
import hashlib
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))
from dsh_pack.export import ExportOptions, export_profile
from dsh_pack.size_preview import build_preview
from dsh_pack.pack import read
from dsh_pack.errors import ExportError
from dsh_pack.user_cli import _invoke_core


ENV = {"schemaVersion":1,"os":{"name":"test","version":"test","arch":"x64"},"node":{"version":"unknown"},"dsh":{"version":"unknown"}}

def fixture(root):
    profile = root / "home" / "profiles" / "sample"
    package = profile / "node_modules" / "fixture-plugin"
    package.mkdir(parents=True)
    (profile / "package.json").write_text(json.dumps({"name": "sample", "dependencies": {"fixture-plugin": "1.0.0"}}))
    (profile / "empty.txt").write_bytes(b"")
    (package / "package.json").write_text(json.dumps({"name": "fixture-plugin", "version": "1.0.0"}))
    (package / "index.js").write_text("export default {}")
    return profile


def artifact(package, *args, **kwargs):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for path in sorted(package.iterdir()):
            data = path.read_bytes()
            entry = tarfile.TarInfo("package/" + path.name)
            entry.size = len(data)
            archive.addfile(entry, io.BytesIO(data))
    return buffer.getvalue()


def snapshot(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*") if p.is_file()}


class SizePreviewTests(unittest.TestCase):
    def test_reference_and_embedded_match_export_and_leave_source_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile = fixture(root)
            before = snapshot(profile)
            fixed_artifact = artifact(profile / "node_modules" / "fixture-plugin")
            for mode in ("share", "freeze"):
                with self.subTest(mode=mode), patch("dsh_pack.export._npm_pack", return_value=fixed_artifact), patch("dsh_pack.export._npm_command", return_value="fixture-npm"):
                    options = ExportOptions(environment=ENV, export_mode=mode)
                    preview = build_preview(profile, options=options)
                    result = export_profile(profile, root / (mode + ".dshcrate"), options=options)
                    size = preview["sizePreview"]
                    self.assertEqual(size["archiveBytes"], result.path.stat().st_size)
                    self.assertEqual(size["archiveBytes"], sum(size["categories"].values()) + size["containerBytes"])
                    self.assertEqual(size["referenceOnlyCount"], int(mode == "share"))
                    self.assertEqual(size["categories"]["plugins"] > 0, mode == "freeze")
                    self.assertEqual(read(result.path).profile_files["empty.txt"], b"")
                    self.assertEqual(snapshot(profile), before)

    def test_selected_data_is_counted(self):
        with tempfile.TemporaryDirectory() as directory, patch("dsh_pack.export._npm_command", return_value="fixture-npm"):
            root = Path(directory)
            profile = fixture(root)
            data = profile.parent.parent / "storages" / "sample.json"
            data.parent.mkdir()
            data.write_text('{"enabled":true}')
            selection = ({"path":"storages/sample.json", "kind":"plugin-data", "owner":"fixture-plugin"},)
            preview = build_preview(profile, options=ExportOptions(environment=ENV, data_selection=selection))
            self.assertGreater(preview["sizePreview"]["categories"]["userData"], 0)

    def test_temp_cleaned_on_success_and_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile = fixture(root)
            captured = []
            def temporary(**kwargs):
                result = tempfile.TemporaryDirectory(dir=root, **kwargs)
                captured.append(Path(result.name))
                return result
            with patch("dsh_pack.size_preview.TemporaryDirectory", side_effect=temporary), patch("dsh_pack.export._npm_command", return_value="fixture-npm"):
                build_preview(profile, options=ExportOptions(environment=ENV))
                error = ExportError("controlled artifact failure", stage="package-artifact", code="EXPORT_PACK_FAILED")
                with patch("dsh_pack.export._npm_pack", side_effect=error):
                    with self.assertRaises(ExportError) as caught:
                        build_preview(profile, options=ExportOptions(environment=ENV, export_mode="freeze"))
                    self.assertIs(caught.exception, error)
            self.assertTrue(captured)
            self.assertTrue(all(not path.exists() for path in captured))

    def test_preview_reuses_secret_validation(self):
        with tempfile.TemporaryDirectory() as directory, patch("dsh_pack.export._npm_command", return_value="fixture-npm"):
            profile = fixture(Path(directory))
            (profile / "config.yml").write_text("DEMO_API_KEY: controlled-test-value")
            before = snapshot(profile)
            with self.assertRaises(ExportError):
                build_preview(profile, options=ExportOptions(environment=ENV))
            self.assertEqual(snapshot(profile), before)

    def test_embedded_artifact_is_built_once_per_preview(self):
        with tempfile.TemporaryDirectory() as directory, patch("dsh_pack.export._npm_command", return_value="fixture-npm"):
            profile = fixture(Path(directory))
            with patch("dsh_pack.export._npm_pack", side_effect=artifact) as pack:
                build_preview(profile, options=ExportOptions(environment=ENV, export_mode="freeze"))
            pack.assert_called_once()

    def test_cli_uses_same_preview_and_preserves_failure(self):
        with tempfile.TemporaryDirectory() as directory, patch("dsh_pack.export._npm_command", return_value="fixture-npm"):
            profile = fixture(Path(directory))
            code, result = _invoke_core(["export", "--profile", str(profile), "--plan-only", "--output", str(Path(directory) / "unused.dshcrate"), "--json"])
            self.assertEqual(code, 0, result)
            self.assertEqual(result["sizePreview"]["status"], "measured")
            error = ExportError("controlled", stage="package-artifact", code="EXPORT_PACK_FAILED")
            with patch("dsh_pack.size_preview.export_profile", side_effect=error):
                code, result = _invoke_core(["export", "--profile", str(profile), "--plan-only", "--output", str(Path(directory) / "unused.dshcrate"), "--json"])
            self.assertEqual(code, 2)
            self.assertEqual(result["error"], error.as_dict())
            self.assertNotIn("sizePreview", result)


if __name__ == "__main__":
    unittest.main()
