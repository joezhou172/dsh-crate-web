"""Read-only Phase 3 Pack preflight checks."""

from __future__ import annotations

import json
import os
import tarfile
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any, Mapping

from .errors import DshPackError, IntegrityError, SchemaValidationError, _default_checks
from .network import network_source_details
from .pack import _read_entries, sha256_bytes
from .validation import validate_manifest, validate_plugins_lock


_SEVERITIES = ("BLOCKER", "WARNING", "INFO")
_STAGE_BY_CODE = {
    "FORMAT_ERROR": "format",
    "SCHEMA_ERROR": "schema",
    "HASH_OR_INTEGRITY_ERROR": "integrity",
    "HASH_MISMATCH": "integrity",
    "INTEGRITY_FILE_MISSING": "integrity",
    "INTEGRITY_FILE_SET_MISMATCH": "integrity",
    "VERSION_MISSING": "identity",
    "PACKAGE_IDENTITY_DRIFT": "identity",
    "REQUIRED_ARTIFACT_MISSING": "artifact",
    "OPTIONAL_ARTIFACT_MISSING": "artifact",
    "PLUGIN_MISSING": "plugin",
    "OPTIONAL_PLUGIN_MISSING": "plugin",
    "PLUGIN_VERSION_MISMATCH": "plugin",
    "NETWORK_INSTALL_REQUIRED": "plugin",
    "ENVIRONMENT_EXACT_MATCH": "environment",
    "ENVIRONMENT_VERSION_MISMATCH": "environment",
    "ENVIRONMENT_OS_MISMATCH": "environment",
    "SECRET_MISSING": "secrets",
    "CONFLICT_BUNDLE_COMPOSITION": "composition",
    "CONFLICT_DUPLICATE_BUNDLE_ORDER": "composition",
    "CONFLICT_DUPLICATE_ARTIFACT": "composition",
}
_EXPECTED_BY_CODE = {
    "FORMAT_ERROR": "a readable DSH Pack archive",
    "SCHEMA_ERROR": "a supported DSH Pack schema",
    "HASH_OR_INTEGRITY_ERROR": "declared integrity matches Pack contents",
    "HASH_MISMATCH": "declared SHA-256 matches artifact bytes",
    "INTEGRITY_FILE_MISSING": "all declared Pack files are present",
    "INTEGRITY_FILE_SET_MISMATCH": "Pack files exactly match the integrity set",
    "VERSION_MISSING": "each plugin has resolved.version",
    "PACKAGE_IDENTITY_DRIFT": "artifact package identity matches lock identity",
    "REQUIRED_ARTIFACT_MISSING": "required embedded artifact is present",
    "OPTIONAL_ARTIFACT_MISSING": "optional embedded artifact is present",
    "PLUGIN_MISSING": "required reference-only plugin is available",
    "OPTIONAL_PLUGIN_MISSING": "optional reference-only plugin is available",
    "PLUGIN_VERSION_MISMATCH": "installed reference-only version matches Pack",
    "NETWORK_INSTALL_REQUIRED": "a supported recorded network source is available for npm installation",
    "ENVIRONMENT_EXACT_MATCH": "current environment satisfies Pack requirement",
    "ENVIRONMENT_VERSION_MISMATCH": "current version satisfies Pack requirement",
    "ENVIRONMENT_OS_MISMATCH": "current OS matches Pack requirement",
    "SECRET_MISSING": "required Secret name is available",
    "CONFLICT_BUNDLE_COMPOSITION": "Profile and lock Bundle composition agree",
    "CONFLICT_DUPLICATE_BUNDLE_ORDER": "each enabled Bundle has a unique order",
    "CONFLICT_DUPLICATE_ARTIFACT": "each artifact path is owned by one plugin",
}
_NEXT_STEP_BY_CODE = {
    "FORMAT_ERROR": "Provide a readable .dshcrate and run inspect again.",
    "SCHEMA_ERROR": "Regenerate the Pack with the supported schema.",
    "HASH_OR_INTEGRITY_ERROR": "Regenerate or restore the Pack from an untampered source.",
    "HASH_MISMATCH": "Restore the original artifact or regenerate the Pack.",
    "INTEGRITY_FILE_MISSING": "Restore the missing Pack member and regenerate its integrity table.",
    "INTEGRITY_FILE_SET_MISMATCH": "Regenerate the Pack so its integrity file set matches its contents.",
    "VERSION_MISSING": "Regenerate plugins.lock.json with a resolved plugin version.",
    "PACKAGE_IDENTITY_DRIFT": "Restore the artifact matching plugins.lock.json or re-export the Profile.",
    "REQUIRED_ARTIFACT_MISSING": "Restore the required embedded artifact before continuing.",
    "OPTIONAL_ARTIFACT_MISSING": "Restore the optional artifact or intentionally export the plugin reference-only.",
    "PLUGIN_MISSING": "Install the required reference-only plugin at the Pack version.",
    "OPTIONAL_PLUGIN_MISSING": "Install the optional plugin or accept the degraded capability.",
    "PLUGIN_VERSION_MISMATCH": "Install the exact reference-only plugin version from the Pack.",
    "NETWORK_INSTALL_REQUIRED": "Import will download this plugin with npm into the temporary Profile before commit.",
    "ENVIRONMENT_EXACT_MATCH": "Continue to the next preflight check.",
    "ENVIRONMENT_VERSION_MISMATCH": "Use a compatible DSH/Node version before continuing.",
    "ENVIRONMENT_OS_MISMATCH": "Review the OS difference before importing the Pack.",
    "SECRET_MISSING": "Provide the Secret outside the Pack before running capability tests.",
    "CONFLICT_BUNDLE_COMPOSITION": "Restore the Profile Bundle list and lock order before continuing.",
    "CONFLICT_DUPLICATE_BUNDLE_ORDER": "Assign each enabled Bundle plugin a unique order and regenerate the Pack.",
    "CONFLICT_DUPLICATE_ARTIFACT": "Give each embedded artifact a unique path and regenerate the Pack.",
}


@dataclass(frozen=True)
class Finding:
    severity: str
    code: str
    message: str
    stage: str
    item: str
    expected: Any
    observed: Any
    evidence: Any
    impact: str
    can_continue: bool
    suggested_next_step: str
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.severity not in _SEVERITIES:
            raise ValueError(f"unsupported preflight severity: {self.severity}")

    def as_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "stage": self.stage,
            "item": self.item,
            "expected": self.expected,
            "observed": self.observed,
            "evidence": self.evidence,
            "impact": self.impact,
            "canContinue": self.can_continue,
            "suggestedNextStep": self.suggested_next_step,
            "suggestedChecks": _default_checks(self.stage, self.code),
            "details": self.details,
        }


@dataclass(frozen=True)
class PreflightContext:
    """Optional facts about the machine that will receive the Pack.

    ``available_plugins=None`` means that reference-only plugin availability is
    not known. An explicit mapping is treated as the complete installed-plugin
    inventory, allowing missing optional plugins to be reported honestly.
    """

    current_environment: Mapping[str, Any] = field(default_factory=dict)
    available_secrets: set[str] | None = None
    available_plugins: Mapping[str, str | None] | None = None
    allow_network_reference_install: bool = False


@dataclass
class PreflightResult:
    pack_path: str
    status: str
    pack: dict[str, Any]
    schema: dict[str, Any]
    environment: dict[str, Any]
    plugins: list[dict[str, Any]]
    secrets: dict[str, Any]
    artifacts: list[dict[str, Any]]
    conflicts: list[dict[str, Any]]
    findings: list[Finding]

    @property
    def blockers(self) -> list[Finding]:
        return [finding for finding in self.findings if finding.severity == "BLOCKER"]

    @property
    def warnings(self) -> list[Finding]:
        return [finding for finding in self.findings if finding.severity == "WARNING"]

    @property
    def warning_count(self) -> int:
        return len(self.warnings)

    @property
    def required_plugins(self) -> list[dict[str, Any]]:
        return [plugin for plugin in self.plugins if plugin.get("required") is True]

    @property
    def optional_plugins(self) -> list[dict[str, Any]]:
        return [plugin for plugin in self.plugins if plugin.get("required") is not True]

    @property
    def can_continue(self) -> bool:
        """Core-owned decision for actions that require a ready Preflight."""

        return self.status == "READY"

    def as_dict(self) -> dict[str, Any]:
        return {
            "pack": self.pack,
            "schema": self.schema,
            "environment": self.environment,
            "plugins": self.plugins,
            "secrets": self.secrets,
            "artifacts": self.artifacts,
            "conflicts": self.conflicts,
            "findings": [finding.as_dict() for finding in self.findings],
            "warningCount": self.warning_count,
            "requiredPlugins": self.required_plugins,
            "optionalPlugins": self.optional_plugins,
            "status": self.status,
            "canContinue": self.can_continue,
        }


def _json_object(content: bytes | None, name: str) -> dict[str, Any] | None:
    if content is None:
        return None
    try:
        value = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _finding(
    severity: str,
    code: str,
    message: str,
    *,
    stage: str | None = None,
    item: str | None = None,
    expected: Any = None,
    observed: Any = None,
    evidence: Any = None,
    impact: str | None = None,
    can_continue: bool | None = None,
    suggested_next_step: str | None = None,
    **details: Any,
) -> Finding:
    if observed is None:
        observed = details.get("actual", message)
    if evidence is None:
        evidence = dict(details) or {"message": message}
    if impact is None:
        impact = "No blocking issue detected." if severity == "INFO" else (
            "Preflight can continue, but the Pack has a non-blocking issue."
            if severity == "WARNING"
            else "Preflight cannot continue safely."
        )
    if can_continue is None:
        can_continue = severity != "BLOCKER"
    return Finding(
        severity=severity,
        code=code,
        message=message,
        stage=stage or _STAGE_BY_CODE.get(code, "preflight"),
        item=item or str(details.get("path") or details.get("plugin") or details.get("secret") or code),
        expected=expected if expected is not None else _EXPECTED_BY_CODE.get(code),
        observed=observed,
        evidence=evidence,
        impact=impact,
        can_continue=can_continue,
        suggested_next_step=suggested_next_step or _NEXT_STEP_BY_CODE.get(code, "Review this finding and run inspect again."),
        details=details,
    )


def _error_finding(error: DshPackError) -> Finding:
    if isinstance(error, IntegrityError):
        return _finding("BLOCKER", "HASH_OR_INTEGRITY_ERROR", str(error))
    if isinstance(error, SchemaValidationError):
        return _finding("BLOCKER", "SCHEMA_ERROR", str(error))
    return _finding("BLOCKER", "FORMAT_ERROR", str(error))


def _environment_value(environment: Mapping[str, Any], section: str, key: str = "version") -> str | None:
    value = environment.get(section)
    if not isinstance(value, Mapping):
        return None
    result = value.get(key)
    return result if isinstance(result, str) and result else None


def _version_matches(requirement: str, current: str) -> bool:
    requirement = requirement.strip().lower()
    current = current.strip().lower()
    # Node reports version strings both with and without a leading "v"
    # (e.g. process.version is "v24.13.0" while process.versions.node is
    # "24.13.0"). A formatting difference must never be treated as a
    # compatibility difference.
    if requirement.startswith("v"):
        requirement = requirement[1:]
    if current.startswith("v"):
        current = current[1:]
    if requirement == current:
        return True
    if requirement.endswith(".x"):
        return current.startswith(requirement[:-1])
    return False


def _profile_bundle_names(entries: Mapping[str, bytes]) -> list[str] | None:
    profile_manifest = _json_object(entries.get("profile/package.json"), "profile/package.json")
    if profile_manifest is None:
        return None
    dsh = profile_manifest.get("dsh")
    if not isinstance(dsh, Mapping):
        return []
    profile = dsh.get("profile")
    if not isinstance(profile, Mapping):
        return []
    bundles = profile.get("bundles")
    if not isinstance(bundles, list) or any(not isinstance(name, str) for name in bundles):
        return None
    return list(bundles)


def _artifact_package_identity(content: bytes) -> dict[str, str] | None:
    """Read package identity from an npm tarball without extracting to disk."""

    try:
        with tarfile.open(fileobj=BytesIO(content), mode="r:gz") as archive:
            try:
                member = archive.getmember("package/package.json")
            except KeyError:
                return None
            if not member.isfile():
                return None
            extracted = archive.extractfile(member)
            if extracted is None:
                return None
            value = json.loads(extracted.read().decode("utf-8"))
    except (OSError, tarfile.TarError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(value, Mapping):
        return None
    name = value.get("name")
    version = value.get("version")
    if not isinstance(name, str) or not isinstance(version, str):
        return None
    return {"name": name, "version": version}


def _status(findings: list[Finding]) -> str:
    if any(finding.severity == "BLOCKER" for finding in findings):
        return "NOT_READY"
    return "READY"


def _empty_result(source: Path, findings: list[Finding]) -> PreflightResult:
    return PreflightResult(
        pack_path=str(source),
        status=_status(findings),
        pack={"path": str(source)},
        schema={"status": "invalid"},
        environment={"required": {}, "current": {}},
        plugins=[],
        secrets={"required": [], "missing": [], "availableNames": []},
        artifacts=[],
        conflicts=[],
        findings=findings,
    )


def inspect_pack(
    source: str | os.PathLike[str],
    *,
    context: PreflightContext | None = None,
) -> PreflightResult:
    """Inspect one Pack without installing, extracting, or modifying anything."""

    source_path = Path(source).resolve()
    context = context or PreflightContext()
    findings: list[Finding] = []
    try:
        entries = _read_entries(source_path)
    except DshPackError as error:
        return _empty_result(source_path, [_error_finding(error)])

    if "manifest.json" not in entries:
        findings.append(_finding("BLOCKER", "FORMAT_ERROR", "Pack is missing manifest.json"))
    if "plugins.lock.json" not in entries:
        findings.append(_finding("BLOCKER", "FORMAT_ERROR", "Pack is missing plugins.lock.json"))
    if not any(name.startswith("profile/") for name in entries):
        findings.append(_finding("BLOCKER", "FORMAT_ERROR", "Pack is missing profile/ files"))
    if findings:
        return _empty_result(source_path, findings)

    manifest = _json_object(entries["manifest.json"], "manifest.json")
    lock = _json_object(entries["plugins.lock.json"], "plugins.lock.json")
    if manifest is None:
        findings.append(_finding("BLOCKER", "SCHEMA_ERROR", "manifest.json must contain a JSON object"))
    if lock is None:
        findings.append(_finding("BLOCKER", "SCHEMA_ERROR", "plugins.lock.json must contain a JSON object"))
    if findings:
        return _empty_result(source_path, findings)
    assert manifest is not None
    assert lock is not None

    try:
        validate_manifest(manifest, require_integrity=True)
    except SchemaValidationError as error:
        findings.append(_finding("BLOCKER", "SCHEMA_ERROR", str(error)))

    raw_plugins = lock.get("plugins", [])
    if not isinstance(raw_plugins, list):
        raw_plugins = []
    plugin_names: set[str] = set()
    missing_version_indexes: set[int] = set()
    for index, raw_plugin in enumerate(raw_plugins):
        if not isinstance(raw_plugin, Mapping):
            continue
        name = raw_plugin.get("name")
        if isinstance(name, str):
            if name in plugin_names:
                findings.append(_finding("BLOCKER", "SCHEMA_ERROR", f"duplicate plugin name: {name}"))
            plugin_names.add(name)
        resolved = raw_plugin.get("resolved")
        version = resolved.get("version") if isinstance(resolved, Mapping) else None
        if not isinstance(version, str) or not version.strip():
            missing_version_indexes.add(index)
            findings.append(
                _finding(
                    "BLOCKER",
                    "VERSION_MISSING",
                    f"plugin at plugins.lock.plugins[{index}] is missing resolved.version",
                    index=index,
                    plugin=name,
                )
            )

    artifact_entries = {name for name in entries if name.startswith("plugins/")}
    artifacts: list[dict[str, Any]] = []
    artifact_paths: dict[str, str] = {}
    for index, raw_plugin in enumerate(raw_plugins):
        if not isinstance(raw_plugin, Mapping):
            continue
        name = raw_plugin.get("name", f"plugin[{index}]")
        required = raw_plugin.get("required") is True
        artifact = raw_plugin.get("artifact")
        if not isinstance(artifact, Mapping):
            continue
        mode = artifact.get("mode")
        path = artifact.get("path") if isinstance(artifact.get("path"), str) else None
        artifact_status = "reference-only"
        if mode == "embedded":
            artifact_status = "present" if path in artifact_entries else "missing"
            if path and path in artifact_paths:
                findings.append(
                    _finding(
                        "BLOCKER",
                        "CONFLICT_DUPLICATE_ARTIFACT",
                        f"plugins {artifact_paths[path]} and {name} use the same artifact path: {path}",
                        path=path,
                    )
                )
            elif path:
                artifact_paths[path] = str(name)
            if path not in artifact_entries:
                severity = "BLOCKER" if required else "WARNING"
                code = "REQUIRED_ARTIFACT_MISSING" if required else "OPTIONAL_ARTIFACT_MISSING"
                findings.append(
                    _finding(
                        severity,
                        code,
                        f"{name} embedded artifact is missing: {path}",
                        plugin=name,
                        path=path,
                    )
                )
        artifacts.append(
            {
                "plugin": name,
                "required": required,
                "mode": mode,
                "path": path,
                "status": artifact_status,
                "sha256": artifact.get("sha256"),
            }
        )

    try:
        validate_plugins_lock(lock, artifact_paths=artifact_entries)
    except SchemaValidationError as error:
        message = str(error)
        if "resolved.version" not in message and "resolved is missing fields" not in message:
            if "artifact.path is missing from plugins/" not in message:
                findings.append(_finding("BLOCKER", "SCHEMA_ERROR", message))

    hash_mismatch_paths: set[str] = set()
    integrity = manifest.get("integrity")
    if isinstance(integrity, Mapping) and isinstance(integrity.get("files"), Mapping):
        declared = dict(integrity["files"])
        actual = set(entries) - {"manifest.json"}
        missing = set(declared) - actual
        unexpected = actual - set(declared)
        plugin_artifact_paths = set(artifact_paths)
        for name in sorted(missing - plugin_artifact_paths):
            findings.append(_finding("BLOCKER", "INTEGRITY_FILE_MISSING", f"integrity file is missing: {name}", path=name))
        if unexpected:
            findings.append(
                _finding(
                    "BLOCKER",
                    "INTEGRITY_FILE_SET_MISMATCH",
                    f"integrity has unexpected files: {sorted(unexpected)}",
                    files=sorted(unexpected),
                )
            )
        for name, expected in declared.items():
            if name not in entries:
                continue
            actual_hash = sha256_bytes(entries[name])
            if actual_hash != expected:
                hash_mismatch_paths.add(name)
                plugin = artifact_paths.get(name)
                findings.append(
                    _finding(
                        "BLOCKER",
                        "HASH_MISMATCH",
                        f"{name} hash mismatch",
                        path=name,
                        expected=expected,
                        actual=actual_hash,
                        plugin=plugin,
                    )
                )
    for artifact in artifacts:
        if artifact.get("mode") != "embedded" or artifact.get("path") not in entries:
            continue
        expected = artifact.get("sha256")
        path = artifact.get("path")
        actual_hash = sha256_bytes(entries[path])
        if isinstance(expected, str) and actual_hash != expected:
            if path not in hash_mismatch_paths:
                findings.append(
                    _finding(
                        "BLOCKER",
                        "HASH_MISMATCH",
                        f"{path} hash mismatch in plugins.lock.json",
                        path=path,
                        expected=expected,
                        actual=actual_hash,
                        plugin=artifact.get("plugin"),
                    )
                )
            hash_mismatch_paths.add(path)
    for artifact in artifacts:
        if artifact.get("path") in hash_mismatch_paths:
            artifact["status"] = "hash-mismatch"

    bundle_orders: dict[int, str] = {}
    bundle_names: list[str] = []
    plugin_summaries: list[dict[str, Any]] = []
    for index, raw_plugin in enumerate(raw_plugins):
        if not isinstance(raw_plugin, Mapping):
            continue
        name = raw_plugin.get("name", f"plugin[{index}]")
        bundle = raw_plugin.get("bundle")
        if isinstance(bundle, Mapping) and bundle.get("enabled") is True:
            order = bundle.get("order")
            if isinstance(order, int) and not isinstance(order, bool):
                if order in bundle_orders:
                    findings.append(
                        _finding(
                            "BLOCKER",
                            "CONFLICT_DUPLICATE_BUNDLE_ORDER",
                            f"plugins {bundle_orders[order]} and {name} share Bundle order {order}",
                            item="dsh.profile.bundles[]",
                            expected="unique Bundle order values",
                            observed={"order": order, "plugins": [bundle_orders[order], str(name)]},
                            evidence={"source": "plugins.lock.json", "order": order},
                            kind="duplicateBundleOrder",
                            order=order,
                        )
                    )
                else:
                    bundle_orders[order] = str(name)
                bundle_names.append(str(name))
        plugin_summaries.append(
            {
                "name": name,
                "required": raw_plugin.get("required"),
                "requested": raw_plugin.get("requested"),
                "resolved": raw_plugin.get("resolved"),
                "runtime": raw_plugin.get("runtime"),
                "bundle": bundle,
                "artifact": raw_plugin.get("artifact"),
            }
        )

    profile_bundles = _profile_bundle_names(entries)
    if profile_bundles is not None and profile_bundles != bundle_names:
        findings.append(
            _finding(
                "BLOCKER",
                "CONFLICT_BUNDLE_COMPOSITION",
                f"Profile bundle order {profile_bundles} differs from plugins.lock order {bundle_names}",
                profile=profile_bundles,
                lock=bundle_names,
            )
        )

    current_environment = dict(context.current_environment)
    required_environment = manifest.get("environment") if isinstance(manifest.get("environment"), Mapping) else {}
    for section, label in (("dsh", "DSH"), ("node", "Node")):
        required = _environment_value(required_environment, section)
        current = _environment_value(current_environment, section)
        if required and current:
            if not _version_matches(required, current):
                findings.append(
                    _finding(
                        "BLOCKER",
                        "ENVIRONMENT_VERSION_MISMATCH",
                        f"Pack requires {label} {required}; current is {current}",
                        stage="environment",
                        item=section,
                        expected=required,
                        observed=current,
                        evidence={"required": required, "current": current},
                    )
                )
    required_os = _environment_value(required_environment, "os", "name")
    current_os = _environment_value(current_environment, "os", "name")
    required_os_version = _environment_value(required_environment, "os", "version")
    current_os_version = _environment_value(current_environment, "os", "version")
    os_name_mismatch = required_os and current_os and required_os.lower() != current_os.lower()
    os_version_mismatch = (
        required_os_version
        and current_os_version
        and required_os_version.lower() != current_os_version.lower()
    )
    if os_name_mismatch or os_version_mismatch:
        findings.append(
            _finding(
                "WARNING",
                "ENVIRONMENT_OS_MISMATCH",
                f"Pack exported for {required_os} {required_os_version or ''}; current OS is {current_os} {current_os_version or ''}".strip(),
                stage="environment",
                item="os",
                expected={"name": required_os, "version": required_os_version},
                observed={"name": current_os, "version": current_os_version},
                evidence={"required": required_environment.get("os"), "current": current_environment.get("os")},
            )
        )

    available_secrets = set(os.environ) if context.available_secrets is None else set(context.available_secrets)
    required_secrets = manifest.get("requiredSecrets", [])
    if not isinstance(required_secrets, list):
        required_secrets = []
    missing_secrets = [name for name in required_secrets if isinstance(name, str) and name not in available_secrets]
    for name in missing_secrets:
        findings.append(_finding("WARNING", "SECRET_MISSING", f"required Secret is missing: {name}", secret=name))

    if context.available_plugins is not None:
        available_plugins = dict(context.available_plugins)
        for plugin in plugin_summaries:
            artifact = plugin.get("artifact")
            if not isinstance(artifact, Mapping) or artifact.get("mode") != "reference-only":
                continue
            name = plugin["name"]
            if name not in available_plugins:
                network_source = network_source_details(plugin)
                if context.allow_network_reference_install and network_source is not None:
                    expected_version = plugin.get("resolved", {}).get("version") if isinstance(plugin.get("resolved"), Mapping) else None
                    findings.append(
                        _finding(
                            "WARNING",
                            "NETWORK_INSTALL_REQUIRED",
                            f"reference-only plugin is not installed locally; npm will download {name}",
                            plugin=name,
                            expected={
                                "sourceType": network_source["sourceType"],
                                "specifier": network_source["specifier"],
                                "version": expected_version,
                            },
                            observed="local source unavailable",
                            evidence={"source": network_source, "resolver": "npm"},
                            impact="Import will contact the recorded network source and install into the temporary Profile.",
                        )
                    )
                    continue
                required = plugin.get("required") is True
                severity = "BLOCKER" if required else "WARNING"
                code = "PLUGIN_MISSING" if required else "OPTIONAL_PLUGIN_MISSING"
                findings.append(_finding(severity, code, f"reference-only plugin is missing: {name}", plugin=name))
                continue
            installed_version = available_plugins[name]
            expected_version = plugin.get("resolved", {}).get("version") if isinstance(plugin.get("resolved"), Mapping) else None
            if installed_version and expected_version and installed_version != expected_version:
                findings.append(
                    _finding(
                        "BLOCKER" if plugin.get("required") is True else "WARNING",
                        "PLUGIN_VERSION_MISMATCH",
                        f"installed {name}@{installed_version} does not match Pack version {expected_version}",
                        plugin=name,
                        expected=expected_version,
                        actual=installed_version,
                    )
                )

    for plugin in plugin_summaries:
        artifact = plugin.get("artifact")
        if not isinstance(artifact, Mapping) or artifact.get("mode") != "embedded":
            continue
        path = artifact.get("path")
        if not isinstance(path, str) or path not in entries:
            continue
        identity = _artifact_package_identity(entries[path])
        if identity is None:
            continue
        plugin["artifactIdentity"] = identity
        resolved = plugin.get("resolved")
        expected_version = resolved.get("version") if isinstance(resolved, Mapping) else None
        drift: dict[str, dict[str, str]] = {}
        if identity["name"] != plugin["name"]:
            drift["name"] = {"expected": str(plugin["name"]), "actual": identity["name"]}
        if isinstance(expected_version, str) and identity["version"] != expected_version:
            drift["version"] = {"expected": expected_version, "actual": identity["version"]}
        runtime = plugin.get("runtime")
        runtime_version = runtime.get("version") if isinstance(runtime, Mapping) else None
        runtime_source = runtime.get("source") if isinstance(runtime, Mapping) else None
        if (
            isinstance(expected_version, str)
            and isinstance(runtime_version, str)
            and expected_version != runtime_version
            and runtime_source != "installation-anchor"
        ):
            drift["runtimeVersion"] = {"expected": expected_version, "actual": runtime_version}
        if drift:
            findings.append(
                _finding(
                    "WARNING",
                    "PACKAGE_IDENTITY_DRIFT",
                    f"embedded package identity differs from lock identity: {plugin['name']}",
                    plugin=plugin["name"],
                    drift=drift,
                )
            )

    conflicts = [
        finding.as_dict()
        for finding in findings
        if finding.code.startswith("CONFLICT_")
    ]
    required = required_environment if isinstance(required_environment, Mapping) else {}
    environment = {"required": dict(required), "current": current_environment}
    schema_version = manifest.get("schemaVersion")
    schema_status = "valid" if not any(finding.code == "SCHEMA_ERROR" for finding in findings) else "invalid"
    return PreflightResult(
        pack_path=str(source_path),
        status=_status(findings),
        pack={
            "path": str(source_path),
            "format": manifest.get("format"),
            "packVersion": manifest.get("packVersion"),
            "profile": manifest.get("profile"),
        },
        schema={"status": schema_status, "version": schema_version},
        environment=environment,
        plugins=plugin_summaries,
        secrets={
            "required": required_secrets,
            "missing": missing_secrets,
            "availableNames": sorted(name for name in available_secrets if name in required_secrets),
        },
        artifacts=artifacts,
        conflicts=conflicts,
        findings=findings,
    )


def render_text(result: PreflightResult) -> str:
    """Render the stable human-readable inspect report."""

    lines = [
        "Pack",
        f"path: {result.pack.get('path', result.pack_path)}",
        f"format: {result.pack.get('format', 'unknown')}",
        f"profile: {result.pack.get('profile', {}).get('name', 'unknown') if isinstance(result.pack.get('profile'), Mapping) else 'unknown'}",
        "",
        "Schema",
        f"status: {result.schema.get('status', 'unknown')}",
        f"version: {result.schema.get('version', 'unknown')}",
        "",
        "DSH requirement",
        f"{_environment_value(result.environment.get('required', {}), 'dsh') or 'unknown'}",
        "Node requirement",
        f"{_environment_value(result.environment.get('required', {}), 'node') or 'unknown'}",
        "OS",
        f"{_environment_value(result.environment.get('required', {}), 'os', 'name') or 'unknown'}",
        "",
        "Plugins",
    ]
    if result.plugins:
        for plugin in result.plugins:
            resolved = plugin.get("resolved")
            version = resolved.get("version", "missing") if isinstance(resolved, Mapping) else "missing"
            required = "required" if plugin.get("required") else "optional"
            artifact = plugin.get("artifact")
            mode = artifact.get("mode", "unknown") if isinstance(artifact, Mapping) else "unknown"
            lines.append(f"- {plugin.get('name')}@{version} [{required}, {mode}]")
    else:
        lines.append("- none")
    lines.extend(["", "Secrets"])
    lines.append(f"required: {', '.join(result.secrets['required']) or 'none'}")
    lines.append(f"missing: {', '.join(result.secrets['missing']) or 'none'}")
    lines.extend(["", "Artifacts"])
    if result.artifacts:
        for artifact in result.artifacts:
            lines.append(f"- {artifact.get('path') or artifact.get('plugin')} [{artifact.get('status')}, {artifact.get('mode')}]")
    else:
        lines.append("- none")
    lines.extend(["", "Conflicts"])
    if result.conflicts:
        lines.extend(f"- {conflict['message']}" for conflict in result.conflicts)
    else:
        lines.append("- none")
    for severity in _SEVERITIES:
        lines.extend(["", severity])
        matching = [finding for finding in result.findings if finding.severity == severity]
        if matching:
            lines.extend(f"- {finding.message}" for finding in matching)
        else:
            lines.append("- none")
    lines.extend(["", f"Status: {result.status}"])
    return "\n".join(lines)
