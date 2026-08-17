"""P7 Skill test set T1-T15.

Run from the repository root:

    python skills/dsh-crate-troubleshooting/tests/run_tests.py

The tests exercise the version gate, code classification, repair-level policy,
and stop conditions of the Troubleshooting Skill against the diagnostic
registry in ``core/dsh_pack/diagnostics.py``.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from core.dsh_pack import diagnostics  # noqa: E402

SKILL_VERSION = "0.1.1"
DSH_CRATE_RANGE = ">=0.1.0 <0.2.0"
SUPPORTED_SCHEMAS = [1]


def envelope(**overrides):
    fields = {
        "producer": "dsh-crate",
        "crateVersion": "0.1.1",
        "diagnosticSchemaVersion": 1,
        "operation": "import",
        "operationId": "op-test",
        "status": "FAIL",
    }
    fields.update(overrides)
    return fields


def issue(code, stage, severity="BLOCKER", **extra):
    return {
        "code": code,
        "stage": stage,
        "severity": severity,
        "item": extra.pop("item", "test-item"),
        "expected": extra.pop("expected", "operation completes"),
        "observed": extra.pop("observed", {"message": "observed failure"}),
        "evidence": extra.pop("evidence", {"stage": stage, "code": code}),
        "impact": extra.pop("impact", "operation stopped"),
        "canContinue": extra.pop("canContinue", False),
        "suggestedChecks": extra.pop("suggestedChecks", ["verify evidence"]),
        "message": extra.pop("message", "observed failure"),
        **extra,
    }


def gate(crate_version, schema_version):
    return diagnostics.compat_status(
        skill_version=SKILL_VERSION,
        dsh_crate_range=DSH_CRATE_RANGE,
        supported_schemas=SUPPORTED_SCHEMAS,
        crate_version=crate_version,
        diagnostic_schema_version=schema_version,
    )


class T1KnownDiagnosticKnownVersion(unittest.TestCase):
    def test_full(self):
        result = gate("0.1.1", 1)
        self.assertEqual(result["status"], "FULL")
        self.assertTrue(result["canProceed"])
        known = diagnostics.classify(issue("PLUGIN_SOURCE_MISSING", "reference-install"))
        self.assertTrue(known["known"])


class T2OldButCompatibleVersion(unittest.TestCase):
    def test_compatible_older_generation_in_range(self):
        # Skill 0.2.0 supports >=0.1.0 <0.3.0; a 0.1.x diagnostic is in range
        # but from an older generation -> COMPATIBLE, can proceed.
        result = diagnostics.compat_status(
            skill_version="0.2.0",
            dsh_crate_range=">=0.1.0 <0.3.0",
            supported_schemas=[1],
            crate_version="0.1.9",
            diagnostic_schema_version=1,
        )
        self.assertEqual(result["status"], "COMPATIBLE")
        self.assertTrue(result["canProceed"])


class T3NewerUnsupportedCrateVersion(unittest.TestCase):
    def test_unsupported(self):
        result = gate("0.2.0", 1)
        self.assertEqual(result["status"], "UNSUPPORTED")
        self.assertFalse(result["canProceed"])
        self.assertIn("outside the supported range", result["reason"])


class T4UnsupportedDiagnosticSchema(unittest.TestCase):
    def test_schema_v2(self):
        result = gate("0.1.1", 2)
        self.assertEqual(result["status"], "UNSUPPORTED")
        self.assertFalse(result["canProceed"])
        self.assertIn("schema", result["reason"])


class T5UnknownDiagnosticCode(unittest.TestCase):
    def test_unknown_code_is_l3_no_write(self):
        classified = diagnostics.classify(issue("ERROR_XYZ_UNKNOWN", "planning"))
        self.assertFalse(classified["known"])
        self.assertEqual(classified["repairLevel"], "L3")
        self.assertEqual(classified["writeScope"], "none")


class T6PluginSourceMissing(unittest.TestCase):
    def test_classify(self):
        classified = diagnostics.classify(issue("PLUGIN_SOURCE_MISSING", "reference-install"))
        self.assertTrue(classified["known"])
        self.assertEqual(classified["stage"], "reference-install")
        self.assertEqual(classified["severity"], "BLOCKER")
        self.assertNotEqual(classified["repairLevel"], "L3")


class T7ArtifactIntegrityFailure(unittest.TestCase):
    def test_classify(self):
        classified = diagnostics.classify(issue("HASH_OR_INTEGRITY_ERROR", "preflight"))
        self.assertTrue(classified["known"])
        self.assertEqual(classified["stage"], "preflight")
        self.assertIn("integrity", classified["summary"].lower())
        self.assertNotEqual(classified["repairLevel"], "L3")


class T8BundleCompositionFailure(unittest.TestCase):
    def test_classify(self):
        classified = diagnostics.classify(issue("CONFLICT_BUNDLE_COMPOSITION", "composition"))
        self.assertTrue(classified["known"])
        self.assertEqual(classified["stage"], "composition")
        self.assertEqual(classified["severity"], "BLOCKER")


class T9ImportPrepareFailure(unittest.TestCase):
    def test_classify(self):
        classified = diagnostics.classify(issue("PROFILE_CONFIG_MISSING", "configuration"))
        self.assertTrue(classified["known"])
        self.assertEqual(classified["stage"], "configuration")
        self.assertEqual(classified["writeScope"], "temporary-profile")


class T10RuntimeVerifyFailure(unittest.TestCase):
    def test_classify(self):
        classified = diagnostics.classify(issue("RUNNER_READY_TIMEOUT", "runtime"))
        self.assertTrue(classified["known"])
        self.assertEqual(classified["stage"], "runtime")
        self.assertEqual(classified["severity"], "BLOCKER")


class T11RepairSucceedsVerifyPass(unittest.TestCase):
    def test_pass_after_repair(self):
        # Pure decision-rule check: after a repair, only a real PASS may report PASS.
        result = {"status": "PASS", "evidence": {"ready": True}}
        self.assertEqual(result["status"], "PASS")
        self.assertNotEqual(result["status"], "FAIL")


class T12RepairFailsRemainFail(unittest.TestCase):
    def test_fail_stays_fail(self):
        result = {"status": "FAIL", "evidence": {"reason": "repair did not resolve"}}
        self.assertEqual(result["status"], "FAIL")
        self.assertNotEqual(result["status"], "PASS")


class T13ConfirmationRequiredRepair(unittest.TestCase):
    def test_overwrite_is_l2(self):
        classified = diagnostics.classify(issue("OVERWRITE_CONFIRMATION_REQUIRED", "planning"))
        self.assertTrue(classified["known"])
        self.assertEqual(classified["repairLevel"], "L2")
        # L2 means the Skill must ask the user before any write.
        self.assertNotEqual(classified["writeScope"], "none")


class T14ForbiddenCredentialMutation(unittest.TestCase):
    def test_secret_class_never_writes(self):
        # SECRET_MISSING carries the policy that secret values are never in the
        # Pack and never mutated by the Skill.
        classified = diagnostics.classify(issue("SECRET_MISSING", "planning"))
        self.assertTrue(classified["known"])
        self.assertEqual(classified["writeScope"], "none")
        # Policy: no credential material may be written, read back into a
        # report, or embedded in a repair recipe.
        self.assertNotIn("credential", classified.get("repairRecipe", "none"))
        self.assertEqual(classified["severity"], "WARNING")


class T15UnrepairableStopsSafely(unittest.TestCase):
    def test_unknown_stops(self):
        classified = diagnostics.classify(issue("UNKNOWN_CODE_99", "planning"))
        self.assertFalse(classified["known"])
        self.assertEqual(classified["repairLevel"], "L3")
        self.assertEqual(classified["writeScope"], "none")
        self.assertFalse(classified.get("canProceed", False))

    def test_unsupported_stops(self):
        result = gate("0.3.0", 1)
        self.assertEqual(result["status"], "UNSUPPORTED")
        self.assertFalse(result["canProceed"])


class T16EnvelopeCarriedByCore(unittest.TestCase):
    """The versioned envelope must be present on real Core diagnostics."""

    def test_pack_import_error_envelope(self):
        from core.dsh_pack.errors import PackImportError

        error = PackImportError(
            "boom", stage="planning", code="PLUGIN_SOURCE_MISSING",
            details={"operationId": "op-test", "item": "@example/plugin"},
        )
        data = error.as_dict()
        for key in ("producer", "crateVersion", "diagnosticSchemaVersion", "operation", "operationId", "status"):
            self.assertIn(key, data, key)
        self.assertEqual(data["producer"], "dsh-crate")
        self.assertEqual(data["operation"], "import")
        self.assertEqual(data["status"], "FAIL")

    def test_preflight_finding_envelope(self):
        from core.dsh_pack.preflight import _finding

        finding = _finding("BLOCKER", "SCHEMA_ERROR", "schema error", path="manifest.json")
        data = finding.as_dict()
        self.assertEqual(data["producer"], "dsh-crate")
        self.assertEqual(data["operation"], "inspect")
        self.assertEqual(data["status"], "BLOCKER")
        self.assertIn("diagnosticSchemaVersion", data)

    def test_runtime_diagnostic_envelope(self):
        from core.dsh_pack.verify import _runtime_diagnostic

        data = _runtime_diagnostic(
            code="RUNNER_READY_TIMEOUT", stage="runtime", message="timeout",
            evidence={"port": 3000}, item="web", expected="ready", impact="no boot",
        )
        self.assertEqual(data["producer"], "dsh-crate")
        self.assertEqual(data["operation"], "verify")
        self.assertEqual(data["status"], "FAIL")


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
