"""Read-only diagnosis using the release's existing diagnostic registry."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any, Sequence

from .diagnostics import CRATE_VERSION, classify, compat_status


def _issues(value: Any):
    if isinstance(value, list):
        for item in value:
            yield from _issues(item)
    elif isinstance(value, dict):
        if isinstance(value.get("code"), str):
            yield value
        # Only traverse report containers, never execute or interpret arbitrary
        # command strings, package configuration or model instructions.
        for key in ("result", "error", "errors", "diagnostic", "diagnostics", "findings", "steps"):
            if key in value:
                yield from _issues(value[key])


def diagnose(report: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(report, dict):
        raise ValueError("diagnostic report must be a JSON object")
    version = report.get("crateVersion")
    schema = report.get("diagnosticSchemaVersion")
    if (report.get("producer") != "dsh-crate" or not isinstance(version, str)
            or type(schema) is not int):
        compatibility = {"status": "UNSUPPORTED", "canProceed": False,
                         "reason": "diagnostic envelope is incomplete"}
    else:
        compatibility = compat_status(
            skill_version=CRATE_VERSION, dsh_crate_range=">=0.1.0 <0.1.1",
            supported_schemas=[1], crate_version=version,
            diagnostic_schema_version=schema,
        )
    issues = []
    for issue in _issues(report):
        matched = classify(issue)
        # A registry entry suggests checks, not a proven root cause. Actual
        # severity, stage and evidence always remain available unchanged.
        issues.append({
            "code": issue["code"], "stage": issue.get("stage"),
            "severity": issue.get("severity"), "known": matched["known"],
            "suggestedChecks": matched.get("suggestedChecks", []),
            "registry": matched, "evidence": copy.deepcopy(issue),
        })
    supported = compatibility["canProceed"] and bool(issues) and all(i["known"] for i in issues)
    return {
        "operation": "diagnose", "readOnly": True, "writeScope": "none",
        "compatibility": compatibility, "sourceStatus": report.get("status"),
        "decision": "REVIEW_EVIDENCE" if supported else "STOP",
        "repairStatus": "UNTESTED", "issues": issues,
        "nextStep": (
            "Check the listed evidence, propose the smallest scoped correction, then rerun Verify."
            if supported else
            "Obtain a complete report from the matching release; unknown evidence must not trigger repair."
        ),
        "sourceReport": copy.deepcopy(report),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dsh-crate diagnose")
    parser.add_argument("report", help="complete diagnostic JSON file")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = diagnose(json.loads(Path(args.report).read_text(encoding="utf-8")))
    except (OSError, ValueError) as error:
        result = {"operation": "diagnose", "readOnly": True, "decision": "STOP",
                  "repairStatus": "UNTESTED", "error": str(error)}
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Diagnosis: {result['decision']} (read-only)")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["decision"] == "REVIEW_EVIDENCE" else 1


if __name__ == "__main__":
    raise SystemExit(main())


def configure_parser(subparsers):
    parser = subparsers.add_parser("diagnose", help="read-only diagnosis from a complete report")
    parser.add_argument("report")
    parser.add_argument("--json", action="store_true")
    parser.set_defaults(handler=lambda args: main([args.report] + (["--json"] if args.json else [])))
