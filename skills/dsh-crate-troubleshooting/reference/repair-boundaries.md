# Repair boundaries

What the DSH Crate Troubleshooting Skill may touch at each repair level.
This file is manually maintained policy and applies to every code in
`diagnostics.generated.md` that carries a repair level.

## L0 — Read only (automatic)

- Read the diagnostic, the Pack manifest, `plugins.lock.json`, `profile/` files, and integrity records.
- Inspect Profile state under DSH_HOME.
- Check whether files, packages, artifacts, ports, and processes exist.
- Read versions, manifests, stdout/stderr, and operation history.
- Never write anything.

## L1 — Safe repair (automatic)

Allowed without confirmation because it never changes the original environment's critical state:

- Clean up the failed temporary/scratch directory created by the Import that already failed.
- Re-run the read-only Preflight / Inspect to refresh evidence.
- Re-download a reference-only dependency from its recorded source (network) into the temporary Profile.
- Re-run Verify after an L1 action.
- Retry a transient install that failed on a network/timing issue, into the temporary Profile only.

L1 actions never touch:

- the original working Profile;
- credentials;
- committed Import targets;
- installed plugin versions in a committed Profile.

## L2 — Confirmation required

Must show the user the exact target and get explicit confirmation before writing:

- Overwrite an existing Profile (Import overwrite).
- Switch the active Profile.
- Restart the DSH runtime.
- Delete a Profile.
- Modify Profile configuration.
- Change an installed plugin version.
- Replace an embedded artifact.

## L3 — Never automatic (report only)

The Skill never performs, even with confirmation inside an automated flow:

- Modify credentials, tokens, cookies, passwords, private keys, or `Authorization` material.
- Delete or modify the original working Profile outside an explicitly confirmed operation.
- Modify unrelated Profiles.
- Modify DSH vendor source or the DSH Crate package itself.
- Lower the verification standard (FAIL -> WARNING) or fabricate a Verify PASS.

Unknown codes and unsupported versions default to L3 / no write.

## Defaults

- Unknown code -> repair level `L3`, write scope `none`.
- Missing envelope -> do not repair; request a matching diagnostic.
- Unsupported version/schema -> interpret evidence only; no automated repair.
