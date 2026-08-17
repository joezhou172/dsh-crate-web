"""Phase 2 Profile-to-Pack export.

This module reads an existing Profile directory. It never installs a Profile,
starts DSH, invokes pnpm, or contacts a registry. Embedded artifacts are made
with ``npm pack`` against an already installed local package directory only.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import posixpath
import re
import shutil
import subprocess
import tarfile
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from .errors import DshPackError, ExportError
from .pack import PackData, create, sha256_bytes
from .validation import validate_payload_key


REFERENCE_ONLY = "reference-only"
EMBEDDED = "embedded"
_VALID_MODES = {REFERENCE_ONLY, EMBEDDED}
_SOURCE_TYPE_PREFIXES = {
    "git": ("git:", "github:", "git+", ".git"),
    "file": ("file:", "./", "../"),
    "link": ("link:",),
    "tarball": ("http://", "https://"),
    "workspace": ("workspace:",),
}
_SECRET_NAME_RE = re.compile(
    r"(?i)(?:api[_-]?key|access[_-]?token|auth[_-]?token|password|secret|private[_-]?key)"
)
_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?im)\b(?:[A-Z][A-Z0-9_]*(?:API[_-]?KEY|TOKEN|PASSWORD|SECRET|PRIVATE[_-]?KEY))\b\s*[:=]\s*['\"]?[^\s,'\"}]+"
)
_SEMVER_RE = re.compile(
    r"^[v=]?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
_SKIP_DIRS = {"node_modules", ".git", "cache", "logs", ".dshpack-work"}
_SKIP_FILES = {
    ".credentials.yaml",
    ".credentials.yml",
    "credentials.json",
    "credentials.yaml",
    "credentials.yml",
    ".env",
    ".env.local",
}


@dataclass(frozen=True)
class PluginExportOptions:
    """User-selected artifact mode and requiredness for one plugin."""

    mode: str = REFERENCE_ONLY
    required: bool = True

    def __post_init__(self) -> None:
        if self.mode not in _VALID_MODES:
            raise ExportError(f"unsupported artifact mode: {self.mode!r}")
        if not isinstance(self.required, bool):
            raise ExportError("PluginExportOptions.required must be a boolean")


@dataclass(frozen=True)
class ExportOptions:
    """Environment and per-plugin choices required for one export."""

    environment: Mapping[str, Any]
    required_secrets: tuple[str, ...] = ()
    plugin_options: Mapping[str, PluginExportOptions] = field(default_factory=dict)
    npm_command: str | None = None
    include_installation_bundles: bool = False


@dataclass(frozen=True)
class ExportResult:
    """The created Pack path and semantic data used to create it."""

    path: Path
    data: PackData



def _imported_required_secrets(profile_dir: Path) -> tuple[str, ...]:
    """Return requiredSecrets recorded for this Profile by a prior Import.

    Import keeps Pack metadata outside the runtime Profile under
    ``DSH_HOME/.dsh-pack/imports/<profile>/manifest.json``.  Re-export of an
    imported Profile must preserve the required Secret names so the Pack keeps
    its original semantics; values are never stored or returned.
    """
    metadata = profile_dir.parent.parent / ".dsh-pack" / "imports" / profile_dir.name / "manifest.json"
    try:
        value = json.loads(metadata.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return ()
    if not isinstance(value, dict):
        return ()
    secrets = value.get("requiredSecrets", [])
    if not isinstance(secrets, list):
        return ()
    return tuple(name for name in secrets if isinstance(name, str) and name.strip())


def _read_json_file(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ExportError(f"cannot read {label}: {path}") from error
    if not isinstance(value, dict):
        raise ExportError(f"{label} must contain a JSON object: {path}")
    return value


def _string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ExportError(f"{path} must be a non-empty string")
    return value


def _source_type(specifier: str) -> str:
    for source_type, prefixes in _SOURCE_TYPE_PREFIXES.items():
        if specifier.startswith(prefixes):
            return source_type
    if specifier.startswith("npm:"):
        return "alias"
    return "registry"


def _repository_specifier(package_manifest: Mapping[str, Any]) -> str | None:
    """Return a portable source locator from npm ``repository`` metadata.

    DSH installation-anchor Bundles are not always listed in the Profile's
    dependency map.  In that case the installed package manifest is the last
    authoritative local source record we have.  Keep the locator in the Pack
    instead of silently falling back to a package name with ``unknown``.
    """

    repository = package_manifest.get("repository")
    if isinstance(repository, str):
        candidate = repository.strip()
    elif isinstance(repository, Mapping):
        candidate = repository.get("url")
        if not isinstance(candidate, str):
            return None
        candidate = candidate.strip()
    else:
        return None
    if not candidate:
        return None
    if candidate.startswith(("git:", "git+", "github:", "ssh://", ".git")):
        return candidate
    if candidate.startswith(("http://", "https://")):
        return f"git+{candidate}"
    return candidate


def _effective_specifier(
    package_name: str,
    specifier: str,
    package_manifest: Mapping[str, Any],
) -> str:
    if specifier != "unknown":
        return specifier
    inferred = _repository_specifier(package_manifest)
    if inferred:
        return inferred
    raise ExportError(
        f"cannot export {package_name}: package source is unavailable; "
        "Profile dependency specifier or package.json.repository is required"
    )


@dataclass(frozen=True)
class _SemVer:
    major: int
    minor: int
    patch: int
    prerelease: tuple[str | int, ...] = ()


def _parse_semver(value: str) -> _SemVer | None:
    match = _SEMVER_RE.fullmatch(value.strip())
    if not match:
        return None
    prerelease = tuple(
        int(identifier) if identifier.isdigit() else identifier
        for identifier in (match.group(4) or "").split(".")
        if identifier
    )
    return _SemVer(int(match.group(1)), int(match.group(2)), int(match.group(3)), prerelease)


def _compare_semver(left: _SemVer, right: _SemVer) -> int:
    left_core = (left.major, left.minor, left.patch)
    right_core = (right.major, right.minor, right.patch)
    if left_core != right_core:
        return (left_core > right_core) - (left_core < right_core)
    if not left.prerelease and not right.prerelease:
        return 0
    if not left.prerelease:
        return 1
    if not right.prerelease:
        return -1
    for left_id, right_id in zip(left.prerelease, right.prerelease):
        if left_id == right_id:
            continue
        if isinstance(left_id, int) and isinstance(right_id, str):
            return -1
        if isinstance(left_id, str) and isinstance(right_id, int):
            return 1
        return (left_id > right_id) - (left_id < right_id)
    return (len(left.prerelease) > len(right.prerelease)) - (
        len(left.prerelease) < len(right.prerelease)
    )


def _parse_range_version(value: str) -> tuple[_SemVer, int | None] | None:
    value = value.strip()
    full = _parse_semver(value)
    if full is not None:
        return full, None
    if value.startswith("v"):
        value = value[1:]
    parts = value.split(".")
    if not 1 <= len(parts) <= 3:
        return None
    numbers: list[int] = []
    wildcard_index: int | None = None
    for index, part in enumerate(parts):
        if part.lower() in {"x", "*"}:
            wildcard_index = index
            break
        if not part.isdigit():
            return None
        numbers.append(int(part))
    if wildcard_index is None:
        wildcard_index = len(parts) if len(parts) < 3 else None
    if wildcard_index is not None and any(part.lower() not in {"x", "*"} for part in parts[wildcard_index:]):
        return None
    while len(numbers) < 3:
        numbers.append(0)
    return _SemVer(*numbers), wildcard_index


def _range_clause_matches(candidate: _SemVer, clause: str) -> bool | None:
    clause = clause.strip()
    if not clause or clause in {"*", "x", "X"}:
        return True
    if clause.startswith("^") or clause.startswith("~"):
        operator = clause[0]
        parsed = _parse_range_version(clause[1:])
        if parsed is None:
            return None
        lower, wildcard_index = parsed
        if operator == "^":
            if lower.major > 0:
                upper = _SemVer(lower.major + 1, 0, 0)
            elif lower.minor > 0:
                upper = _SemVer(0, lower.minor + 1, 0)
            else:
                upper = _SemVer(0, 0, lower.patch + 1)
        elif wildcard_index == 0:
            upper = _SemVer(lower.major + 1, 0, 0)
        else:
            upper = _SemVer(lower.major, lower.minor + 1, 0)
        return _compare_semver(candidate, lower) >= 0 and _compare_semver(candidate, upper) < 0

    match = re.fullmatch(r"(<=|>=|<|>|=)?(.+)", clause)
    if not match:
        return None
    operator = match.group(1) or ""
    parsed = _parse_range_version(match.group(2))
    if parsed is None:
        return None
    bound, wildcard_index = parsed
    comparison = _compare_semver(candidate, bound)
    if wildcard_index is None:
        return {
            "": comparison == 0,
            "=": comparison == 0,
            ">": comparison > 0,
            ">=": comparison >= 0,
            "<": comparison < 0,
            "<=": comparison <= 0,
        }[operator]
    if operator in {"", "="}:
        if wildcard_index == 0:
            return True
        if wildcard_index == 1:
            return candidate.major == bound.major
        return candidate.major == bound.major and candidate.minor == bound.minor
    upper = (
        _SemVer(bound.major + 1, 0, 0)
        if wildcard_index == 0
        else _SemVer(bound.major, bound.minor + 1, 0)
    )
    if operator == ">=":
        return comparison >= 0
    if operator == ">":
        return _compare_semver(candidate, upper) >= 0
    if operator == "<":
        return comparison < 0
    return _compare_semver(candidate, upper) < 0


def _registry_spec_satisfies(specifier: str, version: str) -> bool | None:
    """Check common npm semver ranges without resolving a registry or lockfile."""

    if not re.search(r"(?:^|[\s|])(?:[v=]?\d|[~^<>=*xX])", specifier):
        return None
    candidate = _parse_semver(version)
    if candidate is None:
        return False
    outcomes: list[bool | None] = []
    for alternative in specifier.split("||"):
        clauses = alternative.strip().split()
        clause_results = [_range_clause_matches(candidate, clause) for clause in clauses]
        if all(result is True for result in clause_results):
            outcomes.append(True)
        elif any(result is None for result in clause_results):
            outcomes.append(None)
        else:
            outcomes.append(False)
    if True in outcomes:
        return True
    if None in outcomes:
        return None
    return False


def _package_path(profile_dir: Path, package_name: str) -> Path:
    if package_name.startswith(".") or "\\" in package_name or "/../" in f"/{package_name}/":
        raise ExportError(f"invalid package name for node_modules lookup: {package_name!r}")
    return profile_dir / "node_modules" / Path(*package_name.split("/"))


def _installed_package(profile_dir: Path, package_name: str) -> tuple[Path, dict[str, Any]]:
    # DSH resolves Bundle layers from the installation anchor first and then
    # from the Profile.  Its healer exposes the installation dependency
    # closure at ``$DSH_HOME/profiles/node_modules``.  For a Profile under
    # ``.../profiles/<name>``, that fallback is the parent node_modules
    # directory.  Keep the Profile-local lookup first so user-installed
    # dependencies retain normal Node nearest-wins semantics.
    package_paths = [_package_path(profile_dir, package_name)]
    fallback_path = profile_dir.parent / "node_modules" / Path(*package_name.split("/"))
    if fallback_path not in package_paths:
        package_paths.append(fallback_path)
    for package_dir in package_paths:
        package_json = package_dir / "package.json"
        if package_json.is_file():
            return package_dir, _read_json_file(package_json, f"installed package {package_name}")
    searched = ", ".join(str(path / "package.json") for path in package_paths)
    raise ExportError(f"installed package manifest is missing; searched: {searched}")


def _direct_package_dirs(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    result: list[Path] = []
    for entry in sorted(root.iterdir(), key=lambda path: path.name):
        if entry.name.startswith(".") or not entry.is_dir():
            continue
        if entry.name.startswith("@"):
            result.extend(
                child
                for child in sorted(entry.iterdir(), key=lambda path: path.name)
                if not child.name.startswith(".") and child.is_dir()
            )
        else:
            result.append(entry)
    return result


def _installed_bundle_inventory(profile_dir: Path) -> list[tuple[str, Path, str, dict[str, Any]]]:
    """Find direct Bundle packages in the Profile and DSH installation anchor.

    This intentionally does not recurse through arbitrary dependency trees:
    only packages directly exposed by either DSH resolution root are eligible
    for an explicit "include installed Bundles" export.
    """

    roots = (
        (profile_dir / "node_modules", "profile"),
        (profile_dir.parent / "node_modules", "installation-anchor"),
    )
    found: list[tuple[str, Path, str, dict[str, Any]]] = []
    names: set[str] = set()
    for root, location in roots:
        for package_dir in _direct_package_dirs(root):
            try:
                manifest = _read_json_file(package_dir / "package.json", f"installed package {package_dir.name}")
            except ExportError:
                continue
            package_name = manifest.get("name")
            package_version = manifest.get("version")
            dsh = manifest.get("dsh")
            bundle = dsh.get("bundle") if isinstance(dsh, dict) else None
            patch = bundle.get("patch") if isinstance(bundle, dict) else None
            if (
                not isinstance(package_name, str)
                or not package_name.strip()
                or not isinstance(package_version, str)
                or not package_version.strip()
                or not isinstance(patch, str)
                or not patch.strip()
                or package_name in names
            ):
                continue
            names.add(package_name)
            found.append((package_name, package_dir, location, manifest))
    return found


def _profile_dependencies(profile_manifest: Mapping[str, Any]) -> dict[str, str]:
    dependencies = profile_manifest.get("dependencies", {})
    if not isinstance(dependencies, dict):
        raise ExportError("Profile package.json dependencies must be an object")
    result: dict[str, str] = {}
    for name, specifier in dependencies.items():
        result[_string(name, "Profile dependency name")] = _string(
            specifier, f"Profile dependency {name!r}"
        )
    return result


def _profile_bundles(profile_manifest: Mapping[str, Any]) -> list[str]:
    dsh = profile_manifest.get("dsh", {})
    if dsh is None:
        dsh = {}
    if not isinstance(dsh, dict):
        raise ExportError("Profile package.json dsh must be an object")
    profile = dsh.get("profile", {})
    if profile is None:
        profile = {}
    if not isinstance(profile, dict):
        raise ExportError("Profile package.json dsh.profile must be an object")
    bundles = profile.get("bundles", [])
    if not isinstance(bundles, list) or any(not isinstance(name, str) or not name for name in bundles):
        raise ExportError("Profile package.json dsh.profile.bundles must be an array of names")
    if len(set(bundles)) != len(bundles):
        raise ExportError("Profile package.json dsh.profile.bundles contains duplicates")
    return list(bundles)


def _profile_files(profile_dir: Path, destination: Path) -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    resolved_destination = destination.resolve()
    for path in profile_dir.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        relative_path = path.relative_to(profile_dir)
        if any(part in _SKIP_DIRS for part in relative_path.parts):
            continue
        if relative_path.name in _SKIP_FILES:
            continue
        if path.resolve() == resolved_destination:
            continue
        try:
            content = path.read_bytes()
        except OSError as error:
            raise ExportError(f"cannot read Profile file: {path}") from error
        if _SECRET_ASSIGNMENT_RE.search(content.decode("utf-8", errors="ignore")):
            raise ExportError(f"secret-like value detected in Profile file: {relative_path.as_posix()}")
        key = relative_path.as_posix()
        validate_payload_key(key, "profile", "Profile files")
        result[key] = content
    if "package.json" not in result:
        raise ExportError("Profile package.json was not collected")
    return result


def _with_bundle_composition(profile_files: dict[str, bytes], bundles: Sequence[str]) -> None:
    try:
        manifest = json.loads(profile_files["package.json"].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ExportError("Profile package.json cannot be rewritten for installed Bundles") from error
    if not isinstance(manifest, dict):
        raise ExportError("Profile package.json must contain an object")
    dsh = manifest.get("dsh")
    if dsh is None:
        dsh = {}
        manifest["dsh"] = dsh
    if not isinstance(dsh, dict):
        raise ExportError("Profile package.json dsh must be an object")
    profile = dsh.get("profile")
    if profile is None:
        profile = {}
        dsh["profile"] = profile
    if not isinstance(profile, dict):
        raise ExportError("Profile package.json dsh.profile must be an object")
    profile["bundles"] = list(bundles)
    profile_files["package.json"] = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _npm_command(configured: str | None) -> str:
    if configured:
        return configured
    if os.name == "nt":
        return shutil.which("npm.cmd") or shutil.which("npm") or "npm.cmd"
    return shutil.which("npm") or "npm"


def _bundle_patch_path(package_dir: Path, package_name: str, patch: str) -> str:
    normalized = posixpath.normpath(patch.replace("\\", "/"))
    if normalized in {"", ".", ".."} or normalized.startswith("../") or normalized.startswith("/"):
        raise ExportError(f"Bundle {package_name} has an unsafe dsh.bundle.patch path: {patch!r}")
    package_root = package_dir.resolve()
    patch_path = (package_dir / Path(*normalized.split("/"))).resolve()
    try:
        patch_path.relative_to(package_root)
    except ValueError as error:
        raise ExportError(f"Bundle {package_name} has an unsafe dsh.bundle.patch path: {patch!r}") from error
    if not patch_path.is_file():
        raise ExportError(f"Bundle {package_name} patch file is missing: {patch}")
    return normalized




def _bundle_inserted_loader_ids(patch_text: str) -> list[str]:
    """Collect loader row ids registered via top-level ``insert`` blocks.

    A DSH bundle patch is a YAML list.  A top-level ``- insert:`` item
    registers new loader rows (each indented ``- id:`` line), while a plain
    top-level ``- id:`` item updates an existing row and is not a loader
    registration.  This scanner only understands that shape; nested lists
    inside ``config`` are ignored.
    """
    ids: list[str] = []
    in_insert = False
    insert_indent: int | None = None
    for raw in patch_text.splitlines():
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()
        if indent == 0 and stripped.startswith("- "):
            key = stripped[2:].strip()
            in_insert = key == "insert:"
            insert_indent = None
            continue
        if not in_insert:
            continue
        if not stripped.startswith("- "):
            continue
        if insert_indent is None:
            insert_indent = indent
        if indent != insert_indent:
            continue
        row = stripped[2:].strip()
        if row.startswith("id:"):
            value = row[3:].strip().strip("\"'")
            if value:
                ids.append(value)
    return ids


def _assert_no_duplicate_loader_rows(profile_dir: Path, bundles: Sequence[str]) -> None:
    """Reject bundle compositions that duplicate a loader row.

    DSH's plugin tree loader fails at boot with ``duplicate loader entry id``
    when two bundles in one profile insert the same loader row (for example
    ``dsh-web-app`` and ``dsh-headless`` both insert ``code-runtime``).  Detect
    the collision while the Bundle patch files are still available instead of
    shipping a Pack that cannot start.
    """
    registered_by: dict[str, list[str]] = {}
    for package_name in bundles:
        try:
            package_dir, package_manifest = _installed_package(profile_dir, package_name)
        except ExportError:
            continue
        dsh = package_manifest.get("dsh") or {}
        bundle_meta = dsh.get("bundle") or {}
        patch = bundle_meta.get("patch")
        if not isinstance(patch, str) or not patch.strip():
            continue
        try:
            patch_relative = _bundle_patch_path(package_dir, package_name, patch)
        except ExportError:
            continue
        patch_path = package_dir.joinpath(*patch_relative.split("/"))
        try:
            patch_text = patch_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for row_id in _bundle_inserted_loader_ids(patch_text):
            registered_by.setdefault(row_id, []).append(package_name)
    collisions = sorted(row_id for row_id, names in registered_by.items() if len(names) > 1)
    if not collisions:
        return
    detail = "; ".join(
        f"loader row {row_id!r} registered by {', '.join(registered_by[row_id])}"
        for row_id in collisions
    )
    raise ExportError(
        "Bundle composition duplicates a loader row and cannot boot: " + detail
    )


def _validate_tarball(content: bytes, package_name: str, required_file: str | None = None) -> None:
    from io import BytesIO

    required_member = f"package/{required_file}" if required_file else None
    found_required = False
    try:
        with tarfile.open(fileobj=BytesIO(content), mode="r:gz") as archive:
            for member in archive.getmembers():
                member_name = member.name.replace("\\", "/")
                if any(part in {"node_modules", ".git", "cache", "logs"} for part in member_name.split("/")):
                    raise ExportError(f"npm pack artifact contains forbidden runtime path: {package_name}")
                if member_name.startswith("/") or "/../" in f"/{member_name}/" or member_name.startswith("../"):
                    raise ExportError(f"npm pack artifact contains unsafe path: {package_name}")
                if required_member == member_name and member.isfile():
                    found_required = True
    except (tarfile.TarError, OSError) as error:
        raise ExportError(f"npm pack did not produce a readable tarball: {package_name}") from error
    if required_member and not found_required:
        raise ExportError(f"npm pack artifact is missing Bundle patch file: {package_name}/{required_file}")


def _npm_pack(
    package_dir: Path,
    package_name: str,
    npm_command: str,
    *,
    required_file: str | None = None,
) -> bytes:
    with tempfile.TemporaryDirectory(prefix="dsh-pack-npm-") as directory:
        cache_directory = Path(directory) / "npm-cache"
        cache_directory.mkdir()
        command = [
            npm_command,
            "pack",
            str(package_dir),
            "--ignore-scripts",
            "--pack-destination",
            directory,
            "--cache",
            str(cache_directory),
        ]
        completed = subprocess.run(
            command,
            cwd=package_dir,
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        if completed.returncode != 0:
            raise ExportError(
                f"npm pack failed for {package_name} with exit code {completed.returncode}: "
                f"{completed.stderr.strip() or completed.stdout.strip()}"
            )
        tarballs = sorted(Path(directory).glob("*.tgz"))
        if len(tarballs) != 1:
            raise ExportError(f"npm pack produced {len(tarballs)} tarballs for {package_name}")
        content = tarballs[0].read_bytes()
    _validate_tarball(content, package_name, required_file)
    return content


def _artifact_name(package_name: str, version: str) -> str:
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "-", package_name).strip(".-") or "plugin"
    safe_version = re.sub(r"[^A-Za-z0-9._+-]+", "-", version).strip(".-") or "unknown"
    return f"{safe_name}-{safe_version}.tgz"


def _plugin_lock_entry(
    profile_dir: Path,
    package_name: str,
    specifier: str,
    bundle_order: int | None,
    options: PluginExportOptions,
    npm_command: str,
    runtime_source: str | None = None,
) -> tuple[dict[str, Any], dict[str, bytes]]:
    package_dir, package_manifest = _installed_package(profile_dir, package_name)
    installed_name = _string(package_manifest.get("name", package_name), f"{package_name}.package.json.name")
    if installed_name != package_name:
        raise ExportError(
            f"installed package name mismatch: requested {package_name!r}, found {installed_name!r}"
        )
    version = _string(package_manifest.get("version"), f"{package_name}.package.json.version")
    specifier = _effective_specifier(package_name, specifier, package_manifest)
    source_type = _source_type(specifier)
    if source_type == "registry":
        semver_match = _registry_spec_satisfies(specifier, version)
        if semver_match is False:
            raise ExportError(
                f"installed package {package_name}@{version} does not satisfy requested specifier {specifier!r}"
            )
    resolved_runtime_source = runtime_source or ("profile-dependency" if specifier else "installation-anchor")
    dsh = package_manifest.get("dsh", {})
    if dsh is None:
        dsh = {}
    if not isinstance(dsh, dict):
        raise ExportError(f"{package_name}.package.json.dsh must be an object")
    bundle_meta = dsh.get("bundle", {})
    if bundle_meta is None:
        bundle_meta = {}
    if not isinstance(bundle_meta, dict):
        raise ExportError(f"{package_name}.package.json.dsh.bundle must be an object")
    patch = bundle_meta.get("patch")
    patch_relative_path: str | None = None
    if bundle_order is not None and (not isinstance(patch, str) or not patch.strip()):
        raise ExportError(f"Bundle {package_name} is missing dsh.bundle.patch")
    if bundle_order is not None:
        patch_relative_path = _bundle_patch_path(package_dir, package_name, patch)

    entry: dict[str, Any] = {
        "name": package_name,
        "required": options.required,
        "requested": {"specifier": specifier, "sourceType": source_type},
        "resolved": {
            "version": version,
            "locator": f"registry:{package_name}@{version}" if source_type == "registry" else specifier,
        },
        "runtime": {
            "version": version,
            "source": resolved_runtime_source,
            "entry": dsh.get("runtime", {}).get("entry", package_name)
            if isinstance(dsh.get("runtime", {}), dict)
            else package_name,
        },
        "bundle": {
            "enabled": bundle_order is not None,
            "order": bundle_order,
            "patch": patch if bundle_order is not None else None,
        },
        "artifact": {"mode": options.mode},
    }

    artifacts: dict[str, bytes] = {}
    if options.mode == EMBEDDED:
        content = _npm_pack(
            package_dir,
            package_name,
            npm_command,
            required_file=patch_relative_path,
        )
        artifact_file = _artifact_name(package_name, version)
        artifact_path = f"plugins/{artifact_file}"
        entry["artifact"] = {
            "mode": EMBEDDED,
            "path": artifact_path,
            "sha256": sha256_bytes(content),
        }
        artifacts[artifact_file] = content
    return entry, artifacts


def export_profile(
    profile: str | os.PathLike[str],
    destination: str | os.PathLike[str],
    *,
    options: ExportOptions,
) -> ExportResult:
    """Export one existing Profile directory into a `.dshcrate`.

    The Profile is read only. The only generated external files are the
    destination Pack and temporary local npm tarballs used for embedded mode.
    """

    profile_dir = Path(profile).resolve()
    destination_path = Path(destination).resolve()
    if not profile_dir.is_dir():
        raise ExportError(f"Profile directory does not exist: {profile_dir}")
    if profile_dir == destination_path or profile_dir in destination_path.parents:
        raise ExportError("destination Pack must be outside the source Profile directory")

    profile_manifest = _read_json_file(profile_dir / "package.json", "Profile package.json")
    dependencies = _profile_dependencies(profile_manifest)
    bundles = _profile_bundles(profile_manifest)
    plugin_options = dict(options.plugin_options)
    extra_runtime_sources: dict[str, str] = {}
    if options.include_installation_bundles:
        installed_inventory = _installed_bundle_inventory(profile_dir)
        installed_names = {package_name for package_name, *_ in installed_inventory}
        for package_name, _package_dir, location, _package_manifest in installed_inventory:
            if package_name in plugin_options and package_name not in bundles:
                bundles.append(package_name)
                extra_runtime_sources[package_name] = (
                    "profile-dependency" if location == "profile" else "installation-anchor"
                )
    else:
        installed_names = set()
    plugin_names = list(bundles)
    plugin_names.extend(name for name in dependencies if name not in plugin_names)
    if not plugin_names:
        raise ExportError("Profile has no dependencies or dsh.profile.bundles")
    _assert_no_duplicate_loader_rows(profile_dir, bundles)

    unknown_options = set(plugin_options) - set(plugin_names) - installed_names
    if unknown_options:
        raise ExportError(f"plugin options refer to packages absent from Profile: {sorted(unknown_options)}")

    npm_command = _npm_command(options.npm_command)
    profile_files = _profile_files(profile_dir, destination_path)
    if options.include_installation_bundles:
        _with_bundle_composition(profile_files, bundles)
    plugins: list[dict[str, Any]] = []
    artifacts: dict[str, bytes] = {}
    for package_name in plugin_names:
        specifier = dependencies.get(package_name, "unknown")
        selected = plugin_options.get(package_name, PluginExportOptions())
        entry, package_artifacts = _plugin_lock_entry(
            profile_dir,
            package_name,
            specifier,
            bundles.index(package_name) if package_name in bundles else None,
            selected,
            npm_command,
            extra_runtime_sources.get(package_name),
        )
        plugins.append(entry)
        for artifact_name, content in package_artifacts.items():
            if artifact_name in artifacts:
                raise ExportError(f"duplicate generated artifact filename: {artifact_name}")
            artifacts[artifact_name] = content

    required_secrets = tuple(options.required_secrets) or _imported_required_secrets(profile_dir)
    manifest = {
        "schemaVersion": 1,
        "format": "dshcrate",
        "packVersion": "0.1.0",
        "profile": {"name": profile_dir.name},
        "environment": copy.deepcopy(dict(options.environment)),
        "requiredSecrets": list(required_secrets),
    }
    data = PackData(
        manifest=manifest,
        profile_files=profile_files,
        plugins_lock={"schemaVersion": 1, "plugins": plugins},
        plugin_artifacts=artifacts,
    )
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    created = create(data, destination_path)
    return ExportResult(path=created, data=data)


def _load_environment(args: argparse.Namespace) -> dict[str, Any]:
    if args.environment_json:
        value = _read_json_file(Path(args.environment_json), "environment JSON")
        return value
    return {
        "schemaVersion": 1,
        "os": {"name": args.os_name, "version": args.os_version, "arch": args.os_arch},
        "node": {"version": args.node_version},
        "dsh": {"version": args.dsh_version},
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export an existing DSH Profile into a .dshcrate")
    parser.add_argument("--profile", required=True, help="Profile directory")
    parser.add_argument("--output", required=True, help="Output .dshcrate path")
    parser.add_argument("--environment-json", help="JSON object containing Pack environment")
    parser.add_argument("--dsh-version", default="unknown")
    parser.add_argument("--node-version", default="unknown")
    parser.add_argument("--os-name", default="unknown")
    parser.add_argument("--os-version", default="unknown")
    parser.add_argument("--os-arch", default="unknown")
    parser.add_argument("--embed", action="append", default=[], metavar="PLUGIN")
    parser.add_argument("--reference-only", action="append", default=[], metavar="PLUGIN")
    parser.add_argument("--include-installed-bundles", action="store_true")
    parser.add_argument("--required-secret", action="append", default=[], metavar="NAME")
    args = parser.parse_args(argv)

    overlap = set(args.embed) & set(args.reference_only)
    if overlap:
        parser.error(f"plugin selected for both --embed and --reference-only: {sorted(overlap)}")
    plugin_options = {
        name: PluginExportOptions(mode=EMBEDDED)
        for name in args.embed
    }
    plugin_options.update({name: PluginExportOptions(mode=REFERENCE_ONLY) for name in args.reference_only})
    try:
        result = export_profile(
            args.profile,
            args.output,
            options=ExportOptions(
                environment=_load_environment(args),
                required_secrets=tuple(args.required_secret),
                plugin_options=plugin_options,
                include_installation_bundles=args.include_installed_bundles,
            ),
        )
    except DshPackError as error:
        print(f"EXPORT FAIL: {error}")
        return 2
    print(f"EXPORT PASS: {result.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
