import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from dsh_pack.errors import ExportError, PackImportError
from dsh_pack.importer import ImportOptions, create_import_plan
from dsh_pack.incremental import plan_incremental
from dsh_pack.model_api import endpoint, secret_name, validate
from dsh_pack.export import ExportOptions, export_profile, _profile_files
from dsh_pack.preflight import PreflightContext, inspect_pack
from test_size_preview import artifact, fixture, ENV


class ModelApiBoundaryTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("DSH_PACK_CONFIG_MERGE_COMMAND"), "requires host static YAML parser")
    def test_workspace_model_package_selectors_only(self):
        with tempfile.TemporaryDirectory() as workspace:
            root = Path(workspace)
            (root / "package.json").write_text("{}")
            path = root / "pnpm-workspace.yaml"
            selector = "@deepseek-ai/dsh-base>@deepseek-ai/dsh-agent-default-model"
            for text in (f'overrides: {{"{selector}": "-", "@deepseek-ai/dsh-base>@deepseek-ai/dsh-llm-deepseek-api-key": "-"}}\n',
                         f"packages: ['.']\noverrides:\n  '{selector}': '1.0.0'\n"):
                path.write_bytes(text.encode())
                self.assertEqual(_profile_files(root, root / "out")[path.name], text.encode())
            safe = f'overrides: {{"{selector}": "-"}}\n'
            for text in (safe + "row: {id: llm-pi-ai}\n", safe + "apiKeyEnv: PRIVATE_NAME\n",
                         safe + 'settings: {apiKey: "fake-test-value"}\n',
                         safe + "EXAMPLE_API_KEY: fake-test-value\n",
                         safe + 'headers: {Authorization: "Bearer fake-test-value"}\n',
                         safe + "providers: {internal: {models: []}}\n",
                         f'overrides: {{"{selector}": {{provider: example}}}}\n',
                         safe + "overrides: {}\n", safe + 'extra: &dynamic !custom value\n'):
                path.write_text(text)
                with self.subTest(text=text), self.assertRaises(ExportError):
                    _profile_files(root, root / "out")
            path.unlink()
            (root / "other.yaml").write_text(safe)
            with self.assertRaises(ExportError):
                _profile_files(root, root / "out")

    def test_rejects_extra_headers_and_unlisted_default(self):
        provider = {"models": [{"id": "first"}]}
        with self.assertRaises(ExportError):
            validate({"providers": {"one": provider}, "defaultModel": {"provider": "one", "model": "other"}})
        with self.assertRaises(ExportError):
            validate({"providers": {"one": {**provider, "headers": {}}}, "defaultModel": None})

    def test_clean_endpoints(self):
        for value in ("https://models.example/v1", "http://127.0.0.1:13337/v1", "https://opencode.ai/zen/go/v1",
                      "https://opencode.ai/inference/go/openai/v1"):
            self.assertEqual(endpoint(value), value)

    def test_ambiguous_or_authenticated_endpoints(self):
        for value in ("https://user:password@models.example/v1", "https://models.example/v1?key=x",
                      "https://models.example/#secret", "https://models.example/%3Fsecret",
                      "https://models.example/v1\\other", "file:///test", "http://public.example/v1",
                      "https://opencode.ai/zen/go/v1?key=no", "https://different.example/zen/go/v1"):
            with self.subTest(value=value), self.assertRaises(ExportError):
                endpoint(value)

    def test_only_environment_variable_names(self):
        self.assertEqual(secret_name("MODEL_API_KEY"), "MODEL_API_KEY")
        for value in ("", "Bearer fake", "${MODEL_KEY}", "key=value"):
            with self.subTest(value=value), self.assertRaises(ExportError):
                secret_name(value)

    @unittest.skipUnless(os.environ.get("DSH_PACK_CONFIG_MERGE_COMMAND"), "requires host static YAML parser")
    def test_opencode_go_profile_round_trip_offline(self):
        with tempfile.TemporaryDirectory() as workspace:
            root = Path(workspace)
            profile = fixture(root)
            route = {"baseURL": "https://opencode.ai/zen/go/v1", "api": "openai-completions",
                     "apiKeyEnv": "OPENCODE_API_KEY", "models": [{"id": "fixture-model"}]}
            (profile / "cordis.patch.yml").write_text(json.dumps([
                {"id": "llm-pi-ai", "config": {"providers": {"opencode-go": route}}},
                {"id": "agent-default-model", "config": {"provider": "opencode-go", "model": "fixture-model"}}]))
            with patch("dsh_pack.export._npm_pack", return_value=artifact(profile / "node_modules/fixture-plugin")):
                result = export_profile(profile, root / "offline.dshcrate", options=ExportOptions(
                    environment=ENV, export_mode="freeze", model_providers=("opencode-go",)))
            preflight = inspect_pack(result.path, context=PreflightContext(current_environment=ENV, available_secrets=set()))
            self.assertEqual(preflight.pack["modelApi"]["providers"]["opencode-go"], route)
            self.assertEqual(preflight.secrets["missing"], ["OPENCODE_API_KEY"])

    @unittest.skipUnless(os.environ.get("DSH_PACK_CONFIG_MERGE_COMMAND"), "requires host static YAML parser")
    def test_frozen_archive_and_preflight(self):
        with tempfile.TemporaryDirectory() as workspace:
            root = Path(workspace)
            profile = fixture(root)
            config = profile / "cordis.patch.yml"
            (profile / ".env.test").write_text("FIXTURE_MODEL_KEY=never-pack-this-marker")
            config.write_text(json.dumps([
                {"id": "llm-pi-ai", "config": {"providers": {
                    "one": {"baseURL": "http://127.0.0.1:13337/v1", "api": "openai-completions",
                            "apiKeyEnv": "FIXTURE_MODEL_KEY", "models": [{"id": "first"}, {"id": "second"}],
                            "headers": {"Authorization": "never-pack-this-marker"}},
                    "not-selected": {"baseURL": "https://invalid.example/api?key=never-pack-this-marker"}}}},
                {"id": "agent-default-model", "config": {"provider": "one", "model": "second"}}]))
            original = config.read_bytes()
            blob = artifact(profile / "node_modules/fixture-plugin")
            for selected in [(), ("one",)]:
                with self.subTest(selected=selected), patch("dsh_pack.export._npm_pack", return_value=blob):
                    path = root / "out.dshcrate"
                    result = export_profile(profile, path, options=ExportOptions(
                        environment=ENV, export_mode="freeze", compression="fast", model_providers=selected))
                    with ZipFile(path) as archive:
                        contents = b"".join(archive.read(name) for name in archive.namelist())
                    self.assertNotIn(b"never-pack-this-marker", contents)
                    self.assertNotIn(b"not-selected", contents)
                    inspected = inspect_pack(path, context=PreflightContext(current_environment=ENV, available_secrets=set()))
                    self.assertEqual(inspected.secrets["missing"], ["FIXTURE_MODEL_KEY"] if selected else [])
                    if selected:
                        self.assertEqual(inspected.pack["modelApi"], result.plan["modelApi"])
                        self.assertEqual(result.plan["modelApi"]["defaultModel"]["model"], "second")
                        home = profile.parent.parent
                        options = ImportOptions(current_environment=ENV, overwrite_existing_profile=True,
                                                target_profile_name=profile.name, overwrite_confirmation="OVERWRITE")
                        with self.assertRaises(PackImportError) as blocked:
                            create_import_plan(path, home, options=options)
                        self.assertEqual(blocked.exception.code, "MODEL_API_NEW_PROFILE_ONLY")
                        for mode in ("add", "update"):
                            with self.assertRaises(PackImportError) as blocked:
                                plan_incremental(path, home, profile.name, mode, options, root)
                            self.assertEqual(blocked.exception.code, "MODEL_API_NEW_PROFILE_ONLY")
                    else:
                        self.assertNotIn(b"FIXTURE_MODEL_KEY", contents)
                        self.assertNotIn("modelApi", inspected.pack)
                    self.assertEqual(config.read_bytes(), original)
