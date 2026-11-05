"""Phase 4 Pack import into a named, isolated DSH Profile.

The importer deliberately has no overwrite or merge path. It prepares one new
Profile directory under ``DSH_HOME/profiles`` and keeps Pack metadata outside
the runtime Profile under ``DSH_HOME/.dsh-pack/imports``. Reference-only
plugins are supplied by an explicit local source first. If enabled and no
local source is available, npm resolves recorded registry/GitHub/tarball
metadata inside the temporary Profile; no shell is used and lifecycle scripts
are disabled.
"""

from __future__ import annotations

import json
import base64
import os
import posixpath
import re
import shutil
import subprocess
import tarfile
import tempfile
import uuid
from dataclasses import dataclass, field, replace
from io import BytesIO
from pathlib import Path
from typing import Any, Callable, Mapping

from .errors import DshPackError, PackImportError
from .pack import PackData, read, sha256_bytes
from .network import npm_install_specifier
from .identity import expected_install_version, unknown_source
from .preflight import PreflightContext, PreflightResult, inspect_pack
from .validation import validate_archive_path, bundle_patch_paths
from .bundle import check_patch_declaration, read_bundle_patches


ReferenceInstaller = Callable[[Path, Mapping[str, Any]], None]
_REFERENCE_SOURCE_SKIP_DIRS = {"node_modules", ".git", "cache", "logs"}


@dataclass(frozen=True)
class ImportOptions:
    """Facts and explicit installation adapters used by one import."""

    current_environment: Mapping[str, Any] = field(default_factory=dict)
    available_secrets: set[str] | None = None
    reference_plugin_sources: Mapping[str, str | os.PathLike[str]] = field(default_factory=dict)
    reference_plugin_versions: Mapping[str, str | None] = field(default_factory=dict)
    reference_installer: ReferenceInstaller | None = None
    allow_network_reference_install: bool = True
    npm_command: str | None = None
    pnpm_command: tuple[str, ...] | None = None
    host_bundles: Mapping[str, Any] | None = None
    patch_adapter_command: tuple[str, ...] | None = None
    network_install_timeout: int = 180
    target_profile_name: str | None = None
    overwrite_existing_profile: bool = False
    overwrite_confirmation: str | None = None


@dataclass(frozen=True)
class ImportPlan:
    """A read-only plan produced before any target filesystem write."""

    pack_path: Path
    dsh_home: Path
    requested_profile_name: str
    profile_name: str
    profile_path: Path
    metadata_path: Path
    overwrite: bool
    target_exists: bool
    embedded_plugins: tuple[dict[str, Any], ...]
    reference_plugins: tuple[dict[str, Any], ...]
    preflight: PreflightResult
    portable_data: tuple[str, ...] = ()
    host_provided_dependencies: tuple[dict[str, Any], ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "packPath": str(self.pack_path),
            "dshHome": str(self.dsh_home),
            "requestedProfileName": self.requested_profile_name,
            "profileName": self.profile_name,
            "profilePath": str(self.profile_path),
            "metadataPath": str(self.metadata_path),
            "overwrite": self.overwrite,
            "targetExists": self.target_exists,
            "embeddedPlugins": list(self.embedded_plugins),
            "referencePlugins": list(self.reference_plugins),
            "preflight": self.preflight.as_dict(),
            "portableData": list(self.portable_data),
            "hostProvidedDependencies": list(self.host_provided_dependencies),
            "decision": "READY_TO_IMPORT" if self.preflight.status == "READY" else "NOT_READY",
        }


@dataclass(frozen=True)
class ImportResult:
    """A successfully prepared new Profile."""

    status: str
    profile_path: Path
    metadata_path: Path
    plan: ImportPlan
    installed_plugins: tuple[dict[str, Any], ...]
    network_installs: tuple[dict[str, Any], ...] = ()
    warnings: tuple[dict[str, Any], ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "profilePath": str(self.profile_path),
            "metadataPath": str(self.metadata_path),
            "installedPlugins": list(self.installed_plugins),
            "networkInstalls": list(self.network_installs),
            "warnings": list(self.warnings),
            "plan": self.plan.as_dict(),
        }


@dataclass(frozen=True)
class DeleteResult:
    """Result of an explicitly confirmed Profile deletion.

    ``metadata_status`` reports what happened to the paired Import metadata
    directory: ``removed``, ``no-metadata`` (nothing was stored for this
    Profile), or ``failed`` (the Profile is deleted but metadata cleanup did
    not complete).
    """

    status: str
    profile_name: str
    profile_path: Path
    metadata_path: Path | None = None
    metadata_status: str = "no-metadata"

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "profileName": self.profile_name,
            "profilePath": str(self.profile_path),
            "metadataPath": str(self.metadata_path) if self.metadata_path is not None else None,
            "metadataStatus": self.metadata_status,
        }


def _profile_name(manifest: Mapping[str, Any]) -> str:
    profile = manifest.get("profile")
    if not isinstance(profile, Mapping) or not isinstance(profile.get("name"), str):
        raise PackImportError(
            "Pack manifest has no valid profile name",
            stage="planning",
            code="PROFILE_NAME_MISSING",
        )
    return profile["name"]


def _validate_profile_name(name: str, *, label: str = "Profile name") -> str:
    if (
        not isinstance(name, str)
        or not name.strip()
        or name in {".", ".."}
        or "/" in name
        or "\\" in name
        or "\x00" in name
    ):
        raise PackImportError(
            f"{label} must be a single safe directory name",
            stage="planning",
            code="PROFILE_NAME_INVALID",
            details={"item": name},
        )
    return name


def _select_profile_name(
    dsh_home: Path,
    requested_name: str,
    *,
    target_name: str | None = None,
    overwrite: bool = False,
) -> str:
    """Choose a new Profile directory without ever reusing an occupied name.

    Import has no overwrite or merge mode.  When a Pack's original Profile name
    is already present in the destination DSH_HOME, planning fails with
    ``PROFILE_EXISTS`` instead of allocating a suffix: the original Profile is
    left untouched and no files are written.  The metadata directory is checked
    as well so a stale prepared record cannot be mistaken for an unused target.
    ``overwrite=True`` is a separate explicit path that requires the target to
    already exist and refuses symlink or non-directory targets.
    """

    requested_name = _validate_profile_name(requested_name, label="Pack Profile name")
    selected_name = _validate_profile_name(target_name or requested_name, label="Target Profile name")
    profiles_root = dsh_home / "profiles"
    metadata_root = dsh_home / ".dsh-pack" / "imports"

    def occupied(name: str) -> bool:
        return (profiles_root / name).exists() or (metadata_root / name).exists()

    if overwrite:
        profile_path = profiles_root / selected_name
        if profile_path.is_symlink() or (profile_path.exists() and not profile_path.is_dir()):
            raise PackImportError(
                f"target Profile is not a safe directory: {profile_path}",
                stage="planning",
                code="PROFILE_TARGET_INVALID",
                details={"profilePath": str(profile_path)},
            )
        if not profile_path.exists():
            raise PackImportError(
                f"target Profile does not exist for overwrite: {profile_path}",
                stage="planning",
                code="PROFILE_TARGET_MISSING",
                details={"profilePath": str(profile_path)},
            )
        return selected_name
    if occupied(selected_name):
        raise PackImportError(
            f"target Profile already exists: {profiles_root / selected_name}",
            stage="planning",
            code="PROFILE_EXISTS",
            details={"profilePath": str(profiles_root / selected_name), "requestedProfileName": selected_name},
        )
    return selected_name


def _package_install_path(profile_path: Path, package_name: str) -> Path:
    if not package_name or "\\" in package_name or package_name.startswith("/"):
        raise PackImportError(
            f"unsafe package name: {package_name!r}",
            stage="planning",
            code="PACKAGE_NAME_INVALID",
        )
    parts = package_name.split("/")
    if any(not part or part in {".", ".."} for part in parts):
        raise PackImportError(
            f"unsafe package name: {package_name!r}",
            stage="planning",
            code="PACKAGE_NAME_INVALID",
        )
    return profile_path / "node_modules" / Path(*parts)


def _package_manifest(package_path: Path, *, stage: str) -> dict[str, Any]:
    manifest_path = package_path / "package.json"
    try:
        value = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PackImportError(
            f"cannot read installed package manifest: {manifest_path}",
            stage=stage,
            code="PACKAGE_MANIFEST_INVALID",
        ) from error
    if not isinstance(value, dict) or not isinstance(value.get("name"), str) or not isinstance(value.get("version"), str):
        raise PackImportError(
            f"installed package manifest lacks name/version: {manifest_path}",
            stage=stage,
            code="PACKAGE_MANIFEST_INVALID",
        )
    return value


def _reference_inventory(options: ImportOptions) -> dict[str, str | None]:
    inventory = dict(options.reference_plugin_versions)
    for name, source in options.reference_plugin_sources.items():
        manifest = _package_manifest(Path(source), stage="planning")
        inventory[name] = manifest["version"]
    return inventory


def _reference_plugin_requirements(data: PackData) -> dict[str, str | None]:
    requirements: dict[str, str | None] = {}
    for plugin in data.plugins_lock.get("plugins", []):
        if not isinstance(plugin, Mapping):
            continue
        artifact = plugin.get("artifact")
        name = plugin.get("name")
        if not isinstance(artifact, Mapping) or artifact.get("mode") != "reference-only" or not isinstance(name, str):
            continue
        if unknown_source(plugin):
            continue  # Unknown source requires an explicit, checked local path.
        requirements[name] = expected_install_version(plugin)
    return requirements


def _reference_search_roots(dsh_home: Path) -> tuple[Path, ...]:
    """Return local DSH package roots used for automatic reference discovery.

    Only shared installation roots are eligible: the per-home anchor
    (``profiles/node_modules``) and the home-level ``node_modules``.  Per-Profile
    package directories are excluded because npm hoists a Profile's transitive
    dependencies to that Profile's own ``node_modules`` top level.  Copying a bare
    package out of there cannot resolve those dependencies in the new Profile (a
    sibling Profile is not an ancestor in Node's resolution walk), which yields an
    installed Profile that fails to boot.  Explicit ``reference_plugin_sources``
    overrides remain the way to reuse a package from a specific location.
    """

    profiles_root = dsh_home / "profiles"
    roots: list[Path] = [profiles_root / "node_modules", dsh_home / "node_modules"]
    return tuple(dict.fromkeys(roots))


def _auto_reference_sources(
    data: PackData,
    dsh_home: Path,
    options: ImportOptions,
) -> ImportOptions:
    """Resolve reference-only packages already installed in this DSH_HOME.

    A Pack never stores machine-specific absolute paths.  During Import, use
    DSH's shared installation anchor first, then existing Profile package
    directories, and keep an explicitly supplied source as the override.
    This is local discovery only; it does not contact a registry or run a
    package manager.
    """

    sources = dict(options.reference_plugin_sources)
    requirements = _reference_plugin_requirements(data)
    roots = _reference_search_roots(dsh_home)
    for name, expected_version in requirements.items():
        if name in sources:
            continue
        candidates: list[tuple[Path, str | None]] = []
        for root in roots:
            package_path = root.joinpath(*name.split("/"))
            manifest_path = package_path / "package.json"
            if not manifest_path.is_file():
                continue
            try:
                manifest = _package_manifest(package_path, stage="planning")
            except PackImportError:
                candidates.append((package_path, None))
                continue
            if manifest.get("name") != name:
                continue
            candidates.append((package_path, manifest.get("version")))

        if not candidates:
            continue
        exact = next(
            (path for path, version in candidates if expected_version is not None and version == expected_version),
            None,
        )
        sources[name] = exact or candidates[0][0]

    if sources == options.reference_plugin_sources:
        return options
    return replace(options, reference_plugin_sources=sources)


def _network_reference_plugins(data: PackData, options: ImportOptions) -> tuple[dict[str, Any], ...]:
    """Return reference-only entries that still need a network install."""

    result: list[dict[str, Any]] = []
    for raw_plugin in data.plugins_lock.get("plugins", []):
        if not isinstance(raw_plugin, Mapping):
            continue
        artifact = raw_plugin.get("artifact")
        name = raw_plugin.get("name")
        if not isinstance(artifact, Mapping) or artifact.get("mode") != "reference-only" or not isinstance(name, str):
            continue
        if name in options.reference_plugin_sources or name in options.reference_plugin_versions:
            continue
        if npm_install_specifier(raw_plugin) is None:
            continue
        result.append(dict(raw_plugin))
    return tuple(result)


def _npm_command(configured: str | None) -> str:
    if configured:
        return configured
    if os.name == "nt":
        return shutil.which("npm.cmd") or shutil.which("npm") or "npm.cmd"
    return shutil.which("npm") or "npm"


def _network_error_output(value: str, limit: int = 4000) -> str:
    """Keep command diagnostics bounded and avoid dumping a whole npm log."""

    value = value.strip()
    return value[-limit:] if len(value) > limit else value


def _install_network_reference(profile_path: Path, plugin: Mapping[str, Any], options: ImportOptions) -> dict[str, Any]:
    """Install one recorded network source into the temporary Profile.

    The command is argv-based and lifecycle scripts are disabled. The package
    manager therefore owns registry/GitHub/tarball resolution while Pack keeps
    ownership of target isolation and exact package identity verification.
    """

    name = str(plugin.get("name"))
    specifier = npm_install_specifier(plugin)
    if specifier is None:
        raise PackImportError(
            f"no supported network source is recorded for {name}",
            stage="network-install",
            code="NETWORK_SOURCE_UNSUPPORTED",
            details={"plugin": name},
        )
    command = [
        _npm_command(options.npm_command),
        "install",
        "--ignore-scripts",
        # DSH host packages are peer dependencies supplied by the runtime
        # installation anchor. Do not make npm fetch a second host tree from
        # the public registry while installing a reference-only plugin.
        "--legacy-peer-deps",
        "--no-save",
        "--no-package-lock",
        "--no-audit",
        "--no-fund",
        "--prefix",
        str(profile_path),
        "--",
        specifier,
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=profile_path,
            capture_output=True,
            text=True,
            check=False,
            timeout=max(1, int(options.network_install_timeout)),
        )
    except FileNotFoundError as error:
        raise PackImportError(
            f"npm command is unavailable while installing {name}",
            stage="network-install",
            code="NETWORK_INSTALL_FAILED",
            details={"plugin": name, "command": command[0], "source": specifier, "error": str(error)},
        ) from error
    except subprocess.TimeoutExpired as error:
        raise PackImportError(
            f"network install timed out for {name}",
            stage="network-install",
            code="NETWORK_INSTALL_TIMEOUT",
            details={"plugin": name, "source": specifier, "timeoutSeconds": options.network_install_timeout},
        ) from error
    except OSError as error:
        raise PackImportError(
            f"cannot start npm while installing {name}",
            stage="network-install",
            code="NETWORK_INSTALL_FAILED",
            details={"plugin": name, "command": command[0], "source": specifier, "error": str(error)},
        ) from error
    if completed.returncode != 0:
        raise PackImportError(
            f"npm install failed for {name} with exit code {completed.returncode}",
            stage="network-install",
            code="NETWORK_INSTALL_FAILED",
            details={
                "plugin": name,
                "source": specifier,
                "command": command,
                "exitCode": completed.returncode,
                "stdout": _network_error_output(completed.stdout),
                "stderr": _network_error_output(completed.stderr),
            },
        )
    target = _package_install_path(profile_path, name)
    if not (target / "package.json").is_file():
        raise PackImportError(
            f"npm install completed but package is missing: {name}",
            stage="network-install",
            code="NETWORK_PACKAGE_MISSING",
            details={"plugin": name, "source": specifier, "target": str(target)},
        )
    return {
        "name": name,
        "source": specifier,
        "resolver": "npm",
        "scripts": "ignored",
        "stdout": _network_error_output(completed.stdout),
    }


def _context(options: ImportOptions) -> PreflightContext:
    verified_local_plugins = {}
    for name, source in options.reference_plugin_sources.items():
        manifest = _package_manifest(Path(source), stage="planning")
        if manifest["name"] == name:
            verified_local_plugins[name] = manifest["version"]
    return PreflightContext(
        current_environment=dict(options.current_environment),
        available_secrets=set() if options.available_secrets is None else set(options.available_secrets),
        available_plugins=_reference_inventory(options),
        allow_network_reference_install=options.allow_network_reference_install,
        verified_local_plugins=verified_local_plugins,
    )


def _plugin_rows(lock: Mapping[str, Any], mode: str) -> tuple[dict[str, Any], ...]:
    result: list[dict[str, Any]] = []
    for plugin in lock.get("plugins", []):
        if not isinstance(plugin, Mapping):
            continue
        artifact = plugin.get("artifact")
        if not isinstance(artifact, Mapping) or artifact.get("mode") != mode:
            continue
        result.append(
            {
                "name": plugin.get("name"),
                "version": expected_install_version(plugin),
                "required": plugin.get("required") is True,
                "artifact": dict(artifact),
            }
        )
    return tuple(result)


def create_import_plan(
    source: str | os.PathLike[str],
    dsh_home: str | os.PathLike[str],
    *,
    options: ImportOptions | None = None,
) -> ImportPlan:
    """Run Preflight and create a no-write Import Plan."""

    options = options or ImportOptions()
    source_path = Path(source).resolve()
    home_path = Path(dsh_home).resolve()
    try:
        pack_data = read(source_path)
    except DshPackError:
        pack_data = None
    if pack_data is not None:
        options = _auto_reference_sources(pack_data, home_path, options)
    try:
        preflight = inspect_pack(source_path, context=_context(options))
    except (DshPackError, OSError) as error:
        if isinstance(error, PackImportError):
            raise
        raise PackImportError(
            str(error),
            stage="preflight",
            code="PREFLIGHT_ERROR",
        ) from error
    if preflight.blockers:
        raise PackImportError(
            "Preflight blocked Import",
            stage="preflight",
            code="PREFLIGHT_BLOCKED",
            details={"findings": [finding.as_dict() for finding in preflight.blockers]},
        )
    try:
        data = pack_data if pack_data is not None else read(source_path)
    except DshPackError as error:
        raise PackImportError(str(error), stage="preflight", code="PACK_READ_ERROR") from error

    from .portability import check_targets
    check_targets(home_path, data.user_data, overwrite=options.overwrite_existing_profile)
    requested_profile_name = _profile_name(data.manifest)
    profile_name = _select_profile_name(
        home_path,
        requested_profile_name,
        target_name=options.target_profile_name,
        overwrite=options.overwrite_existing_profile,
    )
    profile_path = home_path / "profiles" / profile_name
    metadata_path = home_path / ".dsh-pack" / "imports" / profile_name
    target_exists = profile_path.exists() or metadata_path.exists()
    # _select_profile_name checks both locations.  Keep these guards for a
    # clear diagnostic if the filesystem changes between selection and return.
    if target_exists and not options.overwrite_existing_profile:
        raise PackImportError(
            f"no safe target Profile name is available for {requested_profile_name!r}",
            stage="planning",
            code="PROFILE_NAME_UNAVAILABLE",
            details={"requestedProfileName": requested_profile_name, "profilePath": str(profile_path), "metadataPath": str(metadata_path)},
        )
    if "package.json" not in data.profile_files:
        raise PackImportError(
            "Pack profile/ is missing package.json",
            stage="planning",
            code="PROFILE_CONFIG_MISSING",
        )

    _, host_dependencies = _host_dependency_overrides(data, options)
    return ImportPlan(
        pack_path=source_path,
        dsh_home=home_path,
        requested_profile_name=requested_profile_name,
        profile_name=profile_name,
        profile_path=profile_path,
            metadata_path=metadata_path,
            overwrite=options.overwrite_existing_profile,
            target_exists=target_exists,
            embedded_plugins=_plugin_rows(data.plugins_lock, "embedded"),
        reference_plugins=_plugin_rows(data.plugins_lock, "reference-only"),
        preflight=preflight,
        portable_data=tuple(data.user_data),
            host_provided_dependencies=tuple(host_dependencies),
    )


def _write_file(root: Path, relative: str, content: bytes) -> None:
    archive_path = validate_archive_path(f"profile/{relative}", expected_root="profile")
    relative_path = archive_path[len("profile/"):]
    destination = root.joinpath(*relative_path.split("/"))
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() or destination.is_symlink():
        raise PackImportError(
            f"Profile target file already exists: {destination}",
            stage="configuration",
            code="PROFILE_FILE_EXISTS",
        )
    destination.write_bytes(content)


def _extract_embedded_artifact(profile_path: Path, plugin: Mapping[str, Any], content: bytes) -> None:
    name = str(plugin["name"])
    target = _package_install_path(profile_path, name)
    if target.exists():
        raise PackImportError(
            f"embedded plugin target already exists: {target}",
            stage="embedded-install",
            code="PLUGIN_TARGET_EXISTS",
        )
    target.mkdir(parents=True, exist_ok=False)
    seen: set[str] = set()
    try:
        with tarfile.open(fileobj=BytesIO(content), mode="r:gz") as archive:
            for member in archive.getmembers():
                raw_name = member.name.replace("\\", "/")
                if raw_name.endswith("/"):
                    raw_name = raw_name[:-1]
                if raw_name == "package":
                    continue
                canonical = validate_archive_path(raw_name)
                if not canonical.startswith("package/"):
                    raise PackImportError(
                        f"artifact member is outside package/: {member.name!r}",
                        stage="embedded-install",
                        code="ARTIFACT_PATH_INVALID",
                    )
                relative = canonical[len("package/"):]
                if not relative or relative in seen:
                    raise PackImportError(
                        f"duplicate artifact member: {member.name!r}",
                        stage="embedded-install",
                        code="ARTIFACT_MEMBER_DUPLICATE",
                    )
                seen.add(relative)
                destination = target.joinpath(*relative.split("/"))
                if member.issym():
                    raise PackImportError(
                        f"unsupported artifact symlink member: {member.name!r}",
                        stage="embedded-install",
                        code="ARTIFACT_MEMBER_TYPE_INVALID",
                    )
                if member.isdir():
                    destination.mkdir(parents=True, exist_ok=True)
                    continue
                if member.islnk():
                    # npm tarballs can contain hardlink members. Resolve the
                    # target inside the same archive and materialize a regular
                    # file so the installed package is a plain directory tree.
                    content_bytes = _read_artifact_hardlink(archive, member)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(content_bytes)
                    continue
                if not member.isfile():
                    raise PackImportError(
                        f"unsupported artifact member type: {member.name!r}",
                        stage="embedded-install",
                        code="ARTIFACT_MEMBER_TYPE_INVALID",
                    )
                extracted = archive.extractfile(member)
                if extracted is None:
                    raise PackImportError(
                        f"cannot read artifact member: {member.name!r}",
                        stage="embedded-install",
                        code="ARTIFACT_MEMBER_READ_ERROR",
                    )
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(extracted.read())
    except PackImportError:
        raise
    except DshPackError as error:
        raise PackImportError(
            f"embedded artifact is unsafe for {name}",
            stage="embedded-install",
            code="ARTIFACT_PATH_INVALID",
            details={"error": str(error)},
        ) from error
    except (OSError, tarfile.TarError) as error:
        raise PackImportError(
            f"cannot unpack embedded artifact for {name}",
            stage="embedded-install",
            code="ARTIFACT_UNPACK_FAILED",
            details={
                "item": name,
                "expected": {"artifact": "valid gzip tar archive", "package": name},
                "observed": {"error": str(error)},
                "evidence": {"package": name, "stage": "embedded-install"},
                "error": str(error),
            },
        ) from error



def _read_artifact_hardlink(archive: tarfile.TarFile, member: tarfile.TarInfo) -> bytes:
    """Read the file content a tar hardlink member points to.

    npm preserves hardlinks in packed tarballs. The link target is resolved
    within the same archive only; symlinks, directory targets, missing
    members, and cycles are rejected.
    """

    resolved: set[str] = set()
    current = member.linkname.replace("\\", "/")
    for _ in range(16):
        canonical = validate_archive_path(current)
        if not canonical.startswith("package/"):
            raise PackImportError(
                f"artifact hardlink target is outside package/: {member.linkname!r}",
                stage="embedded-install",
                code="ARTIFACT_PATH_INVALID",
            )
        if canonical in resolved:
            raise PackImportError(
                f"artifact hardlink target cycle: {member.linkname!r}",
                stage="embedded-install",
                code="ARTIFACT_MEMBER_TYPE_INVALID",
            )
        resolved.add(canonical)
        try:
            target_member = archive.getmember(canonical)
        except KeyError:
            raise PackImportError(
                f"artifact hardlink target is missing: {canonical!r}",
                stage="embedded-install",
                code="ARTIFACT_MEMBER_READ_ERROR",
            ) from None
        if target_member.issym() or target_member.isdir():
            raise PackImportError(
                f"artifact hardlink target is not a regular file: {canonical!r}",
                stage="embedded-install",
                code="ARTIFACT_MEMBER_TYPE_INVALID",
            )
        if target_member.islnk():
            current = target_member.linkname.replace("\\", "/")
            continue
        extracted = archive.extractfile(target_member)
        if extracted is None:
            raise PackImportError(
                f"cannot read artifact hardlink target: {canonical!r}",
                stage="embedded-install",
                code="ARTIFACT_MEMBER_READ_ERROR",
            )
        return extracted.read()
    raise PackImportError(
        f"artifact hardlink chain is too long: {member.name!r}",
        stage="embedded-install",
        code="ARTIFACT_MEMBER_TYPE_INVALID",
    )


def _copy_reference_source(profile_path: Path, plugin: Mapping[str, Any], source: Path) -> None:
    name = str(plugin["name"])
    target = _package_install_path(profile_path, name)
    if not source.is_dir():
        raise PackImportError(
            f"reference plugin source is not a directory: {source}",
            stage="reference-install",
            code="PLUGIN_SOURCE_MISSING",
        )
    source = source.resolve()
    if target.exists():
        raise PackImportError(
            f"reference plugin target already exists: {target}",
            stage="reference-install",
            code="PLUGIN_TARGET_EXISTS",
        )
    target.mkdir(parents=True, exist_ok=False)

    def is_directory_link(path: Path) -> bool:
        junction_check = getattr(path, "is_junction", None)
        return path.is_symlink() or (callable(junction_check) and junction_check())

    for current_root, directory_names, file_names in os.walk(source, topdown=True, followlinks=False):
        current_path = Path(current_root)
        retained_directories: list[str] = []
        for directory_name in directory_names:
            directory_path = current_path / directory_name
            relative_parts = directory_path.relative_to(source).parts
            if any(part in _REFERENCE_SOURCE_SKIP_DIRS for part in relative_parts):
                continue
            if is_directory_link(directory_path):
                raise PackImportError(
                    f"reference plugin source contains symlink or junction: {directory_path}",
                    stage="reference-install",
                    code="PLUGIN_SOURCE_UNSAFE",
                )
            retained_directories.append(directory_name)
        directory_names[:] = retained_directories

        for file_name in file_names:
            path = current_path / file_name
            relative = path.relative_to(source).as_posix()
            validate_archive_path(f"package/{relative}", expected_root="package")
            if path.is_symlink():
                raise PackImportError(
                    f"reference plugin source contains symlink: {path}",
                    stage="reference-install",
                    code="PLUGIN_SOURCE_UNSAFE",
                )
            destination = target / Path(*path.relative_to(source).parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)


def _verify_identity(profile_path: Path, plugin: Mapping[str, Any]) -> dict[str, Any]:
    name = str(plugin["name"])
    expected_version = expected_install_version(plugin)
    installed = _package_manifest(_package_install_path(profile_path, name), stage="version-confirmation")
    if installed["name"] != name or installed["version"] != expected_version:
        raise PackImportError(
            f"installed {name}@{installed.get('version')} does not match Pack {name}@{expected_version}",
            stage="version-confirmation",
            code="PLUGIN_VERSION_MISMATCH",
            details={
                "plugin": name,
                "expected": {"name": name, "version": expected_version},
                "observed": {"name": installed.get("name"), "version": installed.get("version")},
            },
        )
    bundle = plugin.get("bundle")
    if isinstance(bundle, Mapping) and bundle.get("enabled") is True:
        patch = bundle.get("patch")
        package_root = _package_install_path(profile_path, name)
        try:
            paths = bundle_patch_paths(patch)
            for relative in paths:
                package_root.joinpath(*relative.split("/")).resolve().relative_to(package_root.resolve())
        except (DshPackError, ValueError) as error:
            raise PackImportError(
                f"installed Bundle has an unsafe patch path: {name}",
                stage="version-confirmation", code="BUNDLE_PATCH_INVALID",
                details={"plugin": name, "patch": patch},
            ) from error
        try:
            check_patch_declaration(installed, patch)
        except DshPackError as error:
            raise PackImportError(
                f"installed Bundle patch declaration differs from Crate: {name}",
                stage="version-confirmation", code="BUNDLE_PATCH_MISMATCH",
                details={"plugin": name, "expected": patch},
            ) from error
        for relative in paths:
            if not package_root.joinpath(*relative.split("/")).is_file():
                raise PackImportError(
                    f"installed Bundle patch is missing: {name}/{relative}",
                    stage="version-confirmation", code="BUNDLE_PATCH_MISSING",
                    details={"plugin": name, "patch": relative},
                )
        try:
            read_bundle_patches(package_root, patch)
        except DshPackError as error:
            raise PackImportError(
                f"installed Bundle patch content is unsafe: {name}",
                stage="version-confirmation", code="BUNDLE_PATCH_INVALID",
                details={"plugin": name, "patch": patch},
            ) from error
    return {"name": name, "version": installed["version"], "mode": plugin["artifact"]["mode"]}


def _remove_staged_package(profile_path: Path, name: str, *, stage: str) -> None:
    """Replace only a package inside the temporary Profile, without following links."""
    target = _package_install_path(profile_path, name)
    # A package manager can create scoped directories or links. Reject linked
    # ancestors before removing anything; never resolve through them for deletion.
    for parent in target.parents:
        if parent == profile_path:
            break
        if parent.is_symlink() or (getattr(parent, "is_junction", lambda: False)()):
            raise PackImportError(
                f"staged package ancestor is a link: {name}",
                stage=stage, code="PLUGIN_TARGET_UNSAFE",
                details={"plugin": name},
            )
    if target.is_symlink():
        target.unlink()
    elif getattr(target, "is_junction", lambda: False)():
        target.rmdir()
    elif target.is_dir():
        shutil.rmtree(target)
    elif target.exists():
        target.unlink()


def _write_network_manifest(profile_path: Path, dependencies: Mapping[str, str]) -> None:
    # The exported Profile can contain local paths, embedded package registry
    # requests, or optional sources that failed. npm must only see successful
    # network references; the original Profile manifest is restored afterwards.
    (profile_path / "package.json").write_text(
        json.dumps({"name": "dsh-crate-import-staging", "private": True,
                    "dependencies": dict(dependencies)}), encoding="utf-8",
    )


def _network_dependency_spec(plugin: Mapping[str, Any]) -> str:
    specifier = npm_install_specifier(plugin)
    assert specifier is not None  # the network plan already checked support
    prefix = f"{plugin['name']}@"
    return specifier[len(prefix):] if specifier.startswith(prefix) else specifier


def _host_dependency_overrides(data: PackData, options: ImportOptions) -> tuple[dict[str, str], list[dict[str, Any]]]:
    """Use dependencies from a verified installation anchor, never by name alone.

    Desktop supplies public manifest/file evidence read from its actual ASAR.
    The Bundle artifact itself remains installed and managed by pnpm. Only its
    already-present host dependencies are omitted from the Profile's pnpm tree,
    where a second copy of host/native internals could shadow the official host.
    """
    if options.host_bundles is None:
        return {}, []
    overrides: dict[str, str] = {}
    provided: list[dict[str, Any]] = []
    for plugin in data.plugins_lock['plugins']:
        if not plugin.get('bundle', {}).get('enabled') or plugin.get('runtime', {}).get('source') != 'installation-anchor':
            continue
        artifact = plugin.get('artifact', {})
        if artifact.get('mode') != 'embedded':
            continue
        name = str(plugin['name'])
        host = options.host_bundles.get(name)
        def mismatch(message):
            return PackImportError(message, stage='planning', code='HOST_BUNDLE_MISMATCH', details={
                'plugin': name, 'suggestedNextStep': '请使用与 Crate 实际制品一致的官方桌面安装锚点，或重新导出当前环境；不要用另一份宿主依赖覆盖原生运行时。'})
        if not isinstance(host, Mapping) or not isinstance(host.get('manifest'), Mapping) or not isinstance(host.get('files'), Mapping):
            raise mismatch('the target host has no verified evidence for an installation-anchor Bundle')
        content = data.plugin_artifacts[artifact['path'][len('plugins/'):]]
        try:
            archive_context = tarfile.open(fileobj=BytesIO(content), mode='r:gz')
        except (tarfile.TarError, OSError) as error:
            raise mismatch('the host Bundle artifact cannot be read') from error
        with archive_context as archive:
            try:
                manifest_member = archive.getmember('package/package.json')
                if not manifest_member.isfile():
                    raise mismatch('the host Bundle manifest must be a regular file')
                manifest = json.loads(archive.extractfile(manifest_member).read())
            except (tarfile.TarError, KeyError, ValueError, OSError) as error:
                raise mismatch('the host Bundle artifact has no readable package manifest') from error
            if manifest != host['manifest'] or manifest.get('version') != expected_install_version(plugin):
                raise mismatch('the host Bundle manifest differs from the embedded artifact')
            for member in archive:
                if member.isdir():
                    continue
                relative = member.name.removeprefix('package/')
                if relative == 'package.json':
                    continue  # compared semantically above, including dependencies
                if member.isfile():
                    payload = archive.extractfile(member).read()
                elif member.islnk():
                    payload = _read_artifact_hardlink(archive, member)
                else:
                    raise mismatch('the host Bundle artifact contains unsupported members')
                if host['files'].get(relative) != sha256_bytes(payload):
                    raise mismatch('the host Bundle files differ from the embedded artifact')
        installed_dependencies = host.get('dependencies', {})
        if not isinstance(installed_dependencies, Mapping):
            raise mismatch('the host dependency evidence is invalid')
        for field in ('dependencies', 'optionalDependencies'):
            for dependency, requested in manifest.get(field, {}).items():
                version = installed_dependencies.get(dependency)
                if not isinstance(version, str) or not version:
                    if field == 'optionalDependencies':
                        continue
                    raise mismatch('a declared Bundle dependency is missing from the target host')
                overrides[name + '>' + dependency] = '-'
                provided.append({'bundle': name, 'name': dependency, 'requested': requested,
                                 'runtimeVersion': version, 'source': 'verified-installation-anchor'})
    return overrides, provided


def _adapt_profile_patch(profile: Path, options: ImportOptions) -> dict[str, Any] | None:
    if not options.patch_adapter_command:
        return None
    path = profile / 'cordis.patch.yml'
    original = path.read_bytes() if path.is_file() else None
    command = [*options.patch_adapter_command, str(profile)]
    completed = None
    def safe_output(value: Any) -> str:
        text = value.decode('utf-8', errors='replace') if isinstance(value, bytes) else str(value or '')
        for name, secret in os.environ.items():
            if secret and re.search(r'KEY|TOKEN|PASSWORD|SECRET|COOKIE|AUTH|PRIVATE|CREDENTIAL', name, re.I):
                text = text.replace(secret, '[REDACTED]')
        text = re.sub(r'(?i)(Bearer\s+)[^\s"\'<>]+', r'\1[REDACTED]', text)
        return re.sub(r'(?i)([?&](?:token|access_token|auth|api_key)=)[^\s&#"\'<>]+', r'\1[REDACTED]', text)
    try:
        completed = subprocess.run(command, cwd=profile,
            env=dict(os.environ, ELECTRON_RUN_AS_NODE='1'), capture_output=True,
            text=True, timeout=max(1, options.network_install_timeout), check=False)
        result = json.loads(completed.stdout)
        if completed.returncode or not isinstance(result, dict) or result.get('error'):
            raise ValueError('the official patch equivalence adapter failed')
        if type(result.get('changed')) is not bool:
            raise ValueError('patch adapter changed flag is invalid')
        if result.get('changed') is not True:
            if not isinstance(result.get('reason'), str) or not result['reason']:
                raise ValueError('patch adapter unchanged evidence is invalid')
            return {'changed': False, 'reason': result.get('reason', 'unchanged')}
        content = base64.b64decode(result['contentBase64'], validate=True)
        if original is None or sha256_bytes(original) != result['originalSha256'] or sha256_bytes(content) != result['runtimeSha256']:
            raise ValueError('patch adapter content identity mismatch')
        if path.read_bytes() != original:
            raise ValueError('patch changed while the equivalence adapter was running')
        changes = result.get('removedNames')
        tree_hash = result.get('loaderTreeSha256')
        if (not isinstance(changes, list) or not changes or any(not isinstance(row, dict) or set(row) != {'id', 'name'}
                or not all(isinstance(value, str) and value for value in row.values()) for row in changes)
                or not isinstance(tree_hash, str) or not re.fullmatch('[a-f0-9]{64}', tree_hash)):
            raise ValueError('patch adapter equivalence evidence is missing')
        backup = profile / '.dsh-crate/original-profile-config/cordis.patch.yml'
        backup.write_bytes(original)
        path.write_bytes(content)
        return {'changed': True, 'originalSha256': sha256_bytes(original),
                'runtimeSha256': sha256_bytes(content), 'loaderTreeSha256': tree_hash,
                'removedNames': changes, 'adapter': 'official-desktop-composition-equivalence-v1'}
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as error:
        raise PackImportError('cannot preserve official Loader composition while adapting the target patch',
            stage='configuration', code='PROFILE_PATCH_ADAPTATION_FAILED',
            details={'command': command, 'reason': safe_output(str(error)),
                     'exitCode': completed.returncode if completed is not None else None,
                     'stdout': safe_output(completed.stdout if completed is not None else getattr(error, 'stdout', '')),
                     'stderr': safe_output(completed.stderr if completed is not None else getattr(error, 'stderr', '')),
                     'suggestedNextStep': '保留源 Profile 和原始 Crate，检查官方解析器及完整诊断；不要删除必需插件或绕过配置等价校验。'}) from error


def _pnpm_rebuild(profile: Path, data: PackData, plugins: list[Mapping[str, Any]], options: ImportOptions) -> dict[str, Any]:
    """Reconstruct manager-owned state from verified artifacts, never copy it.

    Source SPEC remains in the Pack and original-package.json. The restored
    Profile deliberately requests stable local artifacts so later official
    manager operations do not depend on paths on the exporting machine.
    """
    command = options.pnpm_command
    assert command
    overrides, host_dependencies = _host_dependency_overrides(data, options)
    artifacts = profile / '.dsh-crate' / 'artifacts'
    artifacts.mkdir(parents=True, exist_ok=False)
    original = data.profile_files['package.json']
    (artifacts.parent / 'original-package.json').write_bytes(original)
    manifest = json.loads(original)
    dependencies: dict[str, str] = {}
    for plugin in plugins:
        name = str(plugin['name'])
        artifact = plugin['artifact']
        if artifact['mode'] == 'embedded':
            content = data.plugin_artifacts[artifact['path'][len('plugins/'):]]
        else:
            # The existing installer resolved and verified this reference.
            # Turn its portable package files into a local rebuild artifact.
            source = _package_install_path(profile, name)
            buffer = BytesIO()
            with tarfile.open(fileobj=buffer, mode='w:gz') as archive:
                for item in sorted(source.rglob('*')):
                    relative = item.relative_to(source)
                    if any(part in _REFERENCE_SOURCE_SKIP_DIRS for part in relative.parts):
                        continue
                    if item.is_symlink() or getattr(item, 'is_junction', lambda: False)():
                        raise PackImportError('reference artifact contains a link', stage='configuration', code='PLUGIN_TARGET_UNSAFE', details={'plugin': name})
                    if item.is_file():
                        archive.add(item, arcname='package/' + relative.as_posix(), recursive=False)
            content = buffer.getvalue()
        filename = sha256_bytes(content) + '.tgz'
        (artifacts / filename).write_bytes(content)
        dependencies[name] = 'file:./.dsh-crate/artifacts/' + filename
        _remove_staged_package(profile, name, stage='configuration')
    manifest['dependencies'] = dependencies
    # Imported optional packages are represented once in the rebuilt tree.
    manifest.pop('optionalDependencies', None)
    for field in ('pnpm', 'scripts', 'devDependencies', 'packageManager'):
        manifest.pop(field, None)
    (profile / 'package.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    # Source workspace/auth/hook configuration must not control the rebuild or
    # later official manager operations. Keep the originals as inert evidence.
    originals = artifacts.parent / 'original-profile-config'
    originals.mkdir()
    for name in ('pnpm-workspace.yaml', '.npmrc', '.pnpmfile.cjs', '.pnpmfile.mjs'):
        path = profile / name
        if path.exists():
            path.rename(originals / name)
    (profile / 'pnpm-workspace.yaml').write_text(
        'packages:\n  - .\nnodeLinker: hoisted\nautoInstallPeers: false\nignorePnpmfile: true\nignoreScripts: true\nrecursiveInstall: false\npackageImportMethod: copy\n'
        + 'overrides: ' + json.dumps(overrides,ensure_ascii=False) + '\n', encoding='utf-8')
    # The source lock describes a different machine and different requests.
    (profile / 'pnpm-lock.yaml').unlink(missing_ok=True)
    args = [*command, 'install', '--ignore-scripts', '--prod', '--no-frozen-lockfile',
            '--node-linker=hoisted', '--config.auto-install-peers=false',
            '--config.manage-package-manager-versions=false', '--config.ignore-pnpmfile=true',
            '--config.recursive-install=false', '--config.lockfile-dir=' + str(profile),
            '--config.modules-dir=' + str(profile / 'node_modules'), '--config.virtual-store-dir=' + str(profile / 'node_modules/.pnpm'),
            # Hard-linking a cached package into another Profile changes the
            # existing file's ctime. DSH uses ctime in client module identities,
            # so that can remount the source UI during its own Import request.
            '--config.package-import-method=copy',
            '--config.enable-global-virtual-store=false', '--config.shared-workspace-lockfile=false']
    if not options.allow_network_reference_install:
        args.append('--offline')
    environment = dict(os.environ, ELECTRON_RUN_AS_NODE='1')
    try:
        completed = subprocess.run(args, cwd=profile, env=environment, capture_output=True, text=True,
                                   timeout=max(1, options.network_install_timeout), check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise PackImportError('cannot rebuild the target with pnpm', stage='configuration', code='PACKAGE_MANAGER_FAILED', details={'error': str(error), 'command': args}) from error
    if completed.returncode:
        raise PackImportError('pnpm could not rebuild the target installation', stage='configuration', code='PACKAGE_MANAGER_FAILED', details={
            'command': args, 'exitCode': completed.returncode,
            'stdout': _network_error_output(completed.stdout), 'stderr': _network_error_output(completed.stderr)})
    if not (profile / 'node_modules/.modules.yaml').is_file() or not (profile / 'pnpm-lock.yaml').is_file():
        raise PackImportError('pnpm did not create the required installation records', stage='configuration', code='PACKAGE_MANAGER_STATE_MISSING')
    # pnpm 11 writes this record as JSON, even with its legacy .yaml suffix.
    # Its reader supports a virtualStoreDir relative to node_modules on all
    # platforms, while its Windows writer emits an absolute staging path.
    # Only normalize the generated hoisted record we just installed; never
    # copy machine installation state out of a Pack or alter user profiles.
    modules_path = profile / 'node_modules/.modules.yaml'
    try:
        modules = json.loads(modules_path.read_text(encoding='utf-8'))
        virtual_store = Path(modules['virtualStoreDir'])
        if not virtual_store.is_absolute():
            virtual_store = profile / 'node_modules' / virtual_store
        if modules.get('nodeLinker') != 'hoisted' or virtual_store.resolve() != (profile / 'node_modules/.pnpm').resolve():
            raise ValueError(f"unexpected generated virtual store: {modules.get('nodeLinker')} / {modules.get('virtualStoreDir')}")
        modules['virtualStoreDir'] = '.pnpm'
        modules_path.write_text(json.dumps(modules, indent=2) + '\n', encoding='utf-8')
    except (ValueError, KeyError, TypeError) as error:
        raise PackImportError('pnpm installation records cannot be safely relocated', stage='configuration', code='PACKAGE_MANAGER_STATE_UNSUPPORTED', details={'error': str(error)}) from error
    adaptation = _adapt_profile_patch(profile, options)
    return {'resolver': 'pnpm', 'scripts': 'ignored', 'packageImportMethod': 'copy', 'requests': dependencies,
            **({'profilePatchAdaptation': adaptation} if adaptation is not None else {}),
            'hostProvidedDependencies': host_dependencies,
            'workspaceSha256': sha256_bytes((profile / 'pnpm-workspace.yaml').read_bytes()),
            'originalManifest': '.dsh-crate/original-package.json',
            'originalManifestSha256': sha256_bytes(original),
            'stdout': _network_error_output(completed.stdout)}


def _metadata_payload(plan: ImportPlan, data: PackData, installed: tuple[dict[str, Any], ...], pack_digest: str, installation: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "status": "prepared",
        "pack": {"sha256": pack_digest, "path": str(plan.pack_path)},
        "profile": {"name": plan.profile_name, "path": str(plan.profile_path)},
        "overwrite": plan.overwrite,
        "plugins": list(installed),
        "requiredSecrets": list(data.manifest.get("requiredSecrets", [])),
        **({'installation': {key: value for key, value in installation.items() if key != 'stdout'}} if installation else {}),
    }


def _cleanup(path: Path | None) -> None:
    if path is None or not path.exists():
        return
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


def _cleanup_empty(path: Path | None) -> None:
    """Remove a newly-created directory only when it is empty."""

    if path is None or not path.is_dir():
        return
    try:
        next(path.iterdir())
    except StopIteration:
        path.rmdir()


def _commit_prepared_profile(source: Path, target: Path) -> None:
    """Allow a short Windows sharing delay without replacing an existing Profile."""
    import time
    for attempt in range(5):
        if target.exists():
            raise PackImportError("target Profile appeared during Import", stage="commit", code="PROFILE_EXISTS")
        try:
            source.rename(target)
            return
        except PermissionError as error:
            if getattr(error, "winerror", None) not in {5, 32} or attempt == 4:
                raise
            time.sleep(0.1 * (2 ** attempt))


def import_pack(
    source: str | os.PathLike[str],
    dsh_home: str | os.PathLike[str],
    *,
    options: ImportOptions | None = None,
) -> ImportResult:
    """Import one Pack as a prepared Profile with an explicit safe mode.

    The default mode creates a new Profile and refuses duplicate names. An
    overwrite is accepted only when the caller supplies the exact confirmation
    token produced after a user-facing confirmation dialog.
    """

    options = options or ImportOptions()
    if options.overwrite_existing_profile and options.overwrite_confirmation != "OVERWRITE":
        raise PackImportError(
            "overwriting an existing Profile requires explicit confirmation",
            stage="planning",
            code="OVERWRITE_CONFIRMATION_REQUIRED",
            details={
                "expected": "OVERWRITE",
                "observed": "confirmation missing or invalid",
                "impact": "No Profile was changed.",
                "suggestedNextStep": "Confirm the destructive overwrite in the user interface and retry.",
            },
        )


    if options.overwrite_confirmation is not None and not options.overwrite_existing_profile:
        raise PackImportError(
            "overwrite confirmation cannot be used without overwrite mode",
            stage="planning",
            code="OVERWRITE_MODE_REQUIRED",
            details={"impact": "No Profile was changed."},
        )
    source_path = Path(source).resolve()
    home_path = Path(dsh_home).resolve()
    try:
        pack_data = read(source_path)
    except DshPackError:
        pack_data = None
    if pack_data is not None:
        options = _auto_reference_sources(pack_data, home_path, options)
    plan = create_import_plan(source_path, home_path, options=options)
    try:
        data = read(plan.pack_path)
    except DshPackError as error:
        raise PackImportError(str(error), stage="preflight", code="PACK_READ_ERROR") from error

    from .portability import check_targets, restore_files
    check_targets(plan.dsh_home, data.user_data, overwrite=plan.overwrite)
    data_created: list[Path] = []
    data_directories: list[Path] = []
    profiles_root = plan.dsh_home / "profiles"
    temp_profile: Path | None = None
    final_created = False
    metadata_created = False
    original_profile_backup: Path | None = None
    original_metadata_backup: Path | None = None
    backup_token = uuid.uuid4().hex
    network_plugins = {str(plugin.get("name")): plugin for plugin in _network_reference_plugins(data, options)}
    network_installs: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    metadata_parent = plan.metadata_path.parent
    metadata_root = metadata_parent.parent
    metadata_parent_existed = metadata_parent.exists()
    metadata_root_existed = metadata_root.exists()
    try:
        profiles_root.mkdir(parents=True, exist_ok=True)
        temp_profile = Path(tempfile.mkdtemp(prefix=f".{plan.profile_name}.dsh-pack-", dir=profiles_root))
        for relative, content in data.profile_files.items():
            # Older Crate exporters included their own target installation
            # records. Never restore these as authoritative state; rebuild
            # them from the verified plugin artifacts below.
            if relative.split('/')[0].casefold() == '.dsh-crate':
                continue
            _write_file(temp_profile, relative, content)

        installed: list[dict[str, Any]] = []
        lock_plugins = [plugin for plugin in data.plugins_lock.get("plugins", []) if isinstance(plugin, Mapping)]
        installed_names: set[str] = set()

        # npm reconciles the entire tree and can prune previously extracted
        # packages. Complete every npm operation before materializing embedded
        # artifacts and explicit local sources.
        network_dependencies: dict[str, str] = {}
        if network_plugins:
            _write_network_manifest(temp_profile, network_dependencies)
        for plugin in lock_plugins:
            artifact = plugin.get("artifact")
            if not isinstance(artifact, Mapping) or artifact.get("mode") != "reference-only":
                continue
            name = str(plugin["name"])
            if options.reference_installer is not None or name in options.reference_plugin_sources:
                continue
            if not (options.allow_network_reference_install and name in network_plugins):
                continue
            try:
                network_installs.append(_install_network_reference(temp_profile, plugin, options))
            except PackImportError as error:
                if plugin.get("required") is True:
                    raise
                _remove_staged_package(temp_profile, name, stage="network-install")
                warnings.append(error.as_dict())
                continue
            installed_names.add(name)
            network_dependencies[name] = _network_dependency_spec(plugin)
            _write_network_manifest(temp_profile, network_dependencies)
        if network_plugins:
            (temp_profile / "package.json").write_bytes(data.profile_files["package.json"])

        for plugin in lock_plugins:
            artifact = plugin.get("artifact")
            if not isinstance(artifact, Mapping) or artifact.get("mode") != "embedded":
                continue
            path = artifact.get("path")
            if not isinstance(path, str):
                raise PackImportError(
                    f"embedded artifact path missing for {plugin.get('name')}",
                    stage="embedded-install",
                    code="ARTIFACT_PATH_MISSING",
                )
            content = data.plugin_artifacts.get(path[len("plugins/"):])
            if content is None:
                raise PackImportError(
                    f"embedded artifact missing for {plugin.get('name')}: {path}",
                    stage="embedded-install",
                    code="REQUIRED_ARTIFACT_MISSING",
                )
            _remove_staged_package(temp_profile, str(plugin["name"]), stage="embedded-install")
            _extract_embedded_artifact(temp_profile, plugin, content)
            installed_names.add(str(plugin["name"]))

        for plugin in lock_plugins:
            artifact = plugin.get("artifact")
            if not isinstance(artifact, Mapping) or artifact.get("mode") != "reference-only":
                continue
            name = str(plugin["name"])
            if options.reference_installer is not None:
                try:
                    options.reference_installer(temp_profile, plugin)
                except PackImportError:
                    raise
                except Exception as error:
                    raise PackImportError(
                        f"reference-only plugin installation failed: {name}",
                        stage="reference-install",
                        code="PLUGIN_INSTALL_FAILED",
                        details={"plugin": name, "error": str(error)},
                    ) from error
                installed_names.add(name)
                continue
            if name in options.reference_plugin_sources:
                _remove_staged_package(temp_profile, name, stage="reference-install")
                _copy_reference_source(temp_profile, plugin, Path(options.reference_plugin_sources[name]))
                installed_names.add(name)
                continue
            if options.allow_network_reference_install and name in network_plugins:
                continue  # final identity verification follows all installs
            if plugin.get("required") is True:
                raise PackImportError(
                    f"required reference-only plugin was not installed: {name}",
                    stage="reference-install",
                    code="PLUGIN_MISSING",
                    details={"plugin": name},
                )

        # A later npm operation or installer can replace an earlier package.
        # Confirm the final tree, not stale per-install observations, before any
        # portable Home data is written or the prepared Profile is committed.
        if options.pnpm_command:
            selected = [plugin for plugin in lock_plugins if str(plugin['name']) in installed_names]
            # Validate the inputs before letting the manager consume them.
            for plugin in selected:
                _verify_identity(temp_profile, plugin)
            network_installs.append(_pnpm_rebuild(temp_profile, data, selected, options))
        installed = [_verify_identity(temp_profile, plugin) for plugin in lock_plugins
                     if str(plugin["name"]) in installed_names]

        restore_files(plan.dsh_home, data.user_data, data_created, data_directories)
        pack_digest = sha256_bytes(plan.pack_path.read_bytes())
        final_profile = plan.profile_path
        if final_profile.exists():
            if not plan.overwrite:
                raise PackImportError(
                    f"target Profile appeared during Import: {final_profile}",
                    stage="commit",
                    code="PROFILE_EXISTS",
                )
            original_profile_backup = profiles_root / f".{plan.profile_name}.dsh-pack-backup-{backup_token}"
            final_profile.rename(original_profile_backup)
        if plan.metadata_path.exists():
            if not plan.overwrite:
                raise PackImportError(
                    f"target Import metadata appeared during Import: {plan.metadata_path}",
                    stage="commit",
                    code="PROFILE_EXISTS",
                )
            original_metadata_backup = metadata_parent / f".{plan.profile_name}.dsh-pack-backup-{backup_token}"
            plan.metadata_path.rename(original_metadata_backup)
        _commit_prepared_profile(temp_profile, final_profile)
        temp_profile = None
        final_created = True

        metadata_parent.mkdir(parents=True, exist_ok=True)
        plan.metadata_path.mkdir(parents=False, exist_ok=False)
        metadata_created = True
        (plan.metadata_path / "manifest.json").write_bytes(json.dumps(data.manifest, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n")
        (plan.metadata_path / "plugins.lock.json").write_bytes(json.dumps(data.plugins_lock, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n")
        (plan.metadata_path / "prepared.json").write_bytes(
            json.dumps(_metadata_payload(plan, data, tuple(installed), pack_digest,
                       network_installs[-1] if options.pnpm_command else None), ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"
        )
        for backup in (original_profile_backup, original_metadata_backup):
            if backup is None:
                continue
            try:
                _cleanup(backup)
            except OSError as error:
                warnings.append(
                    {
                        "code": "OVERWRITE_BACKUP_RETAINED",
                        "stage": "commit",
                        "item": str(backup),
                        "message": "previous Profile data was retained as a recovery backup",
                        "details": {"path": str(backup), "error": str(error)},
                    }
                )
        return ImportResult(
            status="prepared",
            profile_path=final_profile,
            metadata_path=plan.metadata_path,
            plan=plan,
            installed_plugins=tuple(installed),
            network_installs=tuple(network_installs),
            warnings=tuple(warnings),
        )
    except (DshPackError, OSError, tarfile.TarError, ValueError) as error:
        # Preserve the first failure before compensation. A Windows sharing
        # lock may reject both the commit rename and subsequent cleanup.
        # Cleanup must not replace that error or claim an unobserved rollback.
        observed = {"error": str(error), "errorType": type(error).__name__}
        if isinstance(error, OSError):
            observed.update({key: getattr(error, key, None)
                             for key in ("errno", "winerror", "filename", "filename2")})
        failure = error if isinstance(error, DshPackError) else PackImportError(
            "Import failed unexpectedly",
            stage="commit",
            code="IMPORT_FAILED",
            details={
                "item": "prepared metadata / Profile commit",
                "expected": {"operation": "write prepared metadata and commit the new Profile"},
                "observed": observed,
                "evidence": {"profilePath": str(plan.profile_path), "metadataPath": str(plan.metadata_path)},
                "impact": "Import failed; inspect the recorded rollback outcome",
                "error": str(error),
            },
        )
        rollback_errors: list[dict[str, Any]] = []

        def compensate(operation: str, path: Path | None, action: Callable[[], None]) -> None:
            try:
                action()
            except OSError as cleanup_error:
                rollback_errors.append({
                    "operation": operation, "path": str(path) if path is not None else None,
                    "error": str(cleanup_error), "errorType": type(cleanup_error).__name__,
                    "errno": cleanup_error.errno, "winerror": getattr(cleanup_error, "winerror", None),
                })

        # Portable files are independent cleanup actions: one locked file must
        # not prevent removing another file created by this Import.
        for created_path in reversed(data_created):
            compensate("remove-portable-file", created_path, lambda path=created_path: path.unlink(missing_ok=True))
        for created_directory in reversed(data_directories):
            compensate("remove-portable-directory", created_directory, lambda path=created_directory: _cleanup_empty(path))
        compensate("remove-temporary-profile", temp_profile, lambda: _cleanup(temp_profile))
        if final_created:
            compensate("remove-failed-profile", plan.profile_path, lambda: _cleanup(plan.profile_path))
        if metadata_created:
            compensate("remove-failed-metadata", plan.metadata_path, lambda: _cleanup(plan.metadata_path))
        for operation, backup, destination in (
            ("restore-original-profile", original_profile_backup, plan.profile_path),
            ("restore-original-metadata", original_metadata_backup, plan.metadata_path),
        ):
            if backup is None or not backup.exists():
                continue
            if destination.exists():
                rollback_errors.append({"operation": operation, "path": str(backup),
                    "error": "恢复目标仍被占用，原始备份已保留，未覆盖该路径。", "destination": str(destination)})
            else:
                compensate(operation, backup, lambda saved=backup, target=destination: saved.rename(target))
        if not metadata_parent_existed:
            compensate("remove-empty-metadata-parent", metadata_parent, lambda: _cleanup_empty(metadata_parent))
        if not metadata_root_existed:
            compensate("remove-empty-metadata-root", metadata_root, lambda: _cleanup_empty(metadata_root))
        if isinstance(failure, PackImportError):
            retained_temp = temp_profile is not None and temp_profile.exists()
            original_retained = original_profile_backup is not None and original_profile_backup.exists()
            original_metadata_retained = original_metadata_backup is not None and original_metadata_backup.exists()
            failure.details.update({
                "temporaryProfileStatus": "retained" if retained_temp else "cleaned",
                "failedProfileStatus": "retained" if final_created and plan.profile_path.exists() else "cleaned",
                "originalProfileStatus": "restore-failed" if original_retained else "unchanged",
                "rollback": {
                    "status": "FAIL" if rollback_errors else "PASS", "errors": rollback_errors,
                    "temporaryProfilePath": str(temp_profile) if retained_temp else None,
                    "originalProfileBackup": str(original_profile_backup) if original_retained else None,
                    "originalMetadataBackup": str(original_metadata_backup) if original_metadata_retained else None,
                },
            })
            if rollback_errors:
                failure.details.update({
                    "canRetry": False,
                    "impact": "导入失败，部分回滚未完成；请保留并检查诊断中列出的残留和备份路径。",
                    "suggestedNextStep": "先检查原始错误与回滚错误，解除占用并核实残留及原 Profile 状态，再手动重新导入。",
                })
        if failure is error:
            raise
        raise failure from error


def delete_profile(
    dsh_home: str | os.PathLike[str],
    profile_name: str,
    *,
    confirmation: str | None = None,
) -> DeleteResult:
    """Delete exactly one Profile and its Import metadata after explicit confirmation.

    Deleting a Profile also removes ``DSH_HOME/.dsh-pack/imports/<name>`` so
    the name is not left permanently reserved by a stale prepared record. If
    metadata cleanup fails, the Profile itself stays deleted and the failure is
    reported through ``DeleteResult.metadata_status``.
    """

    if confirmation != "DELETE":
        raise PackImportError(
            "deleting a Profile requires explicit confirmation",
            stage="planning",
            code="DELETE_CONFIRMATION_REQUIRED",
            details={
                "expected": "DELETE",
                "observed": "confirmation missing or invalid",
                "impact": "No Profile was changed.",
                "suggestedNextStep": "Confirm the destructive deletion in the user interface and retry.",
            },
        )
    safe_name = _validate_profile_name(profile_name, label="Target Profile name")
    home = Path(dsh_home).resolve()
    profiles_root = home / "profiles"
    target = profiles_root / safe_name
    if target.is_symlink() or (target.exists() and not target.is_dir()):
        raise PackImportError(
            f"target Profile is not a safe directory: {target}",
            stage="planning",
            code="PROFILE_TARGET_INVALID",
            details={"profilePath": str(target)},
        )
    if not target.exists():
        raise PackImportError(
            f"target Profile does not exist: {target}",
            stage="planning",
            code="PROFILE_NOT_FOUND",
            details={"profilePath": str(target)},
        )
    metadata_target = home / ".dsh-pack" / "imports" / safe_name
    if metadata_target.is_symlink() or (metadata_target.exists() and not metadata_target.is_dir()):
        raise PackImportError(
            f"Import metadata for the target Profile is not a safe directory: {metadata_target}",
            stage="planning",
            code="PROFILE_TARGET_INVALID",
            details={"metadataPath": str(metadata_target)},
        )
    backup = profiles_root / f".{safe_name}.dsh-pack-delete-{uuid.uuid4().hex}"
    try:
        target.rename(backup)
        shutil.rmtree(backup)
    except OSError as error:
        if backup.exists() and not target.exists():
            try:
                backup.rename(target)
            except OSError:
                pass
        raise PackImportError(
            f"failed to delete Profile: {target}",
            stage="delete",
            code="PROFILE_DELETE_FAILED",
            details={
                "profilePath": str(target),
                "error": str(error),
                "originalProfileStatus": "restored" if target.exists() else "unknown",
            },
        ) from error
    metadata_status = "no-metadata"
    if metadata_target.exists():
        metadata_backup = metadata_target.parent / f".{safe_name}.dsh-pack-delete-{uuid.uuid4().hex}"
        try:
            metadata_target.rename(metadata_backup)
            shutil.rmtree(metadata_backup)
            metadata_status = "removed"
        except OSError as error:
            metadata_status = "failed"
            if metadata_backup.exists() and not metadata_target.exists():
                try:
                    metadata_backup.rename(metadata_target)
                except OSError:
                    pass
    return DeleteResult(
        status="deleted",
        profile_name=safe_name,
        profile_path=target,
        metadata_path=metadata_target,
        metadata_status=metadata_status,
    )
