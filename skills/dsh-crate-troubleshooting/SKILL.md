# DSH Crate Troubleshooting Skill

Version-aware troubleshooting for DSH Crate diagnostics.

This Skill ships with the same version as the DSH Crate release it supports.
The version compatibility contract lives in `compatibility.json`; the code
registry in `core/dsh_pack/diagnostics.py` is the single source of truth for
diagnostic codes and stages (rendered into `reference/diagnostics.generated.md`
and `reference/stages.generated.md` by `scripts/generate-skill-reference.py`).

## 0. Read first

1. `compatibility.json` — what this Skill version supports.
2. `reference/repair-boundaries.md` — what may be touched at each repair level.
3. `reference/diagnostics.generated.md` / `reference/stages.generated.md` —
   codes and stages this release knows.
4. The incoming diagnostic JSON — never guess what it contains.

## 1. Version Gate (always first)

Read the diagnostic envelope:

```json
{
  "producer": "dsh-crate",
  "crateVersion": "0.1.1",
  "diagnosticSchemaVersion": 1,
  "operation": "import",
  "operationId": "...",
  "status": "FAIL"
}
```

Classify with the compatibility contract:

- `FULL` — same Crate generation and a supported diagnostic schema; diagnose normally.
- `COMPATIBLE` — older Crate inside the supported range; use compatibility rules, do not assume newer-only behavior.
- `UNSUPPORTED` — Crate outside the supported range or an unsupported schema. You may interpret the raw evidence, but you MUST NOT apply version-related automatic repair. State clearly: `This diagnostic was produced by DSH Crate <x>, but this Troubleshooting Skill supports <range>. Update the Skill before applying automated repair.`

Missing envelope fields: treat as `UNSUPPORTED` with reason "diagnostic envelope is incomplete"; do not guess the missing values.

## 2. Identify the operation

Use `operation` (e.g. `import`, `export`, `inspect`, `verify`, `create-profile`, `delete-profile`, `switch-profile`). The operation tells you which end state was requested and therefore which "original state unchanged" guarantee applies.

## 3. Identify the failed stage

Look at the issue `stage` and the operation report. Confirm with evidence:

- which Pack file or Profile path is involved;
- which command was run (and its exit code / stdout / stderr);
- which plugin/artifact/item is the subject.

`reference/stages.generated.md` maps each stage to its meaning and Import state.

## 4. Collect evidence

Separate **fact** from **hypothesis**:

- Fact: envelope fields, `code`, `stage`, `item`, `expected`, `observed`, `evidence`, `stdout`/`stderr`, exit code, current file state, current Profile state.
- Hypothesis: anything you infer beyond the evidence. Label it explicitly.

Do not treat a missing check as a pass and do not invent evidence. If the diagnostic says `canContinue: false`, stopping is the correct behavior.

## 5. Match the known diagnostic

Look up `code` in `reference/diagnostics.generated.md`.

- Known code -> use the registry entry (severity, repair level, write scope, suggested checks).
- Unknown code -> `known: false`, repair level `L3`, write scope `none`. Report the code as unknown; never guess a fix.

## 6. Build a hypothesis

Only after evidence supports it:

1. Read the failing stage and its evidence.
2. List plausible causes (max 2-3) with the evidence each would need.
3. Run the cheapest read-only check that discriminates between them.
4. Proceed only when evidence points at one cause.

If evidence is insufficient, stop and request the missing evidence.

## 7. Select the minimum action

Choose the smallest write that addresses the confirmed cause. Respect the repair level:

- `L0` — read-only. Automatic.
- `L1` — safe reversible writes. Automatic; see `reference/repair-boundaries.md`.
- `L2` — must obtain explicit user confirmation before writing.
- `L3` — never automatic. Report only.

## 8. Respect the write boundary

Never:

- mutate credentials, tokens, cookies, passwords, private keys, or `Authorization` material;
- delete or modify the original working Profile except through an explicit confirmed operation;
- modify unrelated Profiles;
- modify DSH vendor source;
- lower the verification standard to clear an error (FAIL -> WARNING);
- fake a Verify PASS.

Scope every write to the target temporary Profile or the exact confirmed target, and record it.

## 9. Execute if allowed

Perform the L1/L2 action exactly as confirmed. If the action fails, do not paper over it: keep the operation `FAIL`, record the new evidence, and stop or request the next confirmed step.

## 10. Verify

Verification is the only arbiter of success:

- Re-run the DSH Crate `verify` for the affected Profile (web or headless mode as configured).
- `PASS` — report PASS with the verifying evidence.
- `FAIL` — report FAIL: "Repair did not resolve the original failure."
- If the affected capability cannot be verified, the result is `UNTESTED`, never PASS.

## 11. Report

Fixed structured output:

```text
Diagnosis
---------
Operation: <operation>
Stage: <stage>
Code: <code>
Severity: <severity>
Item: <item>
Known: yes/no

Evidence
--------
<facts and captured output>

Likely cause
------------
<evidence-backed cause>

Confidence
----------
High / Medium / Low

Action
------
<what was done, or what is proposed>

Write scope
-----------
<scope actually touched>

Verification
------------
PASS / FAIL / UNTESTED / PENDING
<evidence>
```

## 12. Stop conditions

Stop and hand back to the user when any of these hold:

- version gate is `UNSUPPORTED`;
- the code is unknown (L3);
- the required action is `L2`/`L3` without explicit confirmation;
- evidence is insufficient to choose a cause;
- a repair was attempted and verification still fails;
- the diagnostic says the operation is not allowed to continue.
