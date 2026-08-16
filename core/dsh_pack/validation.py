"""Strict Phase 1 schema and archive-path validation.

The validators intentionally describe only the first Pack format. They do not
try to infer DSH compatibility, install packages, or interpret third-party
plugin behavior.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from .errors import PathSafetyError, SchemaValidationError

SCHEMA_VERSION = 1
PACK_FORMAT = "dshcrate"
LEGACY_PACK_FORMATS = {PACK_FORMAT, "dshpack"}
PACK_VERSION = "0.1.0"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SECRET_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_PACKAGE_NAME_RE = re.compile(r"^(?:@[^/\s]+/)?[^/\s]+$")
_SOURCE_TYPES = {"registry", "git", "file", "link", "tarball", "alias", "workspace", "unknown"}
_RUNTIME_SOURCES = {"installation-anchor", "profile-dependency", "unknown"}
_ARTIFACT_MODES = {"embedded", "reference-only"}
_FORBIDDEN_PATH_COMPONENTS = {"node_modules", ".git", "cache", "logs"}
_FORBIDDEN_FILENAMES = {
    ".credentials.yaml",
    ".credentials.yml",
    ".env",
    ".env.local",
    "credentials.json",
    "credentials.yaml",
    "credentials.yml",
}


def _object(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or isinstance(value, list):
        raise SchemaValidationError(f"{path} must be an object")
    return dict(value)


def _strict_keys(
    value: Mapping[str, Any],
    allowed: set[str],
    required: set[str],
    path: str,
) -> None:
    unknown = set(value) - allowed
    missing = required - set(value)
    if unknown:
        raise SchemaValidationError(f"{path} has unknown fields: {sorted(unknown)}")
    if missing:
        raise SchemaValidationError(f"{path} is missing fields: {sorted(missing)}")


def _string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SchemaValidationError(f"{path} must be a non-empty string")
    return value


def _boolean(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        raise SchemaValidationError(f"{path} must be a boolean")
    return value


def _integer(value: Any, path: str, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SchemaValidationError(f"{path} must be an integer")
    if minimum is not None and value < minimum:
        raise SchemaValidationError(f"{path} must be >= {minimum}")
    return value


def _sha256(value: Any, path: str) -> str:
    result = _string(value, path)
    if not _SHA256_RE.fullmatch(result):
        raise SchemaValidationError(f"{path} must be a lowercase SHA-256 hex digest")
    return result


def validate_archive_path(value: Any, *, expected_root: str | None = None) -> str:
    """Validate one canonical, relative ZIP member path.

    ZIP names are required to use forward slashes and cannot contain dot
    segments, empty segments, drive letters, UNC roots, or forbidden runtime
    directories. Requiring the input to already be canonical also prevents
    two spellings from representing the same logical member.
    """

    if not isinstance(value, str) or not value:
        raise PathSafetyError("archive path must be a non-empty string")
    if "\x00" in value or "\\" in value:
        raise PathSafetyError(f"unsafe archive path: {value!r}")
    if value.startswith("/") or value.startswith("//") or re.match(r"^[A-Za-z]:", value):
        raise PathSafetyError(f"absolute archive path is not allowed: {value!r}")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise PathSafetyError(f"non-canonical archive path: {value!r}")
    if any(part in _FORBIDDEN_PATH_COMPONENTS for part in parts):
        raise PathSafetyError(f"runtime directory is not allowed in Pack: {value!r}")
    if parts[-1] in _FORBIDDEN_FILENAMES:
        raise PathSafetyError(f"credential-bearing file is not allowed in Pack: {value!r}")
    if expected_root is not None and (value == expected_root or not value.startswith(f"{expected_root}/")):
        raise PathSafetyError(f"archive path must be below {expected_root}/: {value!r}")
    return value


def validate_payload_key(value: Any, root: str, path: str) -> str:
    """Validate a PackData map key and return its canonical archive path."""

    if not isinstance(value, str) or not value:
        raise PathSafetyError(f"{path} key must be a non-empty relative path")
    if value.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", value):
        raise PathSafetyError(f"{path} key must be relative: {value!r}")
    if value.startswith(f"{root}/"):
        raise PathSafetyError(f"{path} key must omit the {root}/ prefix: {value!r}")
    return validate_archive_path(f"{root}/{value}", expected_root=root)


def validate_manifest(value: Any, *, require_integrity: bool = False) -> dict[str, Any]:
    manifest = _object(value, "manifest")
    # Report an unsupported schema before checking version-specific required
    # fields, so a future schema cannot be misdiagnosed as a malformed v1 Pack.
    if "schemaVersion" in manifest and manifest["schemaVersion"] != SCHEMA_VERSION:
        raise SchemaValidationError(
            f"unsupported manifest.schemaVersion: {manifest['schemaVersion']!r}; expected {SCHEMA_VERSION}"
        )
    allowed = {"schemaVersion", "format", "packVersion", "profile", "environment", "requiredSecrets", "integrity"}
    required = {"schemaVersion", "format", "packVersion", "profile", "environment"}
    if require_integrity:
        required.add("integrity")
    _strict_keys(manifest, allowed, required, "manifest")
    if manifest["schemaVersion"] != SCHEMA_VERSION:
        raise SchemaValidationError(
            f"unsupported manifest.schemaVersion: {manifest['schemaVersion']!r}; expected {SCHEMA_VERSION}"
        )
    if manifest["format"] not in LEGACY_PACK_FORMATS:
        raise SchemaValidationError(f"unsupported manifest.format: {manifest['format']!r}")
    _string(manifest["packVersion"], "manifest.packVersion")

    profile = _object(manifest["profile"], "manifest.profile")
    _strict_keys(profile, {"name"}, {"name"}, "manifest.profile")
    profile_name = _string(profile["name"], "manifest.profile.name")
    if any(char in profile_name for char in "/\\") or profile_name in {".", ".."}:
        raise SchemaValidationError("manifest.profile.name must be a single profile name")

    validate_environment(manifest["environment"])
    required_secrets = manifest.get("requiredSecrets", [])
    if not isinstance(required_secrets, Sequence) or isinstance(required_secrets, (str, bytes, bytearray)):
        raise SchemaValidationError("manifest.requiredSecrets must be an array")
    for index, name in enumerate(required_secrets):
        secret_name = _string(name, f"manifest.requiredSecrets[{index}]")
        if not _SECRET_NAME_RE.fullmatch(secret_name):
            raise SchemaValidationError(f"manifest.requiredSecrets[{index}] must be an environment variable name")
    if "integrity" in manifest:
        validate_integrity(manifest["integrity"])
    return manifest


def validate_environment(value: Any) -> dict[str, Any]:
    environment = _object(value, "manifest.environment")
    _strict_keys(environment, {"schemaVersion", "os", "node", "dsh"}, {"schemaVersion", "os", "node", "dsh"}, "manifest.environment")
    if environment["schemaVersion"] != SCHEMA_VERSION:
        raise SchemaValidationError(
            f"unsupported manifest.environment.schemaVersion: {environment['schemaVersion']!r}; expected {SCHEMA_VERSION}"
        )
    os_info = _object(environment["os"], "manifest.environment.os")
    _strict_keys(os_info, {"name", "version", "arch"}, {"name", "version", "arch"}, "manifest.environment.os")
    for key in ("name", "version", "arch"):
        _string(os_info[key], f"manifest.environment.os.{key}")
    for section in ("node", "dsh"):
        info = _object(environment[section], f"manifest.environment.{section}")
        _strict_keys(info, {"version"}, {"version"}, f"manifest.environment.{section}")
        _string(info["version"], f"manifest.environment.{section}.version")
    return environment


def validate_integrity(value: Any) -> dict[str, Any]:
    integrity = _object(value, "manifest.integrity")
    _strict_keys(integrity, {"algorithm", "files"}, {"algorithm", "files"}, "manifest.integrity")
    if integrity["algorithm"] != "sha256":
        raise SchemaValidationError("manifest.integrity.algorithm must be sha256")
    files = _object(integrity["files"], "manifest.integrity.files")
    if not files:
        raise SchemaValidationError("manifest.integrity.files must not be empty")
    for archive_path, digest in files.items():
        validate_archive_path(archive_path)
        _sha256(digest, f"manifest.integrity.files[{archive_path!r}]")
    return integrity


def _validate_package_name(value: Any, path: str) -> str:
    name = _string(value, path)
    if not _PACKAGE_NAME_RE.fullmatch(name):
        raise SchemaValidationError(f"{path} is not a valid package name")
    return name


def validate_plugins_lock(value: Any, *, artifact_paths: set[str] | None = None) -> dict[str, Any]:
    lock = _object(value, "plugins.lock")
    _strict_keys(lock, {"schemaVersion", "plugins"}, {"schemaVersion", "plugins"}, "plugins.lock")
    if lock["schemaVersion"] != SCHEMA_VERSION:
        raise SchemaValidationError(
            f"unsupported plugins.lock.schemaVersion: {lock['schemaVersion']!r}; expected {SCHEMA_VERSION}"
        )
    plugins = lock["plugins"]
    if not isinstance(plugins, list):
        raise SchemaValidationError("plugins.lock.plugins must be an array")
    seen: set[str] = set()
    for index, raw_plugin in enumerate(plugins):
        path = f"plugins.lock.plugins[{index}]"
        plugin = _object(raw_plugin, path)
        _strict_keys(plugin, {"name", "required", "requested", "resolved", "runtime", "bundle", "artifact"},
                     {"name", "required", "requested", "resolved", "runtime", "bundle", "artifact"}, path)
        name = _validate_package_name(plugin["name"], f"{path}.name")
        if name in seen:
            raise SchemaValidationError(f"duplicate plugin name: {name}")
        seen.add(name)
        _boolean(plugin["required"], f"{path}.required")

        requested = _object(plugin["requested"], f"{path}.requested")
        _strict_keys(requested, {"specifier", "sourceType"}, {"specifier", "sourceType"}, f"{path}.requested")
        _string(requested["specifier"], f"{path}.requested.specifier")
        source_type = _string(requested["sourceType"], f"{path}.requested.sourceType")
        if source_type not in _SOURCE_TYPES:
            raise SchemaValidationError(f"{path}.requested.sourceType is unsupported: {source_type!r}")

        resolved = _object(plugin["resolved"], f"{path}.resolved")
        _strict_keys(resolved, {"version", "locator", "integrity"}, {"version", "locator"}, f"{path}.resolved")
        _string(resolved["version"], f"{path}.resolved.version")
        _string(resolved["locator"], f"{path}.resolved.locator")
        if "integrity" in resolved:
            _string(resolved["integrity"], f"{path}.resolved.integrity")

        runtime = _object(plugin["runtime"], f"{path}.runtime")
        _strict_keys(runtime, {"version", "source", "entry"}, {"version", "source", "entry"}, f"{path}.runtime")
        _string(runtime["version"], f"{path}.runtime.version")
        runtime_source = _string(runtime["source"], f"{path}.runtime.source")
        if runtime_source not in _RUNTIME_SOURCES:
            raise SchemaValidationError(f"{path}.runtime.source is unsupported: {runtime_source!r}")
        _string(runtime["entry"], f"{path}.runtime.entry")

        bundle = _object(plugin["bundle"], f"{path}.bundle")
        _strict_keys(bundle, {"enabled", "order", "patch"}, {"enabled", "order", "patch"}, f"{path}.bundle")
        bundle_enabled = _boolean(bundle["enabled"], f"{path}.bundle.enabled")
        if bundle_enabled:
            _integer(bundle["order"], f"{path}.bundle.order", minimum=0)
            _string(bundle["patch"], f"{path}.bundle.patch")
        else:
            if bundle["order"] is not None or bundle["patch"] is not None:
                raise SchemaValidationError(f"{path}.bundle.order and patch must be null when bundle.enabled is false")

        artifact = _object(plugin["artifact"], f"{path}.artifact")
        _strict_keys(artifact, {"mode", "path", "sha256"}, {"mode"}, f"{path}.artifact")
        mode = _string(artifact["mode"], f"{path}.artifact.mode")
        if mode not in _ARTIFACT_MODES:
            raise SchemaValidationError(f"{path}.artifact.mode is unsupported: {mode!r}")
        if mode == "embedded":
            if "path" not in artifact or "sha256" not in artifact:
                raise SchemaValidationError(f"{path}.artifact requires path and sha256 when embedded")
            artifact_path = validate_archive_path(artifact["path"], expected_root="plugins")
            _sha256(artifact["sha256"], f"{path}.artifact.sha256")
            if artifact_paths is not None and artifact_path not in artifact_paths:
                raise SchemaValidationError(f"{path}.artifact.path is missing from plugins/: {artifact_path}")
        elif "path" in artifact or "sha256" in artifact:
            raise SchemaValidationError(f"{path}.artifact cannot contain embedded fields in reference-only mode")
    return lock
