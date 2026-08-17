# DSH Crate Diagnostic Codes

> Generated from `core/dsh_pack/diagnostics.py` (schema v1, producer `dsh-crate`, crate 0.1.1). Do not edit by hand.

Total codes: **76**. Stages: **16**.

| Code | Stage | Severity | Repair | Write scope | Verify after | Summary |
| --- | --- | --- | --- | --- | --- | --- |
| `ACTIVE_PROFILE` | delete | BLOCKER | L2 | target-profile | yes | Cannot delete the active Profile. |
| `ARTIFACT_MEMBER_DUPLICATE` | embedded-install | BLOCKER | L1 | none | yes | Embedded artifact contains a duplicate member. |
| `ARTIFACT_MEMBER_READ_ERROR` | embedded-install | BLOCKER | L1 | none | yes | Embedded artifact member cannot be read. |
| `ARTIFACT_MEMBER_TYPE_INVALID` | embedded-install | BLOCKER | L1 | none | yes | Embedded artifact member type is invalid. |
| `ARTIFACT_PATH_INVALID` | embedded-install | BLOCKER | L1 | none | yes | Embedded artifact path is invalid. |
| `ARTIFACT_PATH_MISSING` | embedded-install | BLOCKER | L1 | none | yes | Embedded artifact path is missing. |
| `ARTIFACT_UNPACK_FAILED` | embedded-install | BLOCKER | L1 | temporary-profile | yes | Embedded artifact unpack failed. |
| `CONFLICT_BUNDLE_COMPOSITION` | composition | BLOCKER | L1 | target-profile | yes | Bundle composition conflict. |
| `CONFLICT_DUPLICATE_ARTIFACT` | composition | BLOCKER | L1 | none | yes | Duplicate plugin artifact. |
| `CONFLICT_DUPLICATE_BUNDLE_ORDER` | composition | BLOCKER | L1 | none | yes | Duplicate Bundle order. |
| `CRATE_VERSION_MISSING` | planning | BLOCKER | L1 | dsh-home | yes | DSH Crate package version is missing. |
| `DELETE_CONFIRMATION_REQUIRED` | delete | BLOCKER | L2 | target-profile | yes | Delete requires explicit confirmation. |
| `EMBEDDED_DEPENDENCIES_INSTALL_FAILED` | embedded-install | BLOCKER | L1 | temporary-profile | yes | Embedded dependency install failed. |
| `EMBEDDED_DEPENDENCIES_TIMEOUT` | embedded-install | BLOCKER | L1 | temporary-profile | yes | Embedded dependency install timed out. |
| `EMBEDDED_NPM_FAILED` | embedded-install | BLOCKER | L1 | temporary-profile | yes | Embedded npm install failed. |
| `EMBEDDED_NPM_UNAVAILABLE` | embedded-install | BLOCKER | L1 | temporary-profile | yes | npm is unavailable for embedded install. |
| `ENVIRONMENT_EXACT_MATCH` | environment | INFO | L0 | none | yes | Environment matches the source. |
| `ENVIRONMENT_OS_MISMATCH` | environment | WARNING | L0 | none | yes | Operating system differs from the source. |
| `ENVIRONMENT_VERSION_MISMATCH` | environment | WARNING | L0 | none | yes | Environment version differs from the source. |
| `FORMAT_ERROR` | preflight | BLOCKER | L1 | none | yes | Pack format is invalid. |
| `HASH_MISMATCH` | preflight | BLOCKER | L1 | none | yes | Pack hash mismatch. |
| `HASH_OR_INTEGRITY_ERROR` | preflight | BLOCKER | L1 | none | yes | Pack hash or integrity check failed. |
| `HEADLESS_RUNNER_FAILED` | runtime | BLOCKER | L1 | none | yes | Headless runtime failed. |
| `IMPORT_FAILED` | commit | BLOCKER | L1 | temporary-profile | yes | Import failed. |
| `INTEGRITY_FILE_MISSING` | preflight | BLOCKER | L1 | none | yes | Integrity record is missing. |
| `INTEGRITY_FILE_SET_MISMATCH` | preflight | BLOCKER | L1 | none | yes | Integrity file set does not match. |
| `NETWORK_INSTALL_FAILED` | network-install | BLOCKER | L1 | temporary-profile | yes | Network install failed. |
| `NETWORK_INSTALL_REQUIRED` | network-install | WARNING | L0 | none | yes | Network install will be required. |
| `NETWORK_INSTALL_TIMEOUT` | network-install | BLOCKER | L1 | temporary-profile | yes | Network install timed out. |
| `NETWORK_PACKAGE_MISSING` | network-install | BLOCKER | L1 | temporary-profile | yes | Network package is missing. |
| `NETWORK_SOURCE_UNSUPPORTED` | network-install | BLOCKER | L1 | temporary-profile | yes | Network source type is unsupported. |
| `OFFICIAL_BUNDLE_MISSING` | planning | BLOCKER | L1 | dsh-home | yes | Official DSH Bundle cannot be resolved. |
| `OPTIONAL_ARTIFACT_MISSING` | reference-install | WARNING | L0 | none | yes | Optional artifact is missing. |
| `OPTIONAL_PLUGIN_MISSING` | reference-install | WARNING | L0 | none | yes | Optional plugin is missing. |
| `OVERWRITE_CONFIRMATION_REQUIRED` | planning | BLOCKER | L2 | target-profile | yes | Overwrite requires explicit confirmation. |
| `OVERWRITE_MODE_REQUIRED` | planning | BLOCKER | L2 | target-profile | yes | Overwrite mode is required. |
| `PACKAGE_IDENTITY_DRIFT` | version-confirmation | BLOCKER | L1 | none | yes | Package identity drift. |
| `PACKAGE_MANIFEST_INVALID` | planning | BLOCKER | L1 | none | yes | Plugin package manifest is invalid. |
| `PACKAGE_NAME_INVALID` | planning | BLOCKER | L1 | none | yes | Plugin package name is invalid. |
| `PACK_READ_ERROR` | planning | BLOCKER | L1 | none | yes | Pack cannot be read. |
| `PLUGIN_INSTALL_FAILED` | reference-install | BLOCKER | L1 | temporary-profile | yes | Plugin install failed. |
| `PLUGIN_MISSING` | reference-install | BLOCKER | L1 | temporary-profile | yes | Plugin is missing after install. |
| `PLUGIN_SMOKE_FAILED` | plugin-smoke | BLOCKER | L1 | none | yes | Plugin smoke test failed. |
| `PLUGIN_SOURCE_MISSING` | reference-install | BLOCKER | L1 | temporary-profile | yes | Plugin source is missing. |
| `PLUGIN_SOURCE_UNSAFE` | reference-install | BLOCKER | L2 | target-profile | yes | Plugin source is unsafe. |
| `PLUGIN_TARGET_EXISTS` | configuration | BLOCKER | L2 | target-profile | yes | Plugin target directory already exists. |
| `PLUGIN_VERSION_MISMATCH` | version-confirmation | BLOCKER | L1 | temporary-profile | yes | Installed plugin version does not match the Pack. |
| `PREFLIGHT_BLOCKED` | preflight | BLOCKER | L1 | none | yes | Preflight found BLOCKER findings. |
| `PREFLIGHT_ERROR` | preflight | BLOCKER | L1 | none | yes | Preflight crashed. |
| `PROBE_FAILED` | probe | BLOCKER | L1 | none | yes | Runtime probe failed. |
| `PROFILE_CONFIG_MISSING` | configuration | BLOCKER | L1 | temporary-profile | yes | Profile configuration is missing. |
| `PROFILE_DELETE_FAILED` | delete | BLOCKER | L1 | target-profile | yes | Profile deletion failed. |
| `PROFILE_EXISTS` | planning | BLOCKER | L2 | target-profile | yes | Target Profile already exists. |
| `PROFILE_FILE_EXISTS` | configuration | BLOCKER | L2 | target-profile | yes | Target Profile file already exists. |
| `PROFILE_MISSING` | planning | BLOCKER | L1 | none | yes | Target Profile does not exist. |
| `PROFILE_NAME_INVALID` | planning | BLOCKER | L1 | none | yes | Profile name is invalid. |
| `PROFILE_NAME_MISSING` | planning | BLOCKER | L1 | none | yes | Profile name is missing. |
| `PROFILE_NAME_RESERVED` | planning | BLOCKER | L1 | none | yes | Profile name is reserved. |
| `PROFILE_NAME_UNAVAILABLE` | planning | BLOCKER | L1 | none | yes | Profile name is unavailable. |
| `PROFILE_NOT_FOUND` | delete | BLOCKER | L1 | none | yes | Profile not found. |
| `PROFILE_TARGET_INVALID` | planning | BLOCKER | L1 | none | yes | Import target is invalid. |
| `PROFILE_TARGET_MISSING` | planning | BLOCKER | L1 | none | yes | Import target is missing. |
| `REQUIRED_ARTIFACT_MISSING` | reference-install | BLOCKER | L1 | temporary-profile | yes | Required artifact is missing. |
| `RESTART_NOT_CONFIGURED` | restart | BLOCKER | L2 | environment | yes | DSH restart launcher is not configured. |
| `RESTART_PORT_NOT_RELEASED` | restart | BLOCKER | L2 | environment | yes | Port was not released after restart. |
| `RUNNER_EXITED_BEFORE_READY` | runtime | BLOCKER | L1 | none | yes | Runtime exited before ready. |
| `RUNNER_READY_REGEX_INVALID` | runtime | BLOCKER | L1 | temporary-profile | yes | Runtime readyRegex is invalid. |
| `RUNNER_READY_TIMEOUT` | runtime | BLOCKER | L1 | none | yes | Runtime ready timeout. |
| `RUNNER_SPAWN_FAILED` | runtime | BLOCKER | L1 | none | yes | Runtime command could not start. |
| `SCHEMA_ERROR` | preflight | BLOCKER | L1 | none | yes | Pack schema is unsupported. |
| `SECRET_MISSING` | planning | WARNING | L0 | none | yes | Required Secret is missing. |
| `SWITCH_CONFIRMATION_REQUIRED` | planning | BLOCKER | L2 | environment | yes | Profile switch requires explicit confirmation. |
| `VERSION_MISSING` | environment | WARNING | L0 | none | yes | A recorded version is missing. |
| `WEB_HTTP_STATUS_MISMATCH` | runtime | BLOCKER | L1 | none | yes | Web HTTP status does not match. |
| `WEB_HTTP_UNREACHABLE` | runtime | BLOCKER | L1 | none | yes | Web endpoint is unreachable. |
| `WEB_PORT_NOT_OWNED` | runtime | BLOCKER | L2 | environment | yes | Web port is not owned by the runtime. |

## Repair levels

| Level | Meaning |
| --- | --- |
| L0 | No write needed; the diagnostic is advisory or the fix is already applied. |
| L1 | Safe, reversible writes allowed without confirmation (see repair-boundaries.md). |
| L2 | Writes that change the target Profile / environment; explicit user confirmation required. |
| L3 | Never repair; unknown codes and credential-class issues are report-only. |
