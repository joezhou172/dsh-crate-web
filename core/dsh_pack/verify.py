"""Phase 5 verification for a prepared DSH Profile.

The core owns composition checks, status aggregation, evidence shape, and the
plugin smoke-test contract.  Runtime execution is deliberately injected via a
``VerifyAdapter`` so this module never guesses a DSH command, health endpoint,
or model interaction.  Without an adapter, runtime checks are UNTESTED.
"""

from __future__ import annotations

import json
import errno
import ipaddress
import os
import posixpath
import re
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from .errors import _default_checks
from .errors import DshPackError
from .bundle import check_patch_declaration, read_bundle_patches
from .identity import expected_install_version
from .pack import sha256_bytes
from .preflight import _artifact_package_identity
from dataclasses import dataclass, field, replace
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
    from .diagnostics import envelope_fields
    return {
        **envelope_fields(operation="verify", status="FAIL"),
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
        # 步骤身份和必测要求由 Core 决定；适配器标签不能绕过
        # 前置失败，也不能弱化最终状态。保留适配器的原始证据。
        return VerifyStep(
            name=name,
            status=value.status,
            message=value.message,
            required=required,
            evidence=value.evidence,
            diagnostic=value.diagnostic,
        )
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
        required=required,
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

    metadata_manifest, manifest_error = _json_object(metadata_path / "manifest.json")
    lock, lock_error = _json_object(metadata_path / "plugins.lock.json")
    prepared, prepared_error = _json_object(metadata_path / "prepared.json")
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
    installation = prepared.get('installation')
    rebuilt = isinstance(installation, Mapping) and installation.get('resolver') == 'pnpm'
    original_dependencies = None
    if rebuilt:
        try:
            original_bytes = (profile_path / '.dsh-crate/original-package.json').read_bytes()
            if sha256_bytes(original_bytes) != installation.get('originalManifestSha256'):
                raise ValueError('original manifest hash mismatch')
            if sha256_bytes((profile_path / 'pnpm-workspace.yaml').read_bytes()) != installation.get('workspaceSha256'):
                raise ValueError('generated installation workspace hash mismatch')
            adaptation = installation.get('profilePatchAdaptation')
            if isinstance(adaptation, Mapping) and adaptation.get('changed') is True:
                if adaptation.get('adapter') != 'official-desktop-composition-equivalence-v1':
                    raise ValueError('unsupported Profile patch adaptation identity')
                if sha256_bytes((profile_path / '.dsh-crate/original-profile-config/cordis.patch.yml').read_bytes()) != adaptation.get('originalSha256'):
                    raise ValueError('original Profile patch hash mismatch')
                if sha256_bytes((profile_path / 'cordis.patch.yml').read_bytes()) != adaptation.get('runtimeSha256'):
                    raise ValueError('adapted runtime Profile patch hash mismatch')
                if not isinstance(adaptation.get('loaderTreeSha256'), str) or not re.fullmatch('[a-f0-9]{64}', adaptation['loaderTreeSha256']):
                    raise ValueError('official Loader equivalence evidence is invalid')
                removed = adaptation.get('removedNames')
                if not isinstance(removed, list) or not removed or any(not isinstance(row, Mapping) or set(row) != {'id', 'name'} or not all(isinstance(value, str) and value for value in row.values()) for row in removed):
                    raise ValueError('Profile patch adaptation record is invalid')
            original_dependencies = json.loads(original_bytes).get('dependencies', {})
            if not isinstance(original_dependencies, Mapping):
                raise ValueError('original dependencies must be an object')
            modules, error = _json_object(profile_path / 'node_modules/.modules.yaml')
            if error or modules is None or modules.get('nodeLinker') != 'hoisted' or not (profile_path / 'pnpm-lock.yaml').is_file():
                raise ValueError('pnpm installation records are incomplete')
            store = modules.get('virtualStoreDir')
            if not isinstance(store, str) or (profile_path / 'node_modules' / store).resolve() != (profile_path / 'node_modules/.pnpm').resolve():
                raise ValueError('pnpm virtual store does not match the prepared Profile')
        except (OSError, ValueError, TypeError) as error:
            issues.append({'code': 'REBUILD_STATE_INVALID', 'message': str(error)})
    for index, plugin in enumerate(raw_plugins):
        name = plugin.get("name")
        if not isinstance(name, str) or not name:
            issues.append({"code": "PLUGIN_NAME_MISSING", "index": index})
            continue
        requested = plugin.get("requested")
        requested_specifier = requested.get("specifier") if isinstance(requested, Mapping) else None
        resolved_version = expected_install_version(plugin)
        declared_spec = dependencies.get(name)
        installed, installed_error = _package_manifest(profile_path, name)
        prepared_names = {row.get('name') for row in prepared.get('plugins', []) if isinstance(row, Mapping)}
        skipped_optional = plugin.get('required') is not True and name not in prepared_names and installed is None and declared_spec is None
        if rebuilt and not skipped_optional:
            try:
                requests = installation.get('requests', {})
                spec = requests.get(name) if isinstance(requests, Mapping) else None
                match = re.fullmatch(r'file:\./\.dsh-crate/artifacts/([0-9a-f]{64})\.tgz', spec or '')
                if not match or declared_spec != spec:
                    raise ValueError('local artifact dependency mapping mismatch')
                if original_dependencies is None or original_dependencies.get(name, 'unknown') != requested_specifier:
                    raise ValueError('original Profile SPEC does not match plugins.lock')
                artifact = plugin.get('artifact', {})
                if artifact.get('mode') == 'embedded' and artifact.get('sha256') != match[1]:
                    raise ValueError('embedded artifact mapping differs from plugins.lock hash')
                path = profile_path / '.dsh-crate/artifacts' / (match[1] + '.tgz')
                if path.is_symlink() or path.resolve().parent != (profile_path / '.dsh-crate/artifacts').resolve():
                    raise ValueError('artifact path escapes the prepared Profile')
                content = path.read_bytes()
                if sha256_bytes(content) != match[1]:
                    raise ValueError('local rebuild artifact hash mismatch')
                identity = _artifact_package_identity(content)
                if identity != {'name': name, 'version': resolved_version}:
                    raise ValueError('local rebuild artifact identity mismatch')
            except (OSError, ValueError, TypeError) as error:
                issues.append({'code': 'REBUILD_ARTIFACT_INVALID', 'plugin': name, 'message': str(error)})
        elif declared_spec is not None and declared_spec != requested_specifier:
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
        if enabled and not skipped_optional:
            patch = bundle.get("patch")
            package_path_for_plugin = profile_path / "node_modules" / Path(*name.split("/"))
            try:
                read_bundle_patches(package_path_for_plugin, patch)
                if installed is not None:
                    check_patch_declaration(installed, patch)
            except DshPackError as error:
                issues.append({
                    "code": "BUNDLE_PATCH_INVALID",
                    "plugin": name,
                    "patch": patch,
                    "error": str(error),
                })
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
    business_status: str | None = None

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
            "businessStatus": self.business_status or self.status,
            "cleanup": step_map.get("cleanup"),
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


def _cleanup_status(evidence: Mapping[str, Any]) -> str:
    """缺失证据不能当作释放成功；此前失败的清理也不能被末次成功遮蔽。"""
    attempts = evidence.get("attempts", [])
    if isinstance(attempts, list) and any(
        isinstance(item, Mapping) and _cleanup_status(item) == "FAIL" for item in attempts
    ):
        return "FAIL"
    endpoints = evidence.get("endpoints", [])
    endpoints = endpoints if isinstance(endpoints, list) else []
    if (evidence.get("status") == "FAIL" or evidence.get("errors") or evidence.get("processExited") is False
            or evidence.get("portReleased") is False
            or any(isinstance(item, Mapping) and item.get("released") is False for item in endpoints)):
        return "FAIL"
    if evidence.get("processExited") is not True:
        return "UNTESTED"
    if evidence.get("portApplicable") is not False and evidence.get("portReleased") is not True:
        return "UNTESTED"
    if evidence.get("portApplicable") is not False and (
        not isinstance(evidence.get("portEvidence"), Mapping)
        or evidence["portEvidence"].get("checked") is not True
    ):
        return "UNTESTED"
    if evidence.get("endpointsApplicable") is not False and (
        not endpoints or any(not isinstance(item, Mapping) or item.get("checked") is not True
                             or item.get("released") is not True for item in endpoints)
    ):
        return "UNTESTED"
    if isinstance(attempts, list) and any(
        not isinstance(item, Mapping) or _cleanup_status(item) != "PASS" for item in attempts
    ):
        return "UNTESTED"
    return "PASS"


def _cleanup_step(adapter: VerifyAdapter | None) -> VerifyStep:
    close = getattr(adapter, "close", None)
    if not callable(close):
        return _step("cleanup", "UNTESTED", "未提供可核查的最终清理接口",
                     evidence={"processExited": None, "portReleased": None, "endpoints": [],
                               "reason": "VerifyAdapter has no close implementation"})
    try:
        value = close()
    except Exception as error:
        evidence = {"processExited": None, "portReleased": None, "endpoints": [],
                    "error": str(error), "exception": type(error).__name__}
        return _step("cleanup", "FAIL", "最终清理抛出异常；原业务步骤和诊断已保留", evidence=evidence,
                     diagnostic=_runtime_diagnostic(
                         code="VERIFY_CLEANUP_EXCEPTION", stage="cleanup", message="最终清理抛出异常",
                         evidence=evidence, item="cleanup", expected="清理完成并返回资源释放证据",
                         impact="无法确认验证资源已释放；请检查 cleanup 证据中的进程和端点。"))
    evidence = dict(value) if isinstance(value, Mapping) else {
        "processExited": None, "portReleased": None, "endpoints": [],
        "reason": "close returned no resource evidence"}
    status = _cleanup_status(evidence)
    diagnostic = None
    if status != "PASS":
        diagnostic = _runtime_diagnostic(
            code="VERIFY_CLEANUP_FAILED" if status == "FAIL" else "VERIFY_CLEANUP_UNVERIFIED",
            stage="cleanup", message="最终清理失败" if status == "FAIL" else "最终清理证据不足",
            evidence=evidence, item="cleanup", expected="已观察进程、端口和端点均有释放证据",
            impact="原业务步骤和诊断已保留；资源释放状态请单独检查。")
    return _step("cleanup", status,
                 {"PASS": "已核查所记录资源的释放", "FAIL": "清理失败；原业务步骤和诊断已保留",
                  "UNTESTED": "清理证据不足；未将未知状态判为成功"}[status],
                 evidence=evidence, diagnostic=diagnostic)


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

    # 只接受失败行明确命名的条目；全局启动日志和安装顺序不能证明归属。
    # 运行条目可能是未直接列在 Bundle 清单中的包或 subpath，必须保留原名。
    target_pattern = re.compile(
        r"(?P<marker>plugin tree failed to load\s*:\s*|failed to apply loader entry\s+|did not activate\s+)"
        r"[`\"']?(?P<target>(?:@[\w.-]+/)?[\w.-]+(?:/[\w.-]+)*)[`\"']?(?=\s*(?::|$))",
        re.IGNORECASE,
    )
    installed_plugins = composition.evidence.get("installedPlugins", [])
    installed_names = {
        row["name"] for row in installed_plugins
        if isinstance(row, Mapping) and isinstance(row.get("name"), str) and row["name"]
    } if isinstance(installed_plugins, list) else set()
    failed_targets: set[str] = set()
    for line in combined.splitlines():
        if not any(marker in line.lower() for marker in markers):
            continue
        for match in target_pattern.finditer(line):
            target = match.group("target")
            if target.lower() in {"error", "typeerror", "rangeerror", "exception"}:
                continue
            # 泛化的等待失败文案不是 Loader 证据；只有明确包名才可归属。
            if match.group("marker").lower().startswith("did not activate"):
                if not (target.startswith("@") or any(target == name or target.startswith(name + "/") for name in installed_names)):
                    continue
            failed_targets.add(target)
        for name in installed_names:
            if re.search(r"(?<![\w@./-])" + re.escape(name) + r"\s+did not activate\b", line, re.IGNORECASE):
                failed_targets.add(name)
    has_loader_failure = any(marker in lowered for marker in markers if marker != "did not activate")
    if not has_loader_failure and not failed_targets:
        return None
    failed_bundle = next(iter(failed_targets)) if len(failed_targets) == 1 else None

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


def _runtime_blocker(steps: list[VerifyStep]) -> str | None:
    """Preserve the first failure; never probe or restart past missing startup evidence."""
    runtime_names = {name for name, _ in RUNTIME_STEPS}
    prerequisites = {"boot", "surface_ready", "restart", "restart_surface_ready"}
    return next((step.name for step in steps if step.name in runtime_names
                 and (step.status == "FAIL" or (step.name in prerequisites
                      and step.status not in {"PASS", "DEGRADED"}))), None)


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
            business_status="FAIL",
        )
        cleanup = _cleanup_step(options.adapter)
        return replace(result, steps=(*result.steps, cleanup))

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
        blocking_runtime_step = _runtime_blocker(steps)
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
                f"{label} was not run because an earlier runtime prerequisite did not pass",
                evidence={"blockedBy": blocking_runtime_step},
            )
        else:
            context = VerifyContext(previous_steps=dict(previous), **context_base)
            current = _adapter_step(options.adapter, name, context)
        steps.append(current)
        previous[current.name] = current

    # The imported lock, rather than the caller's contract list, defines which
    # plugin capabilities must be accounted for. A missing or empty contract
    # is explicit missing evidence, never an implicit successful smoke test.
    imported_plugins = composition.evidence.get("installedPlugins", [])
    imported_required = {
        row["name"]: row.get("required") is True
        for row in imported_plugins
        if isinstance(row, Mapping) and isinstance(row.get("name"), str)
    } if isinstance(imported_plugins, list) else {}
    contracts = [
        SmokeTestContract(
            plugin=contract.plugin,
            tests=tuple(test for test in contract.tests if isinstance(test, str) and test.strip()),
            required=contract.required or imported_required.get(contract.plugin, False),
        )
        for contract in options.plugin_contracts
    ]
    covered_plugins = {contract.plugin for contract in contracts}
    contracts.extend(
        SmokeTestContract(plugin=name, tests=(), required=required)
        for name, required in imported_required.items()
        if name not in covered_plugins
    )
    blocking_plugin_step = ("composition" if composition.status not in {"PASS", "DEGRADED"}
                            else _runtime_blocker(steps))
    for contract in contracts:
        for test_name in contract.tests or (None,):
            step_name = f"plugin:{contract.plugin}:{test_name or 'untested'}"
            if blocking_plugin_step is not None:
                current = _step(
                    step_name, "UNTESTED", "Plugin smoke test was not run because runtime prerequisites did not pass",
                    required=contract.required,
                    evidence={"plugin": contract.plugin, "test": test_name, "blockedBy": blocking_plugin_step},
                )
            elif test_name is None:
                current = _step(
                    step_name, "UNTESTED", "Imported plugin has no non-empty dedicated smoke-test contract",
                    required=contract.required,
                    evidence={"plugin": contract.plugin, "test": None, "reason": "missing smoke-test contract"},
                )
            else:
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

    business_status = _overall_status(steps)
    steps.append(_cleanup_step(options.adapter))
    result = VerifyResult(
        status=_overall_status(steps),
        dsh_home=options.dsh_home,
        profile_name=options.profile_name,
        mode=options.mode,
        current_environment=options.current_environment,
        available_secret_names=options.available_secret_names,
        steps=tuple(steps),
        plugin_contracts=tuple(contracts),
        business_status=business_status,
    )
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
        self._cleanup_attempts: list[dict[str, Any]] = []
        self._last_cleanup: dict[str, Any] | None = None

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
        if self._url:
            env["DSH_WEB_URL"] = self._url
        extra = self.config.get("environment", {})
        if isinstance(extra, Mapping):
            env.update({str(key): str(value) for key, value in extra.items()})
        # Windows environment names are case-insensitive. Remove all inherited
        # and configured aliases before assigning the actual isolated target.
        env = {key: value for key, value in env.items() if key.upper() not in {"DSH_HOME", "DSH_PROFILE"}}
        env["DSH_HOME"] = str(context.dsh_home)
        env["DSH_PROFILE"] = context.profile_name
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
        if completed.returncode != 0:
            return {"checked": False, "portOwnerPid": None, "portBelongsToProcess": False,
                    "ownershipError": "netstat failed", "exitCode": completed.returncode}
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
            # 已完成的headless命令没有Web端口；不适用不是“释放未知”。
            no_web_port = (self.mode == "headless" and stopped.get("processExited") is True
                           and stopped.get("portApplicable") is False)
            if restarted.status == "PASS" and stopped.get("portReleased") is not True and not no_web_port:
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

    @staticmethod
    def _endpoint_release(url: str) -> dict[str, Any]:
        """只核查已观察的本地 TCP 端点；拒绝连接才证明监听已释放。"""
        evidence: dict[str, Any] = {"checked": False, "released": None, "transport": "tcp"}
        try:
            parsed = urllib.parse.urlparse(url)
            address = ipaddress.ip_address(parsed.hostname or "")
            if not address.is_loopback or parsed.port is None:
                raise ValueError("only explicit loopback endpoints with a port are checked")
            evidence.update({"url": f"{parsed.scheme}://{'[' + str(address) + ']' if address.version == 6 else address}:{parsed.port}",
                             "host": str(address), "port": parsed.port})
            with socket.socket(socket.AF_INET6 if address.version == 6 else socket.AF_INET, socket.SOCK_STREAM) as client:
                client.settimeout(0.3)
                code = client.connect_ex((str(address), parsed.port))
            evidence["socketError"] = code
            if code == 0:
                evidence.update(checked=True, released=False)
            elif code in {errno.ECONNREFUSED, 10061}:
                evidence.update(checked=True, released=True)
            else:
                evidence["reason"] = "连接结果不能证明端点已释放"
        except (OSError, ValueError) as error:
            evidence["reason"] = str(error)
        return evidence

    def close(self) -> dict[str, Any]:
        process = self.process
        url = self._url
        if process is None:
            if self._last_cleanup is not None:
                return self._last_cleanup
            completed = self._last_headless is not None
            return {"pid": None, "url": None, "processExited": True if completed else None,
                    "exitCode": self._last_headless.get("exitCode") if completed else None,
                    "portReleased": None, "portApplicable": False, "endpointsApplicable": False,
                    "endpoints": [], "attempts": [],
                    "reason": "headless subprocess.run completed" if completed else "no runtime process was observed"}
        pid = process.pid
        actions: list[str] = []
        errors: list[dict[str, str]] = []
        exit_code = None
        try:
            if process.poll() is None:
                actions.append("terminate")
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    actions.append("kill")
                    process.kill()
                    process.wait(timeout=5)
            exit_code = process.poll()
        except Exception as error:
            errors.append({"operation": "stop-process", "error": str(error), "exception": type(error).__name__})
            try:
                exit_code = process.poll()
            except Exception as poll_error:
                errors.append({"operation": "poll-process", "error": str(poll_error), "exception": type(poll_error).__name__})
        port_evidence: dict[str, Any] = {"checked": False, "reason": "no observed Web URL"}
        port_released: bool | None = None
        endpoints: list[dict[str, Any]] = []
        if self.mode == "web" and url:
            deadline = time.monotonic() + 2.0
            while True:
                try:
                    port_evidence = self._port_owner_for(url, pid)
                except Exception as error:
                    port_evidence = {"checked": False, "ownershipError": str(error)}
                endpoints = [{"url": url, **self._endpoint_release(url)}]
                if port_evidence.get("checked") is not True:
                    port_released = None
                    break
                port_released = port_evidence.get("portOwnerPid") is None
                if port_released and endpoints[0].get("released") is True:
                    break
                if time.monotonic() >= deadline:
                    break
                time.sleep(0.05)
        for thread in self._threads:
            thread.join(timeout=1)
        evidence = {
            "pid": pid,
            "url": url,
            "exitCode": exit_code,
            "processExited": True if exit_code is not None else (False if not errors else None),
            "portReleased": port_released,
            "portEvidence": port_evidence,
            "portApplicable": self.mode == "web", "endpointsApplicable": self.mode == "web",
            "endpoints": endpoints,
            "endpointCoverage": "observed-web-url-only; Inspector/PTY/unknown descendants are not inferred",
            "actions": actions, "errors": errors,
        }
        self._cleanup_attempts.append(evidence)
        self._last_cleanup = {**evidence, "attempts": list(self._cleanup_attempts)}
        self.process = None
        self._url = None
        return self._last_cleanup


def load_smoke_contracts(path: str | os.PathLike[str]) -> tuple[SmokeTestContract, ...]:
    """Load one JSON object or an array of plugin smoke contracts."""

    value = json.loads(Path(path).read_text(encoding="utf-8"))
    values = value if isinstance(value, list) else [value]
    if any(not isinstance(item, Mapping) for item in values):
        raise ValueError("plugin contract JSON must contain an object or an array of objects")
    return tuple(SmokeTestContract.from_mapping(item) for item in values)
