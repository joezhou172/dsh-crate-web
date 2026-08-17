"""Version-aware diagnostic protocol and Diagnostic Registry for DSH Crate.

Design (P7): the registry in this module is the single source of truth for the
diagnostic protocol:

- ``DIAGNOSTIC_SCHEMA_VERSION`` — generation of the diagnostic envelope.
- ``CRATE_VERSION`` — the DSH Crate version that produced the diagnostic.
- ``DIAGNOSTIC_SPECS`` — every known diagnostic code.
- ``STAGE_SPECS`` — every known failure stage.
- repair permission levels (L0..L3) and write scopes.

Reference documents under ``skills/dsh-crate-troubleshooting/reference/`` are
generated from this module by ``scripts/generate-skill-reference.py``; never
hand-edit generated files. The release workflow fails when the generated
reference is out of date (anti-drift).
"""

from __future__ import annotations

import re
from typing import Any, Mapping

from ._version import __version__ as CRATE_VERSION

DIAGNOSTIC_SCHEMA_VERSION = 1
PRODUCER = "dsh-crate"

# Repair permission levels (see skills/dsh-crate-troubleshooting/SKILL.md).
REPAIR_LEVEL_READ_ONLY = "L0"
REPAIR_LEVEL_SAFE = "L1"
REPAIR_LEVEL_CONFIRMATION = "L2"
REPAIR_LEVEL_FORBIDDEN = "L3"

# Write scopes used by repair recipes.
WRITE_SCOPE_NONE = "none"
WRITE_SCOPE_TEMPORARY_PROFILE = "temporary-profile"
WRITE_SCOPE_TARGET_PROFILE = "target-profile"
WRITE_SCOPE_ENVIRONMENT = "environment"
WRITE_SCOPE_DSH_HOME = "dsh-home"

SEVERITY_BLOCKER = "BLOCKER"
SEVERITY_WARNING = "WARNING"
SEVERITY_INFO = "INFO"

# ---------------------------------------------------------------------------
# Stages
# ---------------------------------------------------------------------------

STAGE_SPECS: dict[str, dict[str, Any]] = {
    "planning": {
        "title": "Plan",
        "description": "Operation planning: target Profile selection, name validation, pack read, and Import preview.",
        "importState": "planning",
    },
    "preflight": {
        "title": "Preflight",
        "description": "Read-only Inspect/Preflight of a Pack before any Profile change.",
        "importState": "preflight",
    },
    "configuration": {
        "title": "Configuration",
        "description": "Writing Pack profile configuration into the target Profile.",
        "importState": "configuration",
    },
    "embedded-install": {
        "title": "Embedded install",
        "description": "Installing an embedded plugin artifact (npm tarball) into the temporary Profile.",
        "importState": "embedded-install",
    },
    "reference-install": {
        "title": "Reference install",
        "description": "Installing or resolving a reference-only plugin source.",
        "importState": "reference-install",
    },
    "network-install": {
        "title": "Network install",
        "description": "Downloading and installing a recorded network package.",
        "importState": "network-install",
    },
    "version-confirmation": {
        "title": "Version confirmation",
        "description": "Confirming the installed package identity matches the Pack resolution.",
        "importState": "version-confirmation",
    },
    "composition": {
        "title": "Bundle composition",
        "description": "Composing Bundle patches and Loader rows for the Profile.",
        "importState": "composition",
    },
    "commit": {
        "title": "Commit",
        "description": "Committing the prepared Profile and metadata as a successful Import.",
        "importState": "commit",
    },
    "delete": {
        "title": "Delete",
        "description": "Deleting a non-running Profile after explicit confirmation.",
        "importState": "delete",
    },
    "restart": {
        "title": "Restart",
        "description": "Restarting DSH on the target Profile and port.",
        "importState": "restart",
    },
    "runtime": {
        "title": "Runtime boot",
        "description": "Starting the DSH runtime and waiting for a ready URL.",
        "importState": "runtime",
    },
    "probe": {
        "title": "Probe",
        "description": "Running a runtime capability probe after boot.",
        "importState": "probe",
    },
    "plugin-smoke": {
        "title": "Plugin smoke",
        "description": "Running a plugin-specific smoke test against the runtime.",
        "importState": "plugin-smoke",
    },
    "environment": {
        "title": "Environment",
        "description": "Environment compatibility findings (OS, Node, DSH versions).",
        "importState": "environment",
    },
    "surface": {
        "title": "Surface",
        "description": "Web surface or Bundle composition surface checks.",
        "importState": "surface",
    },
}


def _spec(
    *,
    stage: str,
    severity: str,
    summary: str,
    description: str,
    expected: str,
    impact: str,
    can_continue: bool,
    suggested_checks: list[str],
    repair_level: str,
    write_scope: str,
    verify_after: bool = True,
) -> dict[str, Any]:
    return {
        "stage": stage,
        "severity": severity,
        "summary": summary,
        "description": description,
        "expected": expected,
        "impact": impact,
        "canContinue": can_continue,
        "suggestedChecks": suggested_checks,
        "repairLevel": repair_level,
        "writeScope": write_scope,
        "verifyAfter": verify_after,
    }


def _checks(*items: str) -> list[str]:
    return list(items)
# ---------------------------------------------------------------------------
# Diagnostic code registry (single source of truth)
# ---------------------------------------------------------------------------

DIAGNOSTIC_SPECS: dict[str, dict[str, Any]] = {
    # --- Planning (web API) ---
    "PROFILE_NAME_RESERVED": _spec(
        stage="planning", severity=SEVERITY_BLOCKER,
        summary="Profile name is reserved.",
        description="The requested Profile name is reserved by DSH and cannot be used.",
        expected="the requested Profile name is available",
        impact="The requested Profile was not created.",
        can_continue=False,
        suggested_checks=_checks("choose another Profile name", "verify DSH reserved-name rules"),
        repair_level=REPAIR_LEVEL_SAFE, write_scope=WRITE_SCOPE_NONE,
    ),
    "PROFILE_EXISTS": _spec(
        stage="planning", severity=SEVERITY_BLOCKER,
        summary="Target Profile already exists.",
        description="A Profile with the requested name already exists in this DSH_HOME.",
        expected="the target Profile name is new or the overwrite is confirmed",
        impact="No Profile was created or modified.",
        can_continue=False,
        suggested_checks=_checks("choose a different Profile name", "delete the existing Profile first", "use explicit overwrite mode with confirmation"),
        repair_level=REPAIR_LEVEL_CONFIRMATION, write_scope=WRITE_SCOPE_TARGET_PROFILE,
    ),
    "PROFILE_MISSING": _spec(
        stage="planning", severity=SEVERITY_BLOCKER,
        summary="Target Profile does not exist.",
        description="The selected Profile does not exist in the current DSH_HOME.",
        expected="the selected Profile exists",
        impact="The operation was not applied.",
        can_continue=False,
        suggested_checks=_checks("verify the Profile name", "choose an existing Profile"),
        repair_level=REPAIR_LEVEL_SAFE, write_scope=WRITE_SCOPE_NONE,
    ),
    "OFFICIAL_BUNDLE_MISSING": _spec(
        stage="planning", severity=SEVERITY_BLOCKER,
        summary="Official DSH Bundle cannot be resolved.",
        description="An official DSH Bundle version could not be resolved for this Profile.",
        expected="the official DSH Bundles are installed in this DSH_HOME",
        impact="The requested Profile was not created.",
        can_continue=False,
        suggested_checks=_checks("install the official DSH bundles into this DSH_HOME", "verify the Bundle list", "retry after Bundle installation"),
        repair_level=REPAIR_LEVEL_SAFE, write_scope=WRITE_SCOPE_DSH_HOME,
    ),
    "CRATE_VERSION_MISSING": _spec(
        stage="planning", severity=SEVERITY_BLOCKER,
        summary="DSH Crate package version is missing.",
        description="The installed DSH Crate package does not expose its version, so the diagnostic protocol cannot stamp it.",
        expected="the DSH Crate installation exposes its package version",
        impact="The requested Profile was not created.",
        can_continue=False,
        suggested_checks=_checks("repair the DSH Crate installation", "reinstall dsh-crate-web and retry"),
        repair_level=REPAIR_LEVEL_SAFE, write_scope=WRITE_SCOPE_DSH_HOME,
    ),
    "ACTIVE_PROFILE": _spec(
        stage="delete", severity=SEVERITY_BLOCKER,
        summary="Cannot delete the active Profile.",
        description="The running DSH process uses this Profile; deleting it would break the running environment.",
        expected="the deleted Profile is not the active runtime Profile",
        impact="The running DSH process would lose its Profile files; deletion was refused.",
        can_continue=False,
        suggested_checks=_checks("switch to another Profile first", "then delete this Profile"),
        repair_level=REPAIR_LEVEL_CONFIRMATION, write_scope=WRITE_SCOPE_TARGET_PROFILE,
    ),
    "SWITCH_CONFIRMATION_REQUIRED": _spec(
        stage="planning", severity=SEVERITY_BLOCKER,
        summary="Profile switch requires explicit confirmation.",
        description="Switching the running Profile is a state-changing operation that requires the user to confirm.",
        expected="the user confirms the switch",
        impact="The current DSH process was not changed.",
        can_continue=False,
        suggested_checks=_checks("confirm the switch", "retry after confirmation"),
        repair_level=REPAIR_LEVEL_CONFIRMATION, write_scope=WRITE_SCOPE_ENVIRONMENT,
    ),
    "RESTART_NOT_CONFIGURED": _spec(
        stage="restart", severity=SEVERITY_BLOCKER,
        summary="DSH restart launcher is not configured.",
        description="The current DSH launch command cannot be safely reconstructed, so restart is refused.",
        expected="the current DSH launch command can be reconstructed",
        impact="The current DSH process was not changed.",
        can_continue=False,
        suggested_checks=_checks("start DSH with an explicit --profile and --port", "configure the DSH Crate restart launcher"),
        repair_level=REPAIR_LEVEL_CONFIRMATION, write_scope=WRITE_SCOPE_ENVIRONMENT,
    ),

    # --- Import planning / prepare ---
    "PROFILE_NAME_MISSING": _spec(
        stage="planning", severity=SEVERITY_BLOCKER,
        summary="Profile name is missing.",
        description="The Pack or request did not provide a target Profile name.",
        expected="a target Profile name is provided",
        impact="Import did not start and no Profile was changed.",
        can_continue=False,
        suggested_checks=_checks("provide a target Profile name", "review the Import preview"),
        repair_level=REPAIR_LEVEL_SAFE, write_scope=WRITE_SCOPE_NONE,
    ),
    "PROFILE_NAME_INVALID": _spec(
        stage="planning", severity=SEVERITY_BLOCKER,
        summary="Profile name is invalid.",
        description="The target Profile name does not satisfy DSH naming rules.",
        expected="the Profile name is valid",
        impact="Import did not start and no Profile was changed.",
        can_continue=False,
        suggested_checks=_checks("use a valid Profile name", "review the Import preview"),
        repair_level=REPAIR_LEVEL_SAFE, write_scope=WRITE_SCOPE_NONE,
    ),
    "PROFILE_NAME_UNAVAILABLE": _spec(
        stage="planning", severity=SEVERITY_BLOCKER,
        summary="Profile name is unavailable.",
        description="The requested Profile name cannot be used in this DSH_HOME.",
        expected="the requested Profile name is available",
        impact="Import did not start and no Profile was changed.",
        can_continue=False,
        suggested_checks=_checks("choose a different Profile name", "review the Import preview"),
        repair_level=REPAIR_LEVEL_SAFE, write_scope=WRITE_SCOPE_NONE,
    ),
    "PROFILE_TARGET_INVALID": _spec(
        stage="planning", severity=SEVERITY_BLOCKER,
        summary="Import target is invalid.",
        description="The import target Profile configuration is invalid.",
        expected="the target Profile is valid",
        impact="Import did not start and no Profile was changed.",
        can_continue=False,
        suggested_checks=_checks("review the target Profile settings", "correct the target and retry"),
        repair_level=REPAIR_LEVEL_SAFE, write_scope=WRITE_SCOPE_NONE,
    ),
    "PROFILE_TARGET_MISSING": _spec(
        stage="planning", severity=SEVERITY_BLOCKER,
        summary="Import target is missing.",
        description="No target Profile was selected for the Import.",
        expected="a target Profile is selected",
        impact="Import did not start and no Profile was changed.",
        can_continue=False,
        suggested_checks=_checks("select a target Profile", "retry"),
        repair_level=REPAIR_LEVEL_SAFE, write_scope=WRITE_SCOPE_NONE,
    ),
    "PACKAGE_NAME_INVALID": _spec(
        stage="planning", severity=SEVERITY_BLOCKER,
        summary="Plugin package name is invalid.",
        description="A plugin package name recorded in the Pack is not a valid npm package name.",
        expected="every plugin package name is valid",
        impact="Import did not start and no Profile was changed.",
        can_continue=False,
        suggested_checks=_checks("verify the Pack plugin identity", "re-export the Pack with a valid name"),
        repair_level=REPAIR_LEVEL_SAFE, write_scope=WRITE_SCOPE_NONE,
    ),
    "PACKAGE_MANIFEST_INVALID": _spec(
        stage="planning", severity=SEVERITY_BLOCKER,
        summary="Plugin package manifest is invalid.",
        description="A plugin package.json inside the Pack is unreadable or malformed.",
        expected="every plugin package.json is valid",
        impact="Import did not start and no Profile was changed.",
        can_continue=False,
        suggested_checks=_checks("verify the Pack manifest", "re-export the Pack"),
        repair_level=REPAIR_LEVEL_SAFE, write_scope=WRITE_SCOPE_NONE,
    ),
    "PACK_READ_ERROR": _spec(
        stage="planning", severity=SEVERITY_BLOCKER,
        summary="Pack cannot be read.",
        description="The .dshcrate file could not be read or parsed.",
        expected="the Pack is readable",
        impact="Import did not start and no Profile was changed.",
        can_continue=False,
        suggested_checks=_checks("verify the Pack file is not corrupt", "re-download or re-export the Pack"),
        repair_level=REPAIR_LEVEL_SAFE, write_scope=WRITE_SCOPE_NONE,
    ),
    "PREFLIGHT_ERROR": _spec(
        stage="preflight", severity=SEVERITY_BLOCKER,
        summary="Preflight crashed.",
        description="Preflight raised an unexpected error while inspecting the Pack.",
        expected="Preflight completes",
        impact="Inspect/Preflight could not finish.",
        can_continue=False,
        suggested_checks=_checks("inspect the Preflight error evidence", "retry Inspect"),
        repair_level=REPAIR_LEVEL_SAFE, write_scope=WRITE_SCOPE_NONE,
    ),
    "PREFLIGHT_BLOCKED": _spec(
        stage="preflight", severity=SEVERITY_BLOCKER,
        summary="Preflight found BLOCKER findings.",
        description="The Pack cannot be imported because Preflight reported blocking findings.",
        expected="no BLOCKER findings",
        impact="Import is not allowed until the BLOCKER findings are resolved.",
        can_continue=False,
        suggested_checks=_checks("open the Preflight findings", "resolve every BLOCKER", "re-run Inspect/Preflight"),
        repair_level=REPAIR_LEVEL_SAFE, write_scope=WRITE_SCOPE_NONE,
    ),
    "PROFILE_CONFIG_MISSING": _spec(
        stage="configuration", severity=SEVERITY_BLOCKER,
        summary="Profile configuration is missing.",
        description="The Pack did not record the Profile configuration that the target needs.",
        expected="the Pack records Profile configuration",
        impact="The new Profile could not be fully configured.",
        can_continue=False,
        suggested_checks=_checks("inspect the Profile configuration files", "re-export the Pack with configuration"),
        repair_level=REPAIR_LEVEL_SAFE, write_scope=WRITE_SCOPE_TEMPORARY_PROFILE,
    ),
    "PROFILE_FILE_EXISTS": _spec(
        stage="configuration", severity=SEVERITY_BLOCKER,
        summary="Target Profile file already exists.",
        description="A configuration file the Pack needs to write already exists in the target Profile.",
        expected="the target Profile is empty or overwrite is confirmed",
        impact="The new Profile could not be fully configured.",
        can_continue=False,
        suggested_checks=_checks("inspect the conflicting file", "choose a new Profile or confirm overwrite"),
        repair_level=REPAIR_LEVEL_CONFIRMATION, write_scope=WRITE_SCOPE_TARGET_PROFILE,
    ),
    "PLUGIN_TARGET_EXISTS": _spec(
        stage="configuration", severity=SEVERITY_BLOCKER,
        summary="Plugin target directory already exists.",
        description="The plugin install location already contains content.",
        expected="the plugin target directory is available",
        impact="The plugin could not be placed into the target Profile.",
        can_continue=False,
        suggested_checks=_checks("inspect the plugin target directory", "choose a new Profile or confirm overwrite"),
        repair_level=REPAIR_LEVEL_CONFIRMATION, write_scope=WRITE_SCOPE_TARGET_PROFILE,
    ),
    # --- Embedded install ---
    "ARTIFACT_PATH_INVALID": _spec(
        stage="embedded-install", severity=SEVERITY_BLOCKER,
        summary="Embedded artifact path is invalid.",
        description="The embedded artifact path recorded in the Pack is unsafe or invalid.",
        expected="the artifact path is safe and valid",
        impact="An embedded package was not installed.",
        can_continue=False,
        suggested_checks=_checks("verify the artifact path", "re-export the Pack with a valid artifact"),
        repair_level=REPAIR_LEVEL_SAFE, write_scope=WRITE_SCOPE_NONE,
    ),
    "ARTIFACT_PATH_MISSING": _spec(
        stage="embedded-install", severity=SEVERITY_BLOCKER,
        summary="Embedded artifact path is missing.",
        description="The Pack declares an embedded artifact but does not record where it is.",
        expected="the artifact path is recorded",
        impact="An embedded package was not installed.",
        can_continue=False,
        suggested_checks=_checks("verify the Pack artifact records", "re-export the Pack"),
        repair_level=REPAIR_LEVEL_SAFE, write_scope=WRITE_SCOPE_NONE,
    ),
    "ARTIFACT_MEMBER_DUPLICATE": _spec(
        stage="embedded-install", severity=SEVERITY_BLOCKER,
        summary="Embedded artifact contains a duplicate member.",
        description="The embedded tarball contains the same logical member more than once.",
        expected="every archive member appears once",
        impact="An embedded package was not installed.",
        can_continue=False,
        suggested_checks=_checks("verify the embedded tarball", "re-export the Pack"),
        repair_level=REPAIR_LEVEL_SAFE, write_scope=WRITE_SCOPE_NONE,
    ),
    "ARTIFACT_MEMBER_TYPE_INVALID": _spec(
        stage="embedded-install", severity=SEVERITY_BLOCKER,
        summary="Embedded artifact member type is invalid.",
        description="The embedded tarball contains an unsupported member type (for example a hardlink or symlink).",
        expected="all archive members are regular files or directories",
        impact="An embedded package was not installed.",
        can_continue=False,
        suggested_checks=_checks("verify the embedded tarball members", "re-export the Pack"),
        repair_level=REPAIR_LEVEL_SAFE, write_scope=WRITE_SCOPE_NONE,
    ),
    "ARTIFACT_MEMBER_READ_ERROR": _spec(
        stage="embedded-install", severity=SEVERITY_BLOCKER,
        summary="Embedded artifact member cannot be read.",
        description="A member of the embedded tarball could not be read from the archive.",
        expected="all archive members are readable",
        impact="An embedded package was not installed.",
        can_continue=False,
        suggested_checks=_checks("verify the embedded tarball integrity", "re-export the Pack"),
        repair_level=REPAIR_LEVEL_SAFE, write_scope=WRITE_SCOPE_NONE,
    ),
    "ARTIFACT_UNPACK_FAILED": _spec(
        stage="embedded-install", severity=SEVERITY_BLOCKER,
        summary="Embedded artifact unpack failed.",
        description="The embedded tarball could not be unpacked into the temporary Profile.",
        expected="the embedded artifact unpacks successfully",
        impact="An embedded package was not installed.",
        can_continue=False,
        suggested_checks=_checks("verify the embedded tarball", "check disk space and permissions"),
        repair_level=REPAIR_LEVEL_SAFE, write_scope=WRITE_SCOPE_TEMPORARY_PROFILE,
    ),
    "EMBEDDED_NPM_UNAVAILABLE": _spec(
        stage="embedded-install", severity=SEVERITY_BLOCKER,
        summary="npm is unavailable for embedded install.",
        description="npm could not be located or executed while installing embedded dependencies.",
        expected="npm is available",
        impact="Embedded plugin dependencies were not installed.",
        can_continue=False,
        suggested_checks=_checks("verify npm is on PATH", "reinstall Node/npm and retry"),
        repair_level=REPAIR_LEVEL_SAFE, write_scope=WRITE_SCOPE_TEMPORARY_PROFILE,
    ),
    "EMBEDDED_NPM_FAILED": _spec(
        stage="embedded-install", severity=SEVERITY_BLOCKER,
        summary="Embedded npm install failed.",
        description="npm exited with a non-zero code while installing embedded dependencies.",
        expected="npm install exits 0",
        impact="Embedded plugin dependencies were not installed.",
        can_continue=False,
        suggested_checks=_checks("inspect the npm stdout/stderr evidence", "check network and registry access"),
        repair_level=REPAIR_LEVEL_SAFE, write_scope=WRITE_SCOPE_TEMPORARY_PROFILE,
    ),
    "EMBEDDED_DEPENDENCIES_TIMEOUT": _spec(
        stage="embedded-install", severity=SEVERITY_BLOCKER,
        summary="Embedded dependency install timed out.",
        description="Installing embedded dependencies exceeded the configured timeout.",
        expected="embedded dependency install completes in time",
        impact="Embedded plugin dependencies were not installed.",
        can_continue=False,
        suggested_checks=_checks("check network latency", "retry with a longer timeout"),
        repair_level=REPAIR_LEVEL_SAFE, write_scope=WRITE_SCOPE_TEMPORARY_PROFILE,
    ),
    "EMBEDDED_DEPENDENCIES_INSTALL_FAILED": _spec(
        stage="embedded-install", severity=SEVERITY_BLOCKER,
        summary="Embedded dependency install failed.",
        description="Installing an embedded plugin artifact failed with a non-zero exit code.",
        expected="install a valid embedded artifact",
        impact="Import stopped during embedded-install; the temporary Profile was cleaned.",
        can_continue=False,
        suggested_checks=_checks("verify the embedded artifact SHA-256 against the Pack lock", "confirm the artifact is a valid npm tarball", "check the npm stdout/stderr evidence"),
        repair_level=REPAIR_LEVEL_SAFE, write_scope=WRITE_SCOPE_TEMPORARY_PROFILE,
    ),
    # --- Reference / network install ---
    "PLUGIN_SOURCE_MISSING": _spec(
        stage="reference-install", severity=SEVERITY_BLOCKER,
        summary="Plugin source is missing.",
        description="The reference-only plugin source recorded in the Pack cannot be resolved.",
        expected="the plugin source is resolvable",
        impact="A reference-only package was not installed.",
        can_continue=False,
        suggested_checks=_checks("provide the exact reference source", "verify the source still exists", "retry Import"),
        repair_level=REPAIR_LEVEL_SAFE, write_scope=WRITE_SCOPE_TEMPORARY_PROFILE,
    ),
    "PLUGIN_SOURCE_UNSAFE": _spec(
        stage="reference-install", severity=SEVERITY_BLOCKER,
        summary="Plugin source is unsafe.",
        description="The reference-only plugin source uses an unsafe or unsupported source type.",
        expected="the plugin source is safe and supported",
        impact="The plugin was not installed from the unsafe source.",
        can_continue=False,
        suggested_checks=_checks("review the source type", "choose an embedded artifact or a supported source"),
        repair_level=REPAIR_LEVEL_CONFIRMATION, write_scope=WRITE_SCOPE_TARGET_PROFILE,
    ),
    "PLUGIN_INSTALL_FAILED": _spec(
        stage="reference-install", severity=SEVERITY_BLOCKER,
        summary="Plugin install failed.",
        description="Installing the reference-only plugin failed.",
        expected="the plugin installs successfully",
        impact="A reference-only package was not installed.",
        can_continue=False,
        suggested_checks=_checks("inspect the install stdout/stderr", "verify the source and version", "retry Import"),
        repair_level=REPAIR_LEVEL_SAFE, write_scope=WRITE_SCOPE_TEMPORARY_PROFILE,
    ),
    "PLUGIN_MISSING": _spec(
        stage="reference-install", severity=SEVERITY_BLOCKER,
        summary="Plugin is missing after install.",
        description="The plugin is not present after the install step.",
        expected="the plugin is present after install",
        impact="The plugin could not be placed into the target Profile.",
        can_continue=False,
        suggested_checks=_checks("verify the install command completed", "inspect the plugin directory"),
        repair_level=REPAIR_LEVEL_SAFE, write_scope=WRITE_SCOPE_TEMPORARY_PROFILE,
    ),
    "PLUGIN_VERSION_MISMATCH": _spec(
        stage="version-confirmation", severity=SEVERITY_BLOCKER,
        summary="Installed plugin version does not match the Pack.",
        description="The installed plugin version does not satisfy the Pack resolution identity.",
        expected="the installed package version matches the Pack resolution",
        impact="Import stopped during version confirmation.",
        can_continue=False,
        suggested_checks=_checks("provide an artifact or source with the Pack resolution version", "re-export the Pack with the resolved version"),
        repair_level=REPAIR_LEVEL_SAFE, write_scope=WRITE_SCOPE_TEMPORARY_PROFILE,
    ),
    "REQUIRED_ARTIFACT_MISSING": _spec(
        stage="reference-install", severity=SEVERITY_BLOCKER,
        summary="Required artifact is missing.",
        description="A required plugin artifact recorded in the Pack is not present and cannot be resolved.",
        expected="every required artifact is available",
        impact="Import cannot continue without the required artifact.",
        can_continue=False,
        suggested_checks=_checks("verify the required artifact record", "provide the artifact or re-export the Pack"),
        repair_level=REPAIR_LEVEL_SAFE, write_scope=WRITE_SCOPE_TEMPORARY_PROFILE,
    ),
    "NETWORK_SOURCE_UNSUPPORTED": _spec(
        stage="network-install", severity=SEVERITY_BLOCKER,
        summary="Network source type is unsupported.",
        description="The Pack records a network source type the installed Core does not support.",
        expected="the network source type is supported",
        impact="The network package was not installed.",
        can_continue=False,
        suggested_checks=_checks("verify the Pack source type", "use an embedded artifact instead"),
        repair_level=REPAIR_LEVEL_SAFE, write_scope=WRITE_SCOPE_TEMPORARY_PROFILE,
    ),
    "NETWORK_INSTALL_FAILED": _spec(
        stage="network-install", severity=SEVERITY_BLOCKER,
        summary="Network install failed.",
        description="npm install of the recorded network package failed.",
        expected="npm install exits 0",
        impact="The network package was not installed into the temporary Profile.",
        can_continue=False,
        suggested_checks=_checks("check npm registry and network reachability", "verify the recorded package version exists", "retry"),
        repair_level=REPAIR_LEVEL_SAFE, write_scope=WRITE_SCOPE_TEMPORARY_PROFILE,
    ),
    "NETWORK_INSTALL_TIMEOUT": _spec(
        stage="network-install", severity=SEVERITY_BLOCKER,
        summary="Network install timed out.",
        description="npm install of the recorded network package exceeded the timeout.",
        expected="npm install completes in time",
        impact="The network package was not installed into the temporary Profile.",
        can_continue=False,
        suggested_checks=_checks("check network latency", "retry with a longer timeout", "or provide an embedded artifact"),
        repair_level=REPAIR_LEVEL_SAFE, write_scope=WRITE_SCOPE_TEMPORARY_PROFILE,
    ),
    "NETWORK_PACKAGE_MISSING": _spec(
        stage="network-install", severity=SEVERITY_BLOCKER,
        summary="Network package is missing.",
        description="The recorded network package could not be found after install.",
        expected="the network package is present after install",
        impact="The network package was not installed into the temporary Profile.",
        can_continue=False,
        suggested_checks=_checks("verify the package name and version", "check the registry response"),
        repair_level=REPAIR_LEVEL_SAFE, write_scope=WRITE_SCOPE_TEMPORARY_PROFILE,
    ),
    # --- Overwrite / delete ---
    "OVERWRITE_CONFIRMATION_REQUIRED": _spec(
        stage="planning", severity=SEVERITY_BLOCKER,
        summary="Overwrite requires explicit confirmation.",
        description="Importing over an existing Profile requires the user to confirm before anything is written.",
        expected="the user confirms the overwrite",
        impact="No Profile was written.",
        can_continue=False,
        suggested_checks=_checks("confirm the overwrite target", "retry after confirmation"),
        repair_level=REPAIR_LEVEL_CONFIRMATION, write_scope=WRITE_SCOPE_TARGET_PROFILE,
    ),
    "OVERWRITE_MODE_REQUIRED": _spec(
        stage="planning", severity=SEVERITY_BLOCKER,
        summary="Overwrite mode is required.",
        description="The Import targets an existing Profile but overwrite mode was not selected.",
        expected="overwrite mode is selected for an existing target",
        impact="No Profile was written.",
        can_continue=False,
        suggested_checks=_checks("select overwrite mode", "or choose a new Profile name"),
        repair_level=REPAIR_LEVEL_CONFIRMATION, write_scope=WRITE_SCOPE_TARGET_PROFILE,
    ),
    "DELETE_CONFIRMATION_REQUIRED": _spec(
        stage="delete", severity=SEVERITY_BLOCKER,
        summary="Delete requires explicit confirmation.",
        description="Deleting a Profile is destructive and requires the user to confirm.",
        expected="the user confirms the deletion",
        impact="The Profile was not deleted.",
        can_continue=False,
        suggested_checks=_checks("confirm the deletion", "retry after confirmation"),
        repair_level=REPAIR_LEVEL_CONFIRMATION, write_scope=WRITE_SCOPE_TARGET_PROFILE,
    ),
    "PROFILE_NOT_FOUND": _spec(
        stage="delete", severity=SEVERITY_BLOCKER,
        summary="Profile not found.",
        description="The Profile selected for deletion does not exist.",
        expected="the Profile exists",
        impact="The Profile was not deleted.",
        can_continue=False,
        suggested_checks=_checks("verify the Profile name", "refresh the Profile list"),
        repair_level=REPAIR_LEVEL_SAFE, write_scope=WRITE_SCOPE_NONE,
    ),
    "PROFILE_DELETE_FAILED": _spec(
        stage="delete", severity=SEVERITY_BLOCKER,
        summary="Profile deletion failed.",
        description="Deleting the Profile failed (for example an OS error).",
        expected="the Profile is deleted",
        impact="The Profile was not deleted.",
        can_continue=False,
        suggested_checks=_checks("check file permissions and locks", "inspect the delete evidence"),
        repair_level=REPAIR_LEVEL_SAFE, write_scope=WRITE_SCOPE_TARGET_PROFILE,
    ),
    "IMPORT_FAILED": _spec(
        stage="commit", severity=SEVERITY_BLOCKER,
        summary="Import failed.",
        description="The Import operation failed; the target and temporary Profiles are cleaned.",
        expected="Import commits a prepared Profile",
        impact="Import stopped; no half-written Profile remains.",
        can_continue=False,
        suggested_checks=_checks("open the failure diagnostic", "correct the reported item", "retry Import"),
        repair_level=REPAIR_LEVEL_SAFE, write_scope=WRITE_SCOPE_TEMPORARY_PROFILE,
    ),

    # --- Verify / runtime ---
    "RUNNER_SPAWN_FAILED": _spec(
        stage="runtime", severity=SEVERITY_BLOCKER,
        summary="Runtime command could not start.",
        description="The runtime command could not be spawned during Verify.",
        expected="the runtime command starts and prints a ready URL",
        impact="DSH runtime could not be started for verification.",
        can_continue=False,
        suggested_checks=_checks("inspect the spawn error", "verify the runtime command and PATH"),
        repair_level=REPAIR_LEVEL_SAFE, write_scope=WRITE_SCOPE_NONE,
    ),
    "RUNNER_READY_REGEX_INVALID": _spec(
        stage="runtime", severity=SEVERITY_BLOCKER,
        summary="Runtime readyRegex is invalid.",
        description="The Verify runner readyRegex is not a valid regular expression.",
        expected="the readyRegex compiles",
        impact="Runtime readiness cannot be detected.",
        can_continue=False,
        suggested_checks=_checks("correct the readyRegex in the Verify configuration", "re-run Verify"),
        repair_level=REPAIR_LEVEL_SAFE, write_scope=WRITE_SCOPE_TEMPORARY_PROFILE,
    ),
    "RUNNER_EXITED_BEFORE_READY": _spec(
        stage="runtime", severity=SEVERITY_BLOCKER,
        summary="Runtime exited before ready.",
        description="The runtime process exited before printing a ready URL.",
        expected="the runtime process stays alive and prints a ready URL",
        impact="The imported Profile cannot boot in the target DSH runtime.",
        can_continue=False,
        suggested_checks=_checks("read the runtime stdout/stderr evidence", "verify the Profile composition and dependencies"),
        repair_level=REPAIR_LEVEL_SAFE, write_scope=WRITE_SCOPE_NONE,
    ),
    "RUNNER_READY_TIMEOUT": _spec(
        stage="runtime", severity=SEVERITY_BLOCKER,
        summary="Runtime ready timeout.",
        description="The runtime did not print a ready URL before the configured timeout.",
        expected="the runtime prints a ready URL within the configured timeout",
        impact="DSH readiness could not be confirmed within the timeout.",
        can_continue=False,
        suggested_checks=_checks("inspect the runtime logs", "verify the port is free", "increase the timeout or fix boot"),
        repair_level=REPAIR_LEVEL_SAFE, write_scope=WRITE_SCOPE_NONE,
    ),
    "HEADLESS_RUNNER_FAILED": _spec(
        stage="runtime", severity=SEVERITY_BLOCKER,
        summary="Headless runtime failed.",
        description="The headless runtime command failed to complete or exited with a failure.",
        expected="the headless runtime command completes successfully",
        impact="The imported Profile could not be verified in headless mode.",
        can_continue=False,
        suggested_checks=_checks("inspect the headless stdout/stderr", "verify the Profile composition"),
        repair_level=REPAIR_LEVEL_SAFE, write_scope=WRITE_SCOPE_NONE,
    ),
    "WEB_HTTP_STATUS_MISMATCH": _spec(
        stage="runtime", severity=SEVERITY_BLOCKER,
        summary="Web HTTP status does not match.",
        description="The web endpoint returned an HTTP status that does not match the expected status.",
        expected="the web endpoint returns the expected HTTP status",
        impact="Web readiness could not be confirmed.",
        can_continue=False,
        suggested_checks=_checks("check the returned status code", "verify the web server started"),
        repair_level=REPAIR_LEVEL_SAFE, write_scope=WRITE_SCOPE_NONE,
    ),
    "WEB_HTTP_UNREACHABLE": _spec(
        stage="runtime", severity=SEVERITY_BLOCKER,
        summary="Web endpoint is unreachable.",
        description="The web endpoint did not respond while the runtime is running.",
        expected="the web endpoint is reachable",
        impact="Web readiness could not be confirmed.",
        can_continue=False,
        suggested_checks=_checks("verify the URL and port", "check firewall and process state"),
        repair_level=REPAIR_LEVEL_SAFE, write_scope=WRITE_SCOPE_NONE,
    ),
    "WEB_PORT_NOT_OWNED": _spec(
        stage="runtime", severity=SEVERITY_BLOCKER,
        summary="Web port is not owned by the runtime.",
        description="The expected web port is not owned by the started runtime process.",
        expected="the runtime process owns the configured port",
        impact="Web readiness could not be confirmed on the expected port.",
        can_continue=False,
        suggested_checks=_checks("check which process owns the port", "free the port or use a different port", "restart DSH"),
        repair_level=REPAIR_LEVEL_CONFIRMATION, write_scope=WRITE_SCOPE_ENVIRONMENT,
    ),
    "RESTART_PORT_NOT_RELEASED": _spec(
        stage="restart", severity=SEVERITY_BLOCKER,
        summary="Port was not released after restart.",
        description="The old DSH process did not release the port before the new process started.",
        expected="the old process releases the port",
        impact="The restarted DSH could not bind the expected port.",
        can_continue=False,
        suggested_checks=_checks("verify the old process exited", "free the port manually", "restart again"),
        repair_level=REPAIR_LEVEL_CONFIRMATION, write_scope=WRITE_SCOPE_ENVIRONMENT,
    ),
    "PROBE_FAILED": _spec(
        stage="probe", severity=SEVERITY_BLOCKER,
        summary="Runtime probe failed.",
        description="A runtime capability probe command failed to complete or exited with a failure.",
        expected="the probe command completes successfully",
        impact="The runtime capability could not be verified.",
        can_continue=False,
        suggested_checks=_checks("inspect the probe stdout/stderr", "verify the probed capability"),
        repair_level=REPAIR_LEVEL_SAFE, write_scope=WRITE_SCOPE_NONE,
    ),
    "PLUGIN_SMOKE_FAILED": _spec(
        stage="plugin-smoke", severity=SEVERITY_BLOCKER,
        summary="Plugin smoke test failed.",
        description="A plugin-specific smoke test failed against the runtime.",
        expected="the plugin smoke test passes",
        impact="The plugin business function could not be verified.",
        can_continue=False,
        suggested_checks=_checks("inspect the smoke test output", "verify the plugin is active", "check plugin external dependencies"),
        repair_level=REPAIR_LEVEL_SAFE, write_scope=WRITE_SCOPE_NONE,
    ),
    # --- Preflight findings ---
    "SCHEMA_ERROR": _spec(
        stage="preflight", severity=SEVERITY_BLOCKER,
        summary="Pack schema is unsupported.",
        description="The Pack manifest schema version is not supported by this Core.",
        expected="the Pack schema version is supported",
        impact="The Pack cannot be interpreted.",
        can_continue=False,
        suggested_checks=_checks("verify the Pack schemaVersion", "use a matching DSH Crate version"),
        repair_level=REPAIR_LEVEL_SAFE, write_scope=WRITE_SCOPE_NONE,
    ),
    "FORMAT_ERROR": _spec(
        stage="preflight", severity=SEVERITY_BLOCKER,
        summary="Pack format is invalid.",
        description="The Pack container or required members are invalid.",
        expected="the Pack format is valid",
        impact="The Pack cannot be read.",
        can_continue=False,
        suggested_checks=_checks("verify the Pack file", "re-export the Pack"),
        repair_level=REPAIR_LEVEL_SAFE, write_scope=WRITE_SCOPE_NONE,
    ),
    "INTEGRITY_FILE_MISSING": _spec(
        stage="preflight", severity=SEVERITY_BLOCKER,
        summary="Integrity record is missing.",
        description="A required integrity record is missing from the Pack.",
        expected="all integrity records are present",
        impact="The Pack integrity cannot be verified.",
        can_continue=False,
        suggested_checks=_checks("verify the Pack integrity records", "re-export the Pack"),
        repair_level=REPAIR_LEVEL_SAFE, write_scope=WRITE_SCOPE_NONE,
    ),
    "INTEGRITY_FILE_SET_MISMATCH": _spec(
        stage="preflight", severity=SEVERITY_BLOCKER,
        summary="Integrity file set does not match.",
        description="The set of files covered by the integrity records does not match the Pack contents.",
        expected="the integrity file set matches the Pack contents",
        impact="The Pack integrity cannot be verified.",
        can_continue=False,
        suggested_checks=_checks("verify the Pack file set", "re-export the Pack"),
        repair_level=REPAIR_LEVEL_SAFE, write_scope=WRITE_SCOPE_NONE,
    ),
    "HASH_OR_INTEGRITY_ERROR": _spec(
        stage="preflight", severity=SEVERITY_BLOCKER,
        summary="Pack hash or integrity check failed.",
        description="A declared hash or integrity record does not match the Pack contents.",
        expected="every declared hash matches the Pack contents",
        impact="The Pack is not accepted as-is.",
        can_continue=False,
        suggested_checks=_checks("verify the affected hash", "re-export the Pack"),
        repair_level=REPAIR_LEVEL_SAFE, write_scope=WRITE_SCOPE_NONE,
    ),
    "HASH_MISMATCH": _spec(
        stage="preflight", severity=SEVERITY_BLOCKER,
        summary="Pack hash mismatch.",
        description="A specific hash record does not match the Pack contents.",
        expected="the hash matches the Pack contents",
        impact="The Pack is not accepted as-is.",
        can_continue=False,
        suggested_checks=_checks("verify the affected hash", "re-export the Pack"),
        repair_level=REPAIR_LEVEL_SAFE, write_scope=WRITE_SCOPE_NONE,
    ),
    "CONFLICT_BUNDLE_COMPOSITION": _spec(
        stage="composition", severity=SEVERITY_BLOCKER,
        summary="Bundle composition conflict.",
        description="The Bundle composition duplicates or conflicts on a Loader row.",
        expected="every Loader row is unique and composable",
        impact="The Profile Bundle composition cannot boot.",
        can_continue=False,
        suggested_checks=_checks("review the Bundle order", "remove the conflicting duplicate", "re-export the Pack"),
        repair_level=REPAIR_LEVEL_SAFE, write_scope=WRITE_SCOPE_TARGET_PROFILE,
    ),
    "CONFLICT_DUPLICATE_ARTIFACT": _spec(
        stage="composition", severity=SEVERITY_BLOCKER,
        summary="Duplicate plugin artifact.",
        description="Two plugins resolve to the same artifact in the composition.",
        expected="every plugin resolves to a distinct artifact",
        impact="The Profile composition is ambiguous.",
        can_continue=False,
        suggested_checks=_checks("review the plugin identity records", "re-export the Pack"),
        repair_level=REPAIR_LEVEL_SAFE, write_scope=WRITE_SCOPE_NONE,
    ),
    "CONFLICT_DUPLICATE_BUNDLE_ORDER": _spec(
        stage="composition", severity=SEVERITY_BLOCKER,
        summary="Duplicate Bundle order.",
        description="A Bundle appears more than once in the Bundle order.",
        expected="every Bundle appears exactly once in order",
        impact="The Bundle order is ambiguous.",
        can_continue=False,
        suggested_checks=_checks("review the Bundle list and order", "re-export the Pack"),
        repair_level=REPAIR_LEVEL_SAFE, write_scope=WRITE_SCOPE_NONE,
    ),
    "PACKAGE_IDENTITY_DRIFT": _spec(
        stage="version-confirmation", severity=SEVERITY_BLOCKER,
        summary="Package identity drift.",
        description="The Pack identity (SPEC/RESOLUTION) drifts from the actual package source or version.",
        expected="the Pack identity matches the resolved package",
        impact="The Pack cannot be imported with the recorded identity.",
        can_continue=False,
        suggested_checks=_checks("verify SPEC and RESOLUTION records", "re-export the Pack from the installed state"),
        repair_level=REPAIR_LEVEL_SAFE, write_scope=WRITE_SCOPE_NONE,
    ),
    "ENVIRONMENT_OS_MISMATCH": _spec(
        stage="environment", severity=SEVERITY_WARNING,
        summary="Operating system differs from the source.",
        description="The target operating system differs from the OS recorded at Export.",
        expected="the target OS matches the source (or the difference is acceptable)",
        impact="Some behaviors may differ from the source environment.",
        can_continue=True,
        suggested_checks=_checks("review the OS difference", "verify the target is supported"),
        repair_level=REPAIR_LEVEL_READ_ONLY, write_scope=WRITE_SCOPE_NONE,
    ),
    "ENVIRONMENT_VERSION_MISMATCH": _spec(
        stage="environment", severity=SEVERITY_WARNING,
        summary="Environment version differs from the source.",
        description="A runtime version (Node, DSH) differs from the version recorded at Export.",
        expected="the target versions match the source (or the difference is acceptable)",
        impact="Some behaviors may differ from the source environment.",
        can_continue=True,
        suggested_checks=_checks("review the version difference", "confirm it is not a breaking difference"),
        repair_level=REPAIR_LEVEL_READ_ONLY, write_scope=WRITE_SCOPE_NONE,
    ),
    "ENVIRONMENT_EXACT_MATCH": _spec(
        stage="environment", severity=SEVERITY_INFO,
        summary="Environment matches the source.",
        description="The target environment matches the environment recorded at Export.",
        expected="the environment matches",
        impact="No environment risk detected.",
        can_continue=True,
        suggested_checks=_checks("none required"),
        repair_level=REPAIR_LEVEL_READ_ONLY, write_scope=WRITE_SCOPE_NONE,
    ),
    "VERSION_MISSING": _spec(
        stage="environment", severity=SEVERITY_WARNING,
        summary="A recorded version is missing.",
        description="A version record required for an environment comparison is missing.",
        expected="all version records are present",
        impact="The environment comparison is incomplete.",
        can_continue=True,
        suggested_checks=_checks("verify the Pack environment records", "re-export the Pack with version data"),
        repair_level=REPAIR_LEVEL_READ_ONLY, write_scope=WRITE_SCOPE_NONE,
    ),
    "NETWORK_INSTALL_REQUIRED": _spec(
        stage="network-install", severity=SEVERITY_WARNING,
        summary="Network install will be required.",
        description="Import will need to install a plugin from the network on the target machine.",
        expected="network access is available (or an embedded artifact is supplied)",
        impact="Import may fail without network access.",
        can_continue=True,
        suggested_checks=_checks("confirm network access on the target", "prefer embedded artifacts for offline targets"),
        repair_level=REPAIR_LEVEL_READ_ONLY, write_scope=WRITE_SCOPE_NONE,
    ),
    "OPTIONAL_PLUGIN_MISSING": _spec(
        stage="reference-install", severity=SEVERITY_WARNING,
        summary="Optional plugin is missing.",
        description="An optional plugin recorded in the Pack is not available on the target.",
        expected="optional plugins resolve (or are intentionally skipped)",
        impact="The optional plugin will be skipped.",
        can_continue=True,
        suggested_checks=_checks("confirm the optional plugin is not required", "provide the optional plugin source"),
        repair_level=REPAIR_LEVEL_READ_ONLY, write_scope=WRITE_SCOPE_NONE,
    ),
    "OPTIONAL_ARTIFACT_MISSING": _spec(
        stage="reference-install", severity=SEVERITY_WARNING,
        summary="Optional artifact is missing.",
        description="An optional plugin artifact is missing on the target.",
        expected="optional artifacts resolve (or are intentionally skipped)",
        impact="The optional artifact will be skipped.",
        can_continue=True,
        suggested_checks=_checks("confirm the optional artifact is not required"),
        repair_level=REPAIR_LEVEL_READ_ONLY, write_scope=WRITE_SCOPE_NONE,
    ),
    "SECRET_MISSING": _spec(
        stage="planning", severity=SEVERITY_WARNING,
        summary="Required Secret is missing.",
        description="The Pack declares a required Secret name that is not present in the target environment.",
        expected="every required Secret is present",
        impact="The restored Profile may not work until the Secret is provided.",
        can_continue=True,
        suggested_checks=_checks("provide the required Secret in the target environment", "confirm the Secret name matches the Pack"),
        repair_level=REPAIR_LEVEL_READ_ONLY, write_scope=WRITE_SCOPE_NONE,
    ),
}
# Preflight may report PLUGIN_MISSING / PLUGIN_VERSION_MISMATCH as WARNING
# findings; when the same code appears as an Import failure it is a BLOCKER.
for _alias in ("PLUGIN_MISSING", "PLUGIN_VERSION_MISMATCH"):
    _base = DIAGNOSTIC_SPECS[_alias]
    DIAGNOSTIC_SPECS[_alias] = {
        **_base,
        "description": _base["description"]
        + " Preflight may report this code as a WARNING finding; as an Import failure it is a BLOCKER.",
    }
del _alias, _base

# ---------------------------------------------------------------------------
# Envelope
# ---------------------------------------------------------------------------


def envelope_fields(*, operation: str, status: str, operation_id: str | None = None) -> dict[str, Any]:
    """Return the versioned diagnostic envelope fields.

    Every diagnostic produced by DSH Crate carries these fields so a
    Troubleshooting Skill can decide whether it understands the diagnostic.
    """
    envelope = {
        "producer": PRODUCER,
        "crateVersion": CRATE_VERSION,
        "diagnosticSchemaVersion": DIAGNOSTIC_SCHEMA_VERSION,
        "operation": operation,
        "status": status,
    }
    if operation_id:
        envelope["operationId"] = operation_id
    return envelope


def decorate_issue(
    issue: Mapping[str, Any],
    *,
    operation: str,
    status: str,
    operation_id: str | None = None,
) -> dict[str, Any]:
    """Merge the versioned envelope into a single-issue diagnostic (additive)."""
    merged = dict(issue)
    for key, value in envelope_fields(operation=operation, status=status, operation_id=operation_id).items():
        merged.setdefault(key, value)
    return merged


# ---------------------------------------------------------------------------
# Registry access
# ---------------------------------------------------------------------------


def spec(code: str) -> dict[str, Any] | None:
    """Return the registry entry for a diagnostic code, or None when unknown."""
    return DIAGNOSTIC_SPECS.get(code)


def known(code: str) -> bool:
    """Whether a diagnostic code is registered."""
    return code in DIAGNOSTIC_SPECS


def classify(issue: Mapping[str, Any]) -> dict[str, Any]:
    """Resolve an issue diagnostic against the registry.

    Returns the matched registry fields plus ``known``. When the code is not
    registered the result marks it unknown and forbids automated repair.
    """
    code = issue.get("code")
    if not isinstance(code, str):
        return {
            "known": False,
            "code": None,
            "reason": "diagnostic carries no string code; do not guess",
            "repairLevel": REPAIR_LEVEL_FORBIDDEN,
            "writeScope": WRITE_SCOPE_NONE,
            "verifyAfter": False,
        }
    entry = spec(code)
    if entry is None:
        return {
            "known": False,
            "code": code,
            "reason": "diagnostic code is not in the registry; update the Skill before automated repair",
            "repairLevel": REPAIR_LEVEL_FORBIDDEN,
            "writeScope": WRITE_SCOPE_NONE,
            "verifyAfter": False,
        }
    return {
        "known": True,
        "code": code,
        **entry,
    }


# ---------------------------------------------------------------------------
# Compatibility gate
# ---------------------------------------------------------------------------


def _parse_semver(value: str) -> tuple[int, int, int] | None:
    match = re.match(r"^\s*v?(\d+)\.(\d+)\.(\d+)", value)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def _clause_match(version: tuple[int, int, int], op: str, target: tuple[int, int, int]) -> bool:
    if op == ">=":
        return version >= target
    if op == ">":
        return version > target
    if op == "<=":
        return version <= target
    if op == "<":
        return version < target
    return version == target


def version_in_range(version: str, range_spec: str) -> bool:
    """Whether a version satisfies a simple space-separated range (>=, >, <=, <, =, ==)."""
    if not range_spec or range_spec.strip() == "*":
        return True
    parsed = _parse_semver(version)
    if parsed is None:
        return False
    for clause in range_spec.split():
        op = ""
        target_text = clause
        for candidate in (">=", "<=", ">", "<", "==", "="):
            if clause.startswith(candidate):
                op = candidate
                target_text = clause[len(candidate):]
                break
        if not op:
            op = "="
        target = _parse_semver(target_text)
        if target is None:
            return False
        if not _clause_match(parsed, op, target):
            return False
    return True


def compat_status(
    *,
    skill_version: str,
    dsh_crate_range: str,
    supported_schemas: list[int],
    crate_version: str,
    diagnostic_schema_version: int,
) -> dict[str, Any]:
    """Return the compatibility result for a Skill against a diagnostic.

    - FULL: same Crate generation, supported schema -> normal troubleshooting.
    - COMPATIBLE: older Crate inside the supported range -> compatibility rules.
    - UNSUPPORTED: Crate outside the range or schema unsupported -> never guess.
    """
    schema_supported = diagnostic_schema_version in (supported_schemas or [])
    version_in = version_in_range(crate_version, dsh_crate_range)
    if not schema_supported or not version_in:
        reason_parts = []
        if not version_in:
            reason_parts.append(
                f"this diagnostic was produced by DSH Crate {crate_version}, which is outside the supported range {dsh_crate_range}"
            )
        if not schema_supported:
            reason_parts.append(
                f"diagnostic schema v{diagnostic_schema_version} is not supported (supported: {supported_schemas or []})"
            )
        return {
            "status": "UNSUPPORTED",
            "reason": "; ".join(reason_parts),
            "skillVersion": skill_version,
            "crateVersion": crate_version,
            "diagnosticSchemaVersion": diagnostic_schema_version,
            "schemaSupported": schema_supported,
            "versionInRange": version_in,
            "canProceed": False,
        }
    skill = _parse_semver(skill_version)
    crate = _parse_semver(crate_version)
    same_generation = (
        skill is not None and crate is not None and skill[0] == crate[0] and skill[1] == crate[1]
    )
    if same_generation:
        return {
            "status": "FULL",
            "reason": "same Crate generation and supported diagnostic schema",
            "skillVersion": skill_version,
            "crateVersion": crate_version,
            "diagnosticSchemaVersion": diagnostic_schema_version,
            "schemaSupported": True,
            "versionInRange": True,
            "canProceed": True,
        }
    return {
        "status": "COMPATIBLE",
        "reason": "Crate version is inside the supported range; use compatibility rules",
        "skillVersion": skill_version,
        "crateVersion": crate_version,
        "diagnosticSchemaVersion": diagnostic_schema_version,
        "schemaSupported": True,
        "versionInRange": True,
        "canProceed": True,
    }
