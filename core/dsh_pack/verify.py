"""Phase 5 verification for a prepared DSH Profile.

The core owns composition checks, status aggregation, evidence shape, and the
plugin smoke-test contract.  Runtime execution is deliberately injected via a
``VerifyAdapter`` so this module never guesses a DSH command, health endpoint,
or model interaction.  Without an adapter, runtime checks are UNTESTED.
"""

from __future__ import annotations

import json
import os
import posixpath
import re
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from .errors import _default_checks
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence


VERIFY_STATUSES = ("PASS", "FAIL", "UNTESTED", "DEGRADED")
RUNTIME_STEPS = (
    ("boot", "DSH boot"),
    ("surface_ready", "Web/headless ready"),
    ("new_session", "new session"),
    ("basic_response", "basic response"),
    ("core_tool", "core tool"),
    ("restart", "restart"),
    ("restart_surface_ready", "verify after restart"),
)


@dataclass(frozen=True)
class SmokeTestContract:
    """Explicit plugin smoke tests; no test means UNTESTED, never PASS."""

    plugin: str
    tests: tuple[str, ...]
    required: bool = True

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "SmokeTestContract":
        plugin = value.get("plugin")
        tests = value.get("tests")
        required = value.get("required", True)
        if not isinstance(plugin, str) or not plugin.strip():
            raise ValueError("plugin smoke contract requires a non-empty plugin")
        if not isinstance(tests, list) or any(not isinstance(item, str) or not item.strip() for item in tests):
            raise ValueError(f"plugin smoke contract tests must be a list of names: {plugin}")
        if not isinstance(required, bool):
            raise ValueError(f"plugin smoke contract required must be boolean: {plugin}")
        return cls(plugin=plugin, tests=tuple(tests), required=required)

    def as_dict(self) -> dict[str, Any]:
        return {"plugin": self.plugin, "required": self.required, "tests": list(self.tests)}


@dataclass(frozen=True)
class VerifyStep:
    name: str
    status: str
    message: str
    required: bool = True
    evidence: dict[str, Any] = field(default_factory=dict)
    diagnostic: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.status not in VERIFY_STATUSES:
            raise ValueError(f"unsupported verify status: {self.status}")

    def as_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "name": self.name,
            "status": self.status,
            "message": self.message,
            "required": self.required,
            "evidence": self.evidence,
        }
        if self.diagnostic is not None:
            value["diagnostic"] = self.diagnostic
        return value


@dataclass(frozen=True)
class VerifyContext:
    dsh_home: Path
    profile_name: str
    profile_path: Path
    mode: str
    current_environment: Mapping[str, Any]
    available_secret_names: frozenset[str]
    metadata_path: Path
    previous_steps: Mapping[str, VerifyStep]


class VerifyAdapter(Protocol):
    """Runtime adapter contract used by ``verify_profile``.

    ``run_step`` must perform the requested real action and return either a
    ``VerifyStep`` or a mapping with ``status``, ``message`` and ``evidence``.
    ``run_plugin_test`` is optional; if absent, plugin tests are UNTESTED.
    """

    def run_step(self, step: str, context: VerifyContext) -> VerifyStep | Mapping[str, Any]:
        ...


def _step(
    name: str,
    status: str,
    message: str,
    *,
    required: bool = True,
    evidence: Mapping[str, Any] | None = None,
    diagnostic: Mapping[str, Any] | None = None,
) -> VerifyStep:
    return VerifyStep(
        name=name,
        status=status,
        message=message,
        required=required,
        evidence=dict(evidence or {}),
        diagnostic=dict(diagnostic) if diagnostic else None,
    )


def _runtime_diagnostic(
    *,
    code: str,
    stage: str,
    message: str,
    evidence: Mapping[str, Any],
    item: str,
    expected: str,
    impact: str,
    can_continue: bool = False,
) -> dict[str, Any]:
    """Structured diagnostic attached to a failed runtime VerifyStep."""
    return {
        "code": code,
        "stage": stage,
        "severity": "BLOCKER",
        "item": item,
        "expected": expected,
        "observed": {"message": message, "code": code},
        "evidence": dict(evidence),
        "impact": impact,
        "canContinue": can_continue,
        "suggestedChecks": _default_checks(stage, code),
        "message": message,
    }


def _normalise_observation(name: str, value: VerifyStep | Mapping[str, Any], *, required: bool) -> VerifyStep:
    if isinstance(value, VerifyStep):
        return value
    if not isinstance(value, Mapping):
        return _step(
            name,
            "FAIL",
            "Verify adapter returned an invalid observation",
            required=required,
            evidence={"observedType": type(value).__name__},
        )
    status = value.get("status")
    if status not in VERIFY_STATUSES:
        return _step(
            name,
            "FAIL",
            "Verify adapter returned an unsupported status",
            required=required,
            evidence={"observed": dict(value)},
        )
    return _step(
        name,
        status,
        str(value.get("message", name)),
        required=bool(value.get("required", required)),
        evidence=value.get("evidence") if isinstance(value.get("evidence"), Mapping) else {},
    )


def _json_object(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        return None, str(error)
    if not isinstance(value, dict):
        return None, "JSON root must be an object"
    return value, None


def _package_manifest(profile_path: Path, name: str) -> tuple[dict[str, Any] | None, str | None]:
    package_path = profile_path / "node_modules" / Path(*name.split("/")) / "package.json"
    value, error = _json_object(package_path)
    if error:
        return None, f"{package_path}: {error}"
    return value, None


def _profile_bundles(profile_manifest: Mapping[str, Any]) -> tuple[list[str] | None, str | None]:
    dsh = profile_manifest.get("dsh", {})
    if dsh is None:
        dsh = {}
    if not isinstance(dsh, Mapping):
        return None, "profile package.json dsh must be an object"
    profile = dsh.get("profile", {})
    if profile is None:
        profile = {}
    if not isinstance(profile, Mapping):
        return None, "profile package.json dsh.profile must be an object"
    bundles = profile.get("bundles", [])
    if not isinstance(bundles, list) or any(not isinstance(name, str) or not name for name in bundles):
        return None, "profile package.json dsh.profile.bundles must be a list of names"
    if len(set(bundles)) != len(bundles):
        return None, "profile package.json dsh.profile.bundles contains duplicates"
    return list(bundles), None


def _resolve_installed_package_dir(anchor_dir: Path, name: str) -> Path | None:
    """Node-style node_modules lookup from an anchor directory.

    Mirrors DSH ``packageDirFromAnchor`` (installation anchor, then the profile
    directory): probes the profile-local ``node_modules``, the shared
    ``profiles/node_modules`` layer, home-level ``node_modules``, then each
    ancestor.  This matches what the Cordis Loader would import from the same
    anchor.
    """
    parts = Path(*name.split("/"))
    current = anchor_dir
    while True:
        candidate = current / "node_modules" / parts
        if (candidate / "package.json").is_file():
            return candidate
        parent = current.parent
        if parent == current:
            return None
        current = parent
    return None


def _internal_composition_issues(
    profile_path: Path,
    dependencies: Mapping[str, Any],
    bundles: Sequence[str],
) -> list[dict[str, Any]]:
    """Verify a Profile against its own manifest when no Pack metadata exists.

    Used when the Crate Import metadata directory for this Profile is absent
    (the Profile was not created by a Crate Import, or the metadata was
    removed).  This can never claim a Pack round-trip: it only checks that
    declared Bundles are installed with their patch files, and that declared
    dependencies resolve.  The caller marks the Pack-comparison dimension as
    UNTESTED.
    """
    issues: list[dict[str, Any]] = []
    declared = dict(dependencies) if isinstance(dependencies, Mapping) else {}
    for name in bundles:
        package_dir = _resolve_installed_package_dir(profile_path, name)
        if package_dir is None:
            issues.append({"code": "BUNDLE_NOT_INSTALLED", "bundle": name, "error": "not resolvable from the profile or shared node_modules layers"})
            continue
        installed, error = _json_object(package_dir / "package.json")
        if installed is None:
            issues.append({"code": "BUNDLE_NOT_INSTALLED", "bundle": name, "error": error})
            continue
        dsh = installed.get("dsh", {})
        if not isinstance(dsh, Mapping):
            dsh = {}
        bundle = dsh.get("bundle", {})
        patch = bundle.get("patch") if isinstance(bundle, Mapping) else None
        normalized_patch = posixpath.normpath(patch.replace("\\", "/")) if isinstance(patch, str) else ""
        safe_patch = (
            normalized_patch not in {"", ".", ".."}
            and not normalized_patch.startswith("../")
            and not normalized_patch.startswith("/")
            and ".." not in normalized_patch.split("/")
        )
        patch_path = package_dir / Path(*normalized_patch.split("/")) if safe_patch else None
        if not isinstance(patch, str) or not patch.strip() or patch_path is None or not patch_path.is_file():
            issues.append({
                "code": "BUNDLE_PATCH_MISSING",
                "bundle": name,
                "patch": patch,
                "path": str(patch_path) if patch_path else None,
            })
    for name, spec in declared.items():
        package_dir = _resolve_installed_package_dir(profile_path, name)
        if package_dir is None:
            issues.append({
                "code": "DEPENDENCY_NOT_INSTALLED",
                "plugin": name,
                "spec": spec,
                "error": "not resolvable from the profile or shared node_modules layers",
            })
    return issues


def _composition_step(options: "VerifyOptions") -> VerifyStep:
    profile_path = options.dsh_home / "profiles" / options.profile_name
    metadata_path = options.dsh_home / ".dsh-pack" / "imports" / options.profile_name
    package_path = profile_path / "package.json"
    profile_manifest, profile_error = _json_object(package_path)
    if profile_error or profile_manifest is None:
        return _step(
            "composition",
            "FAIL",
            "prepared Profile package.json cannot be read",
            evidence={"path": str(package_path), "error": profile_error},
        )
    bundles, bundle_error = _profile_bundles(profile_manifest)
    if bundle_error or bundles is None:
        return _step("composition", "FAIL", bundle_error or "invalid Bundle composition", evidence={"path": str(package_path)})

    manifest_file = metadata_path / "manifest.json"
    lock_file = metadata_path / "plugins.lock.json"
    prepared_file = metadata_path / "prepared.json"
    metadata_present = metadata_path.is_dir() and any(
        candidate.is_file() for candidate in (manifest_file, lock_file, prepared_file)
    )
    if not metadata_present:
        # This Profile was not created by a Crate Import, or the Import
        # metadata was removed.  The Pack-comparison dimension is UNTESTED:
        # only an internal consistency check against the Profile's own
        # manifest is possible, never a claimed round-trip.
        dependencies = profile_manifest.get("dependencies", {})
        if not isinstance(dependencies, Mapping):
            return _step(
                "composition",
                "FAIL",
                "Profile dependencies is not an object",
                evidence={"path": str(package_path)},
            )
        internal_issues = _internal_composition_issues(profile_path, dependencies, bundles)
        if internal_issues:
            return _step(
                "composition",
                "FAIL",
                "Crate Import metadata is absent and the Profile fails its internal consistency check",
                evidence={
                    "metadataPath": str(metadata_path),
                    "packComparison": "UNTESTED",
                    "issues": internal_issues,
                },
            )
        return _step(
            "composition",
            "DEGRADED",
            "Crate Import metadata is absent; only internal consistency was checked, Pack round-trip UNTESTED",
            evidence={
                "metadataPath": str(metadata_path),
                "profileBundles": bundles,
                "packComparison": "UNTESTED",
            },
        )
    metadata_manifest, manifest_error = _json_object(manifest_file)
    lock, lock_error = _json_object(lock_file)
    prepared, prepared_error = _json_object(prepared_file)
    if manifest_error or lock_error or prepared_error or metadata_manifest is None or lock is None or prepared is None:
        return _step(
            "composition",
            "FAIL",
            "prepared Import metadata is incomplete",
            evidence={
                "metadataPath": str(metadata_path),
                "manifestError": manifest_error,
                "lockError": lock_error,
                "preparedError": prepared_error,
            },
        )
    if prepared.get("status") != "prepared":
        return _step(
            "composition",
            "FAIL",
            "Import metadata is not marked prepared",
            evidence={"metadataPath": str(metadata_path), "preparedStatus": prepared.get("status")},
        )
    raw_plugins = lock.get("plugins")
    if not isinstance(raw_plugins, list) or any(not isinstance(plugin, Mapping) for plugin in raw_plugins):
        return _step("composition", "FAIL", "plugins.lock.json plugins is invalid", evidence={"path": str(metadata_path / "plugins.lock.json")})

    dependencies = profile_manifest.get("dependencies", {})
    if not isinstance(dependencies, Mapping):
        return _step("composition", "FAIL", "Profile dependencies is not an object", evidence={"path": str(package_path)})

    expected_bundles: list[str] = []
    installed_rows: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    for index, plugin in enumerate(raw_plugins):
        name = plugin.get("name")
        if not isinstance(name, str) or not name:
            issues.append({"code": "PLUGIN_NAME_MISSING", "index": index})
            continue
        requested = plugin.get("requested")
        requested_specifier = requested.get("specifier") if isinstance(requested, Mapping) else None
        resolved = plugin.get("resolved")
        resolved_version = resolved.get("version") if isinstance(resolved, Mapping) else None
        declared_spec = dependencies.get(name)
        if declared_spec is not None and declared_spec != requested_specifier:
            issues.append({
                "code": "PROFILE_SPEC_MISMATCH",
                "plugin": name,
                "expected": requested_specifier,
                "observed": declared_spec,
            })
        bundle = plugin.get("bundle")
        enabled = isinstance(bundle, Mapping) and bundle.get("enabled") is True
        if enabled:
            expected_bundles.append(name)
            patch = bundle.get("patch")
            package_path_for_plugin = profile_path / "node_modules" / Path(*name.split("/"))
            normalized_patch = posixpath.normpath(patch.replace("\\", "/")) if isinstance(patch, str) else ""
            safe_patch = (
                normalized_patch not in {"", ".", ".."}
                and not normalized_patch.startswith("../")
                and not normalized_patch.startswith("/")
                and ".." not in normalized_patch.split("/")
            )
            patch_path = package_path_for_plugin / Path(*normalized_patch.split("/")) if safe_patch else None
            if not isinstance(patch, str) or not patch.strip() or patch_path is None or not patch_path.is_file():
                issues.append({
                    "code": "BUNDLE_PATCH_MISSING",
                    "plugin": name,
                    "patch": patch,
                    "path": str(patch_path) if patch_path else None,
                })
        installed, installed_error = _package_manifest(profile_path, name)
        installed_row = {
            "name": name,
            "required": plugin.get("required") is True,
            "mode": (plugin.get("artifact") or {}).get("mode") if isinstance(plugin.get("artifact"), Mapping) else None,
            "expectedVersion": resolved_version,
            "installed": installed,
            "error": installed_error,
        }
        installed_rows.append(installed_row)
        if installed is None:
            issue = {"code": "PLUGIN_NOT_INSTALLED", "plugin": name, "error": installed_error}
            if plugin.get("required") is True:
                issues.append(issue)
            else:
                issue["optional"] = True
                issues.append(issue)
        else:
            mismatch = installed.get("name") != name or installed.get("version") != resolved_version
            if mismatch:
                issues.append({
                    "code": "PACKAGE_IDENTITY_MISMATCH",
                    "plugin": name,
                    "expected": {"name": name, "version": resolved_version},
                    "observed": {"name": installed.get("name"), "version": installed.get("version")},
                })

    if bundles != expected_bundles:
        issues.append({"code": "BUNDLE_ORDER_MISMATCH", "expected": expected_bundles, "observed": bundles})

    required_issues = [issue for issue in issues if not issue.get("optional")]
    if required_issues:
        status = "FAIL"
        message = "Profile composition does not match prepared Pack metadata"
    elif issues:
        status = "DEGRADED"
        message = "Profile composition is usable but optional plugin evidence is incomplete"
    else:
        status = "PASS"
        message = "Profile, lock, Bundle order, patches, and installed package identities agree"
    return _step(
        "composition",
        status,
        message,
        evidence={
            "profilePath": str(profile_path),
            "metadataPath": str(metadata_path),
            "profileBundles": bundles,
            "lockBundleOrder": expected_bundles,
            "installedPlugins": installed_rows,
            "pack": prepared.get("pack"),
            "issues": issues,
            "requiredSecrets": metadata_manifest.get("requiredSecrets", []),
        },
    )


@dataclass(frozen=True)
class VerifyOptions:
    dsh_home: Path
    profile_name: str
    mode: str = "web"
    current_environment: Mapping[str, Any] = field(default_factory=dict)
    available_secret_names: frozenset[str] = frozenset()
    adapter: VerifyAdapter | None = None
    plugin_contracts: tuple[SmokeTestContract, ...] = ()

    def __post_init__(self) -> None:
        if self.mode not in {"web", "headless"}:
            raise ValueError("VerifyOptions.mode must be 'web' or 'headless'")


@dataclass(frozen=True)
class VerifyResult:
    status: str
    dsh_home: Path
    profile_name: str
    mode: str
    current_environment: Mapping[str, Any]
    available_secret_names: frozenset[str]
    steps: tuple[VerifyStep, ...]
    plugin_contracts: tuple[SmokeTestContract, ...]

    def __post_init__(self) -> None:
        if self.status not in VERIFY_STATUSES:
            raise ValueError(f"unsupported verify result status: {self.status}")

    def as_dict(self) -> dict[str, Any]:
        step_map = {step.name: step.as_dict() for step in self.steps}
        plugin_smokes = [
            step.as_dict()
            for step in self.steps
            if step.name.startswith("plugin:")
        ]
        return {
            "status": self.status,
            "profile": {
                "name": self.profile_name,
                "dshHome": str(self.dsh_home),
                "path": str(self.dsh_home / "profiles" / self.profile_name),
            },
            "mode": self.mode,
            "environment": {"current": dict(self.current_environment)},
            "secrets": {
                "availableNames": sorted(self.available_secret_names),
                "valuesIncluded": False,
            },
            # Keep the ordered steps array for compatibility, while exposing
            # the stable Phase 5 machine-report fields required by callers.
            "composition": step_map.get("composition"),
            "boot": step_map.get("boot"),
            "ready": step_map.get("surface_ready"),
            "session": step_map.get("new_session"),
            "basicResponse": step_map.get("basic_response"),
            "coreTool": step_map.get("core_tool"),
            "pluginSmokes": plugin_smokes,
            "restart": step_map.get("restart"),
            "restartReady": step_map.get("restart_surface_ready"),
            "steps": [step.as_dict() for step in self.steps],
            "pluginSmokeContracts": [contract.as_dict() for contract in self.plugin_contracts],
        }


def _overall_status(steps: Sequence[VerifyStep]) -> str:
    required = [step for step in steps if step.required]
    optional = [step for step in steps if not step.required]
    if any(step.status == "FAIL" for step in required):
        return "FAIL"
    if any(step.status == "UNTESTED" for step in required):
        return "UNTESTED"
    if any(step.status in {"DEGRADED", "FAIL"} for step in required):
        return "DEGRADED"
    if any(step.status != "PASS" for step in optional):
        return "DEGRADED"
    return "PASS"


def _loader_composition_failure(composition: VerifyStep, boot: VerifyStep) -> dict[str, Any] | None:
    """Classify a real DSH Loader activation failure as composition failure.

    DSH resolves Bundle patches and activates their Loader entries during boot.
    A structurally valid Pack can therefore pass the local file checks while
    the effective composition still fails in the real runtime.  Keep the
    original ``boot=FAIL`` step, but attach the same runtime evidence to the
    composition step so a report can answer which Bundle prevented startup.
    """

    if boot.status != "FAIL":
        return None
    evidence = boot.evidence
    stderr = str(evidence.get("stderr", ""))
    stdout = str(evidence.get("stdout", ""))
    combined = f"{stderr}\n{stdout}"
    lowered = combined.lower()
    markers = (
        "plugin tree failed to load",
        "did not activate",
        "failed to apply loader entry",
        "loader activation failed",
    )
    if not any(marker in lowered for marker in markers):
        return None

    failed_bundle: str | None = None
    installed_plugins = composition.evidence.get("installedPlugins", [])
    if isinstance(installed_plugins, list):
        for row in installed_plugins:
            if not isinstance(row, Mapping):
                continue
            name = row.get("name")
            if not isinstance(name, str) or not name:
                continue
            if name in combined:
                failed_bundle = name
                break
    if failed_bundle is None:
        match = re.search(r"(?:failed to apply loader entry|did not activate)\s+([^\s:(]+)", combined, re.IGNORECASE)
        if match:
            failed_bundle = match.group(1)

    observed = "Loader activation failed" if "loader activation failed" in lowered else "DSH Loader activation failed"
    return {
        "stage": "composition",
        "failedBundle": failed_bundle,
        "observed": observed,
        "stderr": stderr,
        "impact": "Imported profile cannot start.",
        "bootMessage": boot.message,
    }


def _adapter_step(
    adapter: VerifyAdapter | None,
    name: str,
    context: VerifyContext,
    *,
    required: bool = True,
) -> VerifyStep:
    if adapter is None:
        return _step(
            name,
            "UNTESTED",
            "No runtime VerifyAdapter was supplied",
            required=required,
            evidence={"reason": "runtime execution is not implicit"},
        )
    method = getattr(adapter, "run_step", None)
    if not callable(method):
        return _step(
            name,
            "UNTESTED",
            "VerifyAdapter has no run_step implementation",
            required=required,
            evidence={"reason": "adapter contract missing"},
        )
    try:
        return _normalise_observation(name, method(name, context), required=required)
    except Exception as error:  # adapters are external execution boundaries
        return _step(
            name,
            "FAIL",
            f"VerifyAdapter failed during {name}",
            required=required,
            evidence={"error": str(error), "exception": type(error).__name__},
        )


def _plugin_step(
    adapter: VerifyAdapter | None,
    contract: SmokeTestContract,
    test_name: str,
    context: VerifyContext,
) -> VerifyStep:
    step_name = f"plugin:{contract.plugin}:{test_name}"
    if adapter is None or not callable(getattr(adapter, "run_plugin_test", None)):
        return _step(
            step_name,
            "UNTESTED",
            "No plugin smoke-test runner was supplied",
            required=contract.required,
            evidence={"plugin": contract.plugin, "test": test_name},
        )
    try:
        value = adapter.run_plugin_test(contract.plugin, test_name, context)  # type: ignore[attr-defined]
        observed = _normalise_observation(step_name, value, required=contract.required)
        if observed.required != contract.required:
            observed = VerifyStep(
                name=observed.name,
                status=observed.status,
                message=observed.message,
                required=contract.required,
                evidence=observed.evidence,
            )
        return observed
    except Exception as error:  # plugin tests are an external execution boundary
        return _step(
            step_name,
            "FAIL",
            f"Plugin smoke test failed to execute: {contract.plugin}/{test_name}",
            required=contract.required,
            evidence={"plugin": contract.plugin, "test": test_name, "error": str(error)},
        )


def verify_profile(options: VerifyOptions) -> VerifyResult:
    """Verify one prepared Profile without changing its files."""

    if not options.dsh_home.is_dir():
        result = VerifyResult(
            status="FAIL",
            dsh_home=options.dsh_home,
            profile_name=options.profile_name,
            mode=options.mode,
            current_environment=options.current_environment,
            available_secret_names=options.available_secret_names,
            steps=(_step("composition", "FAIL", "DSH_HOME does not exist", evidence={"dshHome": str(options.dsh_home)}),),
            plugin_contracts=options.plugin_contracts,
        )
        return result

    composition = _composition_step(options)
    steps: list[VerifyStep] = [composition]
    previous: dict[str, VerifyStep] = {composition.name: composition}
    context_base = {
        "dsh_home": options.dsh_home,
        "profile_name": options.profile_name,
        "profile_path": options.dsh_home / "profiles" / options.profile_name,
        "mode": options.mode,
        "current_environment": options.current_environment,
        "available_secret_names": options.available_secret_names,
        "metadata_path": options.dsh_home / ".dsh-pack" / "imports" / options.profile_name,
    }

    for name, label in RUNTIME_STEPS:
        blocking_runtime_step = next(
            (step.name for step in steps if step.name in {"boot", "restart"} and step.status == "FAIL"),
            None,
        )
        if composition.status == "FAIL":
            current = _step(
                name,
                "UNTESTED",
                f"{label} was not run because composition failed",
                evidence={"blockedBy": "composition"},
            )
        elif blocking_runtime_step is not None:
            current = _step(
                name,
                "UNTESTED",
                f"{label} was not run because an earlier runtime step failed",
                evidence={"blockedBy": blocking_runtime_step},
            )
        else:
            context = VerifyContext(previous_steps=dict(previous), **context_base)
            current = _adapter_step(options.adapter, name, context)
        steps.append(current)
        previous[current.name] = current

    for contract in options.plugin_contracts:
        for test_name in contract.tests:
            context = VerifyContext(previous_steps=dict(previous), **context_base)
            current = _plugin_step(options.adapter, contract, test_name, context)
            steps.append(current)
            previous[current.name] = current

    boot = next((step for step in steps if step.name == "boot"), None)
    runtime_composition_failure = (
        _loader_composition_failure(composition, boot)
        if boot is not None
        else None
    )
    if runtime_composition_failure is not None:
        composition = _step(
            "composition",
            "FAIL",
            "Bundle composition failed during DSH Loader activation",
            evidence={
                **composition.evidence,
                "runtimeFailure": runtime_composition_failure,
            },
        )
        steps[0] = composition

    result = VerifyResult(
        status=_overall_status(steps),
        dsh_home=options.dsh_home,
        profile_name=options.profile_name,
        mode=options.mode,
        current_environment=options.current_environment,
        available_secret_names=options.available_secret_names,
        steps=tuple(steps),
        plugin_contracts=options.plugin_contracts,
    )
    close = getattr(options.adapter, "close", None)
    if callable(close):
        try:
            close()
        except Exception:
            # Runtime cleanup evidence belongs to the adapter; do not replace
            # the actual verification result with a cleanup exception.
            pass
    return result


class SubprocessVerifyAdapter:
    """Explicit subprocess adapter for a real DSH or test runner.

    Configuration shape::

        {
          "mode": "web",
          "command": ["node", ".../bin.js", "--profile", "{profile}"],
          "cwd": "...",
          "timeoutSeconds": 60,
          "readyRegex": "dsh web: (?P<url>https?://[^\\s]+)",
          "expectedStatus": 200,
          "probes": {"new_session": ["..."], "core_tool": ["..."]},
          "pluginTests": {"plugin-a": {"loads": ["..."]}}
        }

    Commands are arrays, never shell strings.  ``{dsh_home}``, ``{profile}``,
    ``{profile_path}``, ``{url}``, and ``{pid}`` placeholders are available.
    Missing probe commands remain UNTESTED.  The adapter records full
    stdout/stderr in step evidence and never records environment values.
    """

    def __init__(self, config: Mapping[str, Any]) -> None:
        self.config = dict(config)
        self.mode = self.config.get("mode", "web")
        if self.mode not in {"web", "headless"}:
            raise ValueError("SubprocessVerifyAdapter mode must be 'web' or 'headless'")
        self.process: subprocess.Popen[str] | None = None
        self._logs: dict[str, list[str]] = {"stdout": [], "stderr": []}
        self._threads: list[threading.Thread] = []
        self._url: str | None = None
        self._last_headless: dict[str, Any] | None = None

    def _timeout(self) -> float:
        value = self.config.get("timeoutSeconds", 60)
        return float(value) if isinstance(value, (int, float)) and value > 0 else 60.0

    def _format(self, value: str, context: VerifyContext) -> str:
        values = {
            "dsh_home": str(context.dsh_home),
            "profile": context.profile_name,
            "profile_path": str(context.profile_path),
            "url": self._url or "",
            "pid": str(self.process.pid if self.process is not None else ""),
        }
        return value.format_map(values)

    def _command(self, key: str, context: VerifyContext) -> list[str] | None:
        raw = self.config.get("command") if key in {"boot", "restart"} else (self.config.get("probes", {}) or {}).get(key)
        if not isinstance(raw, list) or any(not isinstance(item, str) for item in raw):
            return None
        return [self._format(item, context) for item in raw]

    def _environment(self, context: VerifyContext) -> dict[str, str]:
        env = dict(os.environ) if self.config.get("inheritEnvironment", True) is not False else {}
        env["DSH_HOME"] = str(context.dsh_home)
        env["DSH_PROFILE"] = context.profile_name
        if self._url:
            env["DSH_WEB_URL"] = self._url
        extra = self.config.get("environment", {})
        if isinstance(extra, Mapping):
            env.update({str(key): str(value) for key, value in extra.items()})
        return env

    @staticmethod
    def _drain(stream, target: list[str]) -> None:
        try:
            for line in stream:
                target.append(line)
        finally:
            stream.close()

    def _logs_evidence(self) -> dict[str, Any]:
        return {"stdout": "".join(self._logs["stdout"]), "stderr": "".join(self._logs["stderr"])}

    def _spawn_web(self, context: VerifyContext) -> VerifyStep:
        command = self._command("boot", context)
        if command is None:
            return _step("boot", "UNTESTED", "runner config has no boot command", evidence={"mode": self.mode})
        self._logs = {"stdout": [], "stderr": []}
        try:
            cwd = self.config.get("cwd")
            self.process = subprocess.Popen(
                command,
                cwd=str(cwd) if isinstance(cwd, str) else None,
                env=self._environment(context),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            assert self.process.stdout is not None and self.process.stderr is not None
            self._threads = [
                threading.Thread(target=self._drain, args=(self.process.stdout, self._logs["stdout"]), daemon=True),
                threading.Thread(target=self._drain, args=(self.process.stderr, self._logs["stderr"]), daemon=True),
            ]
            for thread in self._threads:
                thread.start()
        except (OSError, ValueError) as error:
            evidence = {"command": command, "error": str(error)}
            return _step(
                "boot",
                "FAIL",
                "could not start runtime command",
                evidence=evidence,
                diagnostic=_runtime_diagnostic(
                    code="RUNNER_SPAWN_FAILED",
                    stage="runtime",
                    message="could not start runtime command",
                    evidence=evidence,
                    item="command",
                    expected="the runtime command starts and prints a ready URL",
                    impact="DSH runtime could not be started for verification.",
                ),
            )
        pattern = self.config.get("readyRegex", r"dsh web: (?P<url>https?://[^\s]+)")
        try:
            regex = re.compile(pattern if isinstance(pattern, str) else r"dsh web: (?P<url>https?://[^\s]+)")
        except re.error as error:
            self.close()
            evidence = {"error": str(error)}
            return _step(
                "boot",
                "FAIL",
                "runner readyRegex is invalid",
                evidence=evidence,
                diagnostic=_runtime_diagnostic(
                    code="RUNNER_READY_REGEX_INVALID",
                    stage="runtime",
                    message="runner readyRegex is invalid",
                    evidence=evidence,
                    item="readyRegex",
                    expected="a valid readyRegex that extracts the ready URL",
                    impact="DSH readiness could not be detected.",
                ),
            )
        deadline = time.monotonic() + self._timeout()
        while time.monotonic() < deadline:
            combined = "".join(self._logs["stdout"])
            match = regex.search(combined)
            if match:
                self._url = match.groupdict().get("url") or (match.group(1) if match.groups() else match.group(0))
                return _step("boot", "PASS", "runtime printed its ready URL", evidence={"pid": self.process.pid, "url": self._url, **self._logs_evidence()})
            code = self.process.poll()
            if code is not None:
                evidence = {"exitCode": code, **self._logs_evidence()}
                return _step(
                    "boot",
                    "FAIL",
                    "runtime exited before ready",
                    evidence=evidence,
                    diagnostic=_runtime_diagnostic(
                        code="RUNNER_EXITED_BEFORE_READY",
                        stage="runtime",
                        message="runtime exited before ready",
                        evidence=evidence,
                        item="runtime",
                        expected="the runtime process stays alive and prints a ready URL",
                        impact="The imported Profile cannot boot in the target DSH runtime.",
                    ),
                )
            time.sleep(0.05)
        self.close()
        evidence = {"timeoutSeconds": self._timeout(), **self._logs_evidence()}
        return _step(
            "boot",
            "FAIL",
            "runtime did not print a ready URL before timeout",
            evidence=evidence,
            diagnostic=_runtime_diagnostic(
                code="RUNNER_READY_TIMEOUT",
                stage="runtime",
                message="runtime did not print a ready URL before timeout",
                evidence=evidence,
                item="runtime",
                expected="the runtime prints a ready URL within the configured timeout",
                impact="DSH readiness could not be confirmed within the timeout.",
            ),
        )

    def _run_headless(self, context: VerifyContext, step_name: str = "boot") -> VerifyStep:
        command = self._command("boot", context)
        if command is None:
            return _step(step_name, "UNTESTED", "runner config has no headless command", evidence={"mode": self.mode})
        try:
            completed = subprocess.run(
                command,
                cwd=str(self.config["cwd"]) if isinstance(self.config.get("cwd"), str) else None,
                env=self._environment(context),
                capture_output=True,
                text=True,
                timeout=self._timeout(),
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            evidence = {"command": command, "error": str(error)}
            return _step(
                step_name,
                "FAIL",
                "headless runtime command failed to complete",
                evidence=evidence,
                diagnostic=_runtime_diagnostic(
                    code="HEADLESS_RUNNER_FAILED",
                    stage="runtime",
                    message="headless runtime command failed to complete",
                    evidence=evidence,
                    item="command",
                    expected="the headless runtime command completes successfully",
                    impact="The imported Profile could not be verified in headless mode.",
                ),
            )
        self._last_headless = {"exitCode": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr}
        evidence = {"command": command, **self._last_headless}
        if completed.returncode == 0:
            return _step(step_name, "PASS", "headless runtime completed", evidence=evidence)
        return _step(
            step_name,
            "FAIL",
            "headless runtime exited with failure",
            evidence=evidence,
            diagnostic=_runtime_diagnostic(
                code="HEADLESS_RUNNER_FAILED",
                stage="runtime",
                message="headless runtime exited with failure",
                evidence=evidence,
                item="runtime",
                expected="the headless runtime exits with code 0",
                impact="The imported Profile failed in headless runtime.",
            ),
        )

    def _probe(self, step: str, context: VerifyContext) -> VerifyStep:
        command = self._command(step, context)
        if command is None:
            return _step(step, "UNTESTED", f"no explicit {step} probe command was supplied", evidence={"mode": self.mode})
        try:
            completed = subprocess.run(
                command,
                cwd=str(self.config["cwd"]) if isinstance(self.config.get("cwd"), str) else None,
                env=self._environment(context),
                capture_output=True,
                text=True,
                timeout=self._timeout(),
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            evidence = {"command": command, "error": str(error)}
            return _step(
                step,
                "FAIL",
                f"{step} probe failed to complete",
                evidence=evidence,
                diagnostic=_runtime_diagnostic(
                    code="PROBE_FAILED",
                    stage="probe",
                    message=f"{step} probe failed to complete",
                    evidence=evidence,
                    item=step,
                    expected=f"the {step} probe command completes successfully",
                    impact=f"The {step} runtime capability could not be verified.",
                ),
            )
        evidence = {"command": command, "exitCode": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr}
        if completed.returncode == 0:
            return _step(step, "PASS", f"{step} probe completed", evidence=evidence)
        return _step(
            step,
            "FAIL",
            f"{step} probe failed",
            evidence=evidence,
            diagnostic=_runtime_diagnostic(
                code="PROBE_FAILED",
                stage="probe",
                message=f"{step} probe failed",
                evidence=evidence,
                item=step,
                expected=f"the {step} probe command exits with code 0",
                impact=f"The {step} runtime capability could not be verified.",
            ),
        )

    def _surface_ready(self, context: VerifyContext, step: str = "surface_ready") -> VerifyStep:
        if self.mode == "headless":
            if self._last_headless is None:
                return _step(step, "UNTESTED", "headless boot has not completed", evidence={})
            status = "PASS" if self._last_headless["exitCode"] == 0 else "FAIL"
            return _step(step, status, "headless completion is the ready signal", evidence=dict(self._last_headless))
        if not self._url:
            return _step(step, "UNTESTED", "boot did not provide a Web URL", evidence={})
        ownership = self._port_owner()
        if ownership["checked"] is not True:
            return _step(
                step,
                "UNTESTED",
                "could not verify that the Web port belongs to the test PID",
                evidence={"url": self._url, **ownership},
            )
        if ownership["portBelongsToProcess"] is not True:
            evidence = {"url": self._url, **ownership}
            return _step(
                step,
                "FAIL",
                "Web port does not belong to the test PID",
                evidence=evidence,
                diagnostic=_runtime_diagnostic(
                    code="WEB_PORT_NOT_OWNED",
                    stage="surface",
                    message="Web port does not belong to the test PID",
                    evidence=evidence,
                    item="port",
                    expected="the listening port belongs to the runtime process being verified",
                    impact="Another process may occupy the DSH Web port.",
                ),
            )
        try:
            with urllib.request.urlopen(self._url, timeout=self._timeout()) as response:
                code = response.status
                body = response.read()
        except (OSError, urllib.error.URLError) as error:
            evidence = {"url": self._url, "error": str(error), "pid": self.process.pid if self.process else None}
            return _step(
                step,
                "FAIL",
                "Web URL did not return an HTTP response",
                evidence=evidence,
                diagnostic=_runtime_diagnostic(
                    code="WEB_HTTP_UNREACHABLE",
                    stage="surface",
                    message="Web URL did not return an HTTP response",
                    evidence=evidence,
                    item="url",
                    expected="the DSH Web URL returns an HTTP response",
                    impact="The DSH Web surface is not reachable.",
                ),
            )
        expected = self.config.get("expectedStatus", 200)
        status = "PASS" if code == expected else "FAIL"
        evidence = {"url": self._url, "pid": self.process.pid if self.process else None, **ownership, "status": code, "expectedStatus": expected, "responseBytes": len(body)}
        if status == "PASS":
            return _step(step, "PASS", "Web HTTP readiness probe completed", evidence=evidence)
        return _step(
            step,
            "FAIL",
            "Web HTTP status did not match expected",
            evidence=evidence,
            diagnostic=_runtime_diagnostic(
                code="WEB_HTTP_STATUS_MISMATCH",
                stage="surface",
                message="Web HTTP status did not match expected",
                evidence=evidence,
                item="url",
                expected=f"the DSH Web URL returns HTTP {expected}",
                impact="The DSH Web surface returned an unexpected HTTP status.",
            ),
        )

    def _port_owner(self) -> dict[str, Any]:
        """Check the listening PID for the adapter's URL without third-party dependencies."""

        if self.process is None or not self._url:
            return {"checked": False, "portOwnerPid": None, "portBelongsToProcess": False, "ownershipError": "process or URL is unavailable"}
        return self._port_owner_for(self._url, self.process.pid)

    @staticmethod
    def _port_owner_for(url: str | None, pid: int | None) -> dict[str, Any]:
        if not url or pid is None:
            return {"checked": False, "portOwnerPid": None, "portBelongsToProcess": False, "ownershipError": "process or URL is unavailable"}
        parsed = urllib.parse.urlparse(url)
        if parsed.port is None:
            return {"checked": False, "portOwnerPid": None, "portBelongsToProcess": False, "ownershipError": "URL has no port"}
        if os.name != "nt":
            return {"checked": False, "portOwnerPid": None, "portBelongsToProcess": False, "ownershipError": "port ownership probe is currently implemented for Windows netstat"}
        try:
            completed = subprocess.run(
                ["netstat", "-ano", "-p", "tcp"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            return {"checked": False, "portOwnerPid": None, "portBelongsToProcess": False, "ownershipError": str(error)}
        port_owner: int | None = None
        for line in completed.stdout.splitlines():
            fields = line.split()
            if len(fields) < 5 or fields[0].upper() != "TCP" or fields[3].upper() != "LISTENING":
                continue
            port_match = re.search(r":(\d+)$", fields[1])
            if port_match is None or int(port_match.group(1)) != parsed.port:
                continue
            try:
                port_owner = int(fields[4])
            except ValueError:
                continue
            break
        return {
            "checked": True,
            "portOwnerPid": port_owner,
            "portBelongsToProcess": port_owner == pid,
        }

    def run_step(self, step: str, context: VerifyContext) -> VerifyStep:
        if step == "boot":
            return self._run_headless(context) if self.mode == "headless" else self._spawn_web(context)
        if step == "surface_ready" or step == "restart_surface_ready":
            return self._surface_ready(context, step)
        if step == "restart":
            stopped = self.close()
            restarted = self._run_headless(context, step) if self.mode == "headless" else self._rename(self._spawn_web(context), step)
            evidence = dict(restarted.evidence)
            evidence["stoppedProcess"] = stopped
            if restarted.status == "PASS" and stopped.get("portReleased") is not True:
                return _step(
                    step,
                    "FAIL",
                    "restart completed without proof that the previous process port was released",
                    evidence=evidence,
                    diagnostic=_runtime_diagnostic(
                        code="RESTART_PORT_NOT_RELEASED",
                        stage="restart",
                        message="restart completed without proof that the previous process port was released",
                        evidence=evidence,
                        item="port",
                        expected="the previous runtime process releases the Web port before restart",
                        impact="The restarted DSH may conflict with a stale process on the same port.",
                    ),
                )
            return VerifyStep(
                name=restarted.name,
                status=restarted.status,
                message=restarted.message,
                required=restarted.required,
                evidence=evidence,
                diagnostic=restarted.diagnostic,
            )
        if step in {"new_session", "basic_response", "core_tool"}:
            return self._probe(step, context)
        return _step(step, "UNTESTED", f"unsupported subprocess verify step: {step}", evidence={})

    @staticmethod
    def _rename(value: VerifyStep, name: str) -> VerifyStep:
        return VerifyStep(name=name, status=value.status, message=value.message, required=value.required, evidence=value.evidence, diagnostic=value.diagnostic)

    def run_plugin_test(self, plugin: str, test_name: str, context: VerifyContext) -> VerifyStep:
        configured = self.config.get("pluginTests", {})
        command = configured.get(plugin, {}).get(test_name) if isinstance(configured, Mapping) and isinstance(configured.get(plugin), Mapping) else None
        if not isinstance(command, list) or any(not isinstance(item, str) for item in command):
            return _step(f"plugin:{plugin}:{test_name}", "UNTESTED", "no explicit plugin smoke command was supplied", required=True, evidence={"plugin": plugin, "test": test_name})
        command = [self._format(item, context) for item in command]
        try:
            completed = subprocess.run(command, cwd=str(self.config["cwd"]) if isinstance(self.config.get("cwd"), str) else None, env=self._environment(context), capture_output=True, text=True, timeout=self._timeout(), check=False)
        except (OSError, subprocess.TimeoutExpired) as error:
            evidence = {"command": command, "error": str(error)}
            return _step(
                f"plugin:{plugin}:{test_name}",
                "FAIL",
                "plugin smoke command failed to complete",
                required=True,
                evidence=evidence,
                diagnostic=_runtime_diagnostic(
                    code="PLUGIN_SMOKE_FAILED",
                    stage="plugin-smoke",
                    message="plugin smoke command failed to complete",
                    evidence=evidence,
                    item=plugin,
                    expected=f"the plugin smoke command for {plugin} completes successfully",
                    impact=f"Plugin {plugin} smoke test could not be verified.",
                ),
            )
        evidence = {"command": command, "exitCode": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr}
        if completed.returncode == 0:
            return _step(f"plugin:{plugin}:{test_name}", "PASS", "plugin smoke command completed", required=True, evidence=evidence)
        return _step(
            f"plugin:{plugin}:{test_name}",
            "FAIL",
            "plugin smoke command failed",
            required=True,
            evidence=evidence,
            diagnostic=_runtime_diagnostic(
                code="PLUGIN_SMOKE_FAILED",
                stage="plugin-smoke",
                message="plugin smoke command failed",
                evidence=evidence,
                item=plugin,
                expected=f"the plugin smoke command for {plugin} exits with code 0",
                impact=f"Plugin {plugin} smoke test failed.",
            ),
        )

    def close(self) -> dict[str, Any]:
        process = self.process
        url = self._url
        if process is None:
            return {"pid": None, "url": url, "processExited": True, "portReleased": True, "reason": "no persistent process"}
        pid = process.pid
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        exit_code = process.poll()
        port_evidence: dict[str, Any] = {"checked": True, "portOwnerPid": None, "portBelongsToProcess": False}
        port_released = True
        if self.mode == "web" and url:
            deadline = time.monotonic() + 2.0
            while True:
                port_evidence = self._port_owner_for(url, pid)
                if port_evidence.get("checked") is not True:
                    port_released = False
                    break
                if port_evidence.get("portOwnerPid") is None:
                    port_released = True
                    break
                if time.monotonic() >= deadline:
                    port_released = False
                    break
                time.sleep(0.05)
        evidence = {
            "pid": pid,
            "url": url,
            "exitCode": exit_code,
            "processExited": process.poll() is not None,
            "portReleased": port_released,
            "portEvidence": port_evidence,
        }
        self.process = None
        self._url = None
        return evidence


def load_smoke_contracts(path: str | os.PathLike[str]) -> tuple[SmokeTestContract, ...]:
    """Load one JSON object or an array of plugin smoke contracts."""

    value = json.loads(Path(path).read_text(encoding="utf-8"))
    values = value if isinstance(value, list) else [value]
    if any(not isinstance(item, Mapping) for item in values):
        raise ValueError("plugin contract JSON must contain an object or an array of objects")
    return tuple(SmokeTestContract.from_mapping(item) for item in values)
