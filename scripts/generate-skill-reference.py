"""Generate the DSH Crate Troubleshooting Skill reference documents.

The code registry in ``core/dsh_pack/diagnostics.py`` is the single source of
truth for diagnostic codes and stages.  This script renders that registry into
Markdown reference files so the Skill never drifts from the Core.

Run from the repository root:

    python scripts/generate-skill-reference.py

The generated files are committed; CI runs this script and fails on drift.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.dsh_pack import diagnostics  # noqa: E402


def render_diagnostics(specs: dict[str, dict]) -> str:
    lines = [
        "# DSH Crate Diagnostic Codes",
        "",
        f"> Generated from `core/dsh_pack/diagnostics.py` (schema v{diagnostics.DIAGNOSTIC_SCHEMA_VERSION}, producer `{diagnostics.PRODUCER}`, crate {diagnostics.CRATE_VERSION}). Do not edit by hand.",
        "",
        f"Total codes: **{len(specs)}**. Stages: **{len(diagnostics.STAGE_SPECS)}**.",
        "",
        "| Code | Stage | Severity | Repair | Write scope | Verify after | Summary |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for code in sorted(specs):
        spec = specs[code]
        lines.append(
            "| `%s` | %s | %s | %s | %s | %s | %s |"
            % (
                code,
                spec.get("stage", "unknown"),
                spec.get("severity", "INFO"),
                spec.get("repairLevel", "L3"),
                spec.get("writeScope", "none"),
                "yes" if spec.get("verifyAfter") else "no",
                (spec.get("summary") or "").replace("|", "\\|"),
            )
        )
    lines.append("")
    lines.append("## Repair levels")
    lines.append("")
    lines.append("| Level | Meaning |")
    lines.append("| --- | --- |")
    lines.append("| L0 | No write needed; the diagnostic is advisory or the fix is already applied. |")
    lines.append("| L1 | Safe, reversible writes allowed without confirmation (see repair-boundaries.md). |")
    lines.append("| L2 | Writes that change the target Profile / environment; explicit user confirmation required. |")
    lines.append("| L3 | Never repair; unknown codes and credential-class issues are report-only. |")
    lines.append("")
    return "\n".join(lines)


def render_stages(stages: dict[str, dict]) -> str:
    lines = [
        "# DSH Crate Diagnostic Stages",
        "",
        f"> Generated from `core/dsh_pack/diagnostics.py` (schema v{diagnostics.DIAGNOSTIC_SCHEMA_VERSION}). Do not edit by hand.",
        "",
        "| Stage | Title | Description | Import state |",
        "| --- | --- | --- | --- |",
    ]
    for stage in sorted(stages):
        spec = stages[stage]
        lines.append(
            "| %s | %s | %s | %s |"
            % (
                stage,
                (spec.get("title") or "").replace("|", "\\|"),
                (spec.get("description") or "").replace("|", "\\|"),
                spec.get("importState", "unknown"),
            )
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    out_dir = ROOT / "skills" / "dsh-crate-troubleshooting" / "reference"
    out_dir.mkdir(parents=True, exist_ok=True)
    diagnostics_md = out_dir / "diagnostics.generated.md"
    stages_md = out_dir / "stages.generated.md"
    diagnostics_md.write_text(render_diagnostics(diagnostics.DIAGNOSTIC_SPECS), encoding="utf-8", newline="\n")
    stages_md.write_text(render_stages(diagnostics.STAGE_SPECS), encoding="utf-8", newline="\n")
    print(f"wrote {diagnostics_md}")
    print(f"wrote {stages_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
