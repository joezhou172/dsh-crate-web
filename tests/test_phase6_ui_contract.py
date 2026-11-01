"""Gate 6 UI/Core boundary contracts.

These tests intentionally inspect the small browser/host adapter surface. The
browser must render Core decisions and diagnostics, not recreate them.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
CLIENT = ROOT / "src" / "client" / "DshCratePage.tsx"
HOST = ROOT / "src" / "index.ts"
LOCALES = ROOT / "src" / "client" / "locales.ts"
CLIENT_LIB = ROOT / "lib" / "client.js"
HOST_LIB = ROOT / "lib" / "index.js"


class Phase6UiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = CLIENT.read_text(encoding="utf-8")
        cls.host = HOST.read_text(encoding="utf-8")
        cls.locales = LOCALES.read_text(encoding="utf-8")

    def test_preflight_exposes_top_level_core_continue_decision(self) -> None:
        preflight = Path(ROOT / "core" / "dsh_pack" / "preflight.py").read_text(encoding="utf-8")
        self.assertIn("def can_continue", preflight)
        self.assertIn('"canContinue": self.can_continue', preflight)
        self.assertIn('"warningCount": self.warning_count', preflight)
        self.assertIn('"requiredPlugins": self.required_plugins', preflight)
        self.assertIn('"optionalPlugins": self.optional_plugins', preflight)

    def test_import_preview_has_target_safety_and_environment_sections(self) -> None:
        for marker in (
            "targetProfile",
            "requiredPlugins",
            "optionalPlugins",
            "warningCount",
            "environment",
            "willNotOverwrite",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.client)
        self.assertIn("result.targetProfile", self.client)
        self.assertIn("--plan-only", self.host)

    def test_failure_keeps_structured_diagnostic_and_copy_action(self) -> None:
        dialog = (CLIENT.parent / "ReportDialog.tsx").read_text(encoding="utf-8")
        # 摘要不枚举诊断字段；弹窗与复制必须保留整个响应，不能选择字段或截断。
        for marker in ("JSON.stringify(value, null, 2)", "navigator.clipboard.writeText(text)", "<dialog", "forwardToAgent"):
            with self.subTest(marker=marker):
                self.assertIn(marker, dialog)
        self.assertIn("openDetails(value)", self.client)
        self.assertNotIn(".slice(", dialog)
        self.assertIn("Copy full diagnostic", self.locales)
        self.assertNotIn("throw new Error(error)", self.client)

    def test_core_failure_diagnostic_preserves_profile_lifecycle(self) -> None:
        errors = Path(ROOT / "core" / "dsh_pack" / "errors.py").read_text(encoding="utf-8")
        self.assertIn('"originalProfileStatus"', errors)
        self.assertIn('"failedProfileStatus"', errors)

    def test_verify_is_available_through_host_and_ui(self) -> None:
        self.assertIn("action === 'verify'", self.host)
        self.assertIn("['verify'", self.host)
        self.assertIn("'verify'", self.client)
        self.assertIn("verifyButton", self.client)

    def test_client_does_not_reimplement_core_status_rules(self) -> None:
        forbidden = (
            "result.status === 'READY'",
            "result.status === 'PASS'",
            "finding.severity ===",
        )
        for expression in forbidden:
            with self.subTest(expression=expression):
                self.assertNotIn(expression, self.client)

    def test_export_defaults_to_embedded_for_importable_packs(self) -> None:
        self.assertIn("modes[name] ?? 'embedded'", self.client)

    def test_installed_bundle_inventory_is_separate_from_active_export_plugins(self) -> None:
        for marker in ("listInstalledBundles", "installedBundles", "installation-anchor"):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.host)
        self.assertIn("installedBundles", self.client)
        self.assertIn("active", self.client)
        self.assertIn("includeInstalledBundles", self.client)
        self.assertIn("include-installed-bundles", self.host)
        self.assertNotIn("selectedProfile?.plugins", self.client)

    def test_export_result_expands_plugins_bundle_order_and_artifact_mode(self) -> None:
        for marker in ("exportPlugins", "plugin.bundle", "bundle.order", "artifact.mode", "runtime.source"):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.client)
        self.assertIn("exportPlugins", self.locales)

    def test_import_success_has_explicit_result_and_target(self) -> None:
        for marker in ("ImportSuccess", "importSuccess", "installedPlugins", "preparedProfile"):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.client)
        self.assertIn("importSuccess", self.locales)

    def test_import_target_modes_require_core_confirmation_for_destructive_actions(self) -> None:
        for marker in ("ImportMode", "overwrite", "window.confirm", "newProfileDialogOpen", "confirmNewProfileImport", "confirmOverwrite", "targetProfile", "profileNameExists"):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.client if marker != "targetProfile" else self.client)
        self.assertIn("OVERWRITE", Path(ROOT / "core" / "dsh_pack" / "importer.py").read_text(encoding="utf-8"))
        self.assertIn("--confirm-overwrite", self.host)

    def test_profile_delete_requires_confirmation_and_uses_core(self) -> None:
        self.assertIn("delete-profile", self.host)
        self.assertIn("confirmDelete", self.client)
        self.assertIn("window.confirm", self.client)
        self.assertIn("DELETE_CONFIRMATION_REQUIRED", Path(ROOT / "core" / "dsh_pack" / "importer.py").read_text(encoding="utf-8"))

    def test_published_lib_contains_profile_safety_flow(self) -> None:
        client_lib = CLIENT_LIB.read_text(encoding="utf-8")
        host_lib = HOST_LIB.read_text(encoding="utf-8")
        for marker in ("newProfileDialogOpen", "confirmNewProfileImport", "window.confirm", "profileNameExists", "delete-profile", "confirmDelete"):
            with self.subTest(marker=marker):
                self.assertIn(marker, client_lib)
        for marker in ("--target-profile", "--confirm-overwrite", 'action === "delete-profile"'):
            with self.subTest(marker=marker):
                self.assertIn(marker, host_lib)

    def test_profile_management_exposes_delete_and_real_switch_restart(self) -> None:
        for marker in (
            'data-field="profileManagement"',
            'switch-profile',
            'switch-status',
            'switchProfile',
            'window.confirm',
            'currentRuntimeProfile',
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.client)
        for marker in (
            "action === 'switch-profile'",
            "action === 'switch-status'",
            'SWITCH_CONFIRMATION_REQUIRED',
            'ACTIVE_PROFILE',
            'restart-helper.mjs',
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.host)
        self.assertIn('data-field": "profileManagement"', CLIENT_LIB.read_text(encoding="utf-8"))
        self.assertIn('action === "switch-profile"', HOST_LIB.read_text(encoding="utf-8"))
        self.assertIn('PROFILE_SWITCH_READY', (ROOT / 'src' / 'restart-helper.mjs').read_text(encoding='utf-8'))

    def test_create_profile_defaults_to_official_and_crate_bundles(self) -> None:
        for marker in (
            "create-profile",
            "DEFAULT_CREATE_BUNDLES",
            "OFFICIAL_BUNDLE_MISSING",
            "PROFILE_EXISTS",
            "CRATE_PACKAGE_NAME",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.host)
        for marker in ("createSelectedProfile", "createProfile", "createSuccess", "createTarget"):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.client)
        for marker in ("createProfile", "createProfileHint", "createPending", "createSuccess"):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.locales)
        self.assertIn('action === "create-profile"', HOST_LIB.read_text(encoding="utf-8"))
        self.assertIn("createSelectedProfile", CLIENT_LIB.read_text(encoding="utf-8"))

    def test_reading_profiles_never_installs_crate_into_other_profiles(self) -> None:
        # The old global repair changed unrelated user Profiles during read-only
        # actions. Explicit new-Profile creation may install only into its target.
        self.assertNotIn("ensureCrateBundleInAllProfiles", self.host)
        reader = self.host.split("async function listProfiles(", 1)[1].split("const PROFILE_PATCH_TEMPLATE", 1)[0]
        self.assertNotIn("writeFile(", reader)
        self.assertNotIn("copyPackage(", reader)
        creator = self.host.split("async function createProfile(", 1)[1].split("async function handleApi(", 1)[0]
        self.assertNotIn("copyPackage(packageRoot, join(profileDir, 'node_modules'", creator)
        self.assertIn("copyPackage(packageRoot, join(seedProfile, 'node_modules'", creator)
        self.assertIn("['export', '--profile', seedProfile", creator)
        self.assertIn("['import', pack, '--dsh-home', home", creator)
        self.assertIn("await lstat(profileDir)", creator)


if __name__ == "__main__":
    unittest.main()
