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
import os
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
from .preflight import PreflightContext, PreflightResult, inspect_pack
from .validation import validate_archive_path


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
        resolved = plugin.get("resolved")
        version = resolved.get("version") if isinstance(resolved, Mapping) else None
        requirements[name] = version if isinstance(version, str) else None
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


def _manifest_declares_workspace(content: bytes) -> bool:
    """Return True when an embedded tarball uses the workspace: protocol.

    Workspace-protocol dependencies cannot be reconciled by npm outside the
    DSH monorepo, and their packages are supplied by the DSH installation
    anchor at runtime.  Such embedded packages are extracted as-is and skip
    the package-manager closure pass.
    """

    try:
        with tarfile.open(fileobj=BytesIO(content), mode="r:gz") as archive:
            member = archive.getmember("package/package.json")
            extracted = archive.extractfile(member)
            if extracted is None:
                return False
            manifest = json.loads(extracted.read())
    except (KeyError, OSError, tarfile.TarError, json.JSONDecodeError):
        return False
    if not isinstance(manifest, dict):
        return False
    declared = dict(manifest.get("dependencies") or {})
    declared.update(manifest.get("peerDependencies") or {})
    return any(
        isinstance(specifier, str) and specifier.startswith("workspace:")
        for specifier in declared.values()
    )


def _install_embedded_dependencies(
    profile_path: Path,
    embedded_artifacts: list[tuple[dict[str, Any], bytes]],
    options: ImportOptions,
) -> None:
    """Install the dependency closure of every eligible embedded plugin.

    An embedded artifact is the recorded package tarball itself; it carries the
    plugin code but not the plugin's transitive ``dependencies``.  A single npm
    reconciliation with every eligible embedded tarball as an install argument
    restores that closure so the resulting Profile can boot with the same
    dependency closure the source Profile had.  Embedded packages that declare
    ``workspace:`` protocol dependencies are excluded: their closure is supplied
    by the DSH installation anchor at runtime.  Lifecycle scripts stay disabled
    and the local npm cache is preferred so already-available dependencies do
    not require a second network round trip.
    """

    if not embedded_artifacts:
        return
    # DSH workspace packages declare their internal dependencies with the
    # workspace: protocol, which a plain package manager cannot reconcile
    # outside the monorepo.  Those closures are supplied by the DSH
    # installation anchor at runtime, so the extracted package is kept as-is
    # and only plugins with a normal registry closure run through npm.
    eligible: list[tuple[dict[str, Any], bytes]] = []
    for plugin, content in embedded_artifacts:
        if _manifest_declares_workspace(content):
            continue
        eligible.append((plugin, content))
    if not eligible:
        return
    staging = Path(tempfile.mkdtemp(prefix=".dsh-pack-embedded-", dir=profile_path.parent))
    names = [str(plugin.get("name")) for plugin, _content in eligible]
    try:
        tarball_paths: list[str] = []
        for index, (_plugin, content) in enumerate(eligible):
            tarball = staging / f"embedded-{index}.tgz"
            tarball.write_bytes(content)
            tarball_paths.append(str(tarball))
        command = [
            _npm_command(options.npm_command),
            "install",
            "--ignore-scripts",
            "--legacy-peer-deps",
            "--no-save",
            "--no-package-lock",
            "--no-audit",
            "--no-fund",
            "--prefer-offline",
            "--prefix",
            str(profile_path),
            "--",
            *tarball_paths,
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
                f"npm command is unavailable while installing embedded dependencies for {', '.join(names)}",
                stage="embedded-install",
                code="EMBEDDED_NPM_UNAVAILABLE",
                details={"plugins": names, "command": command[0], "error": str(error)},
            ) from error
        except subprocess.TimeoutExpired as error:
            raise PackImportError(
                f"embedded dependency install timed out for {', '.join(names)}",
                stage="embedded-install",
                code="EMBEDDED_DEPENDENCIES_TIMEOUT",
                details={"plugins": names, "timeoutSeconds": options.network_install_timeout},
            ) from error
        except OSError as error:
            raise PackImportError(
                f"cannot start npm while installing embedded dependencies for {', '.join(names)}",
                stage="embedded-install",
                code="EMBEDDED_NPM_FAILED",
                details={"plugins": names, "command": command[0], "error": str(error)},
            ) from error
        if completed.returncode != 0:
            raise PackImportError(
                f"embedded dependency install failed for {', '.join(names)} with exit code {completed.returncode}",
                stage="embedded-install",
                code="EMBEDDED_DEPENDENCIES_INSTALL_FAILED",
                details={
                    "plugins": names,
                    "command": command,
                    "exitCode": completed.returncode,
                    "stdout": _network_error_output(completed.stdout),
                    "stderr": _network_error_output(completed.stderr),
                },
            )
    finally:
        _cleanup(staging)


def _context(options: ImportOptions) -> PreflightContext:
    return PreflightContext(
        current_environment=dict(options.current_environment),
        available_secrets=set() if options.available_secrets is None else set(options.available_secrets),
        available_plugins=_reference_inventory(options),
        allow_network_reference_install=options.allow_network_reference_install,
    )


def _plugin_rows(lock: Mapping[str, Any], mode: str) -> tuple[dict[str, Any], ...]:
    result: list[dict[str, Any]] = []
    for plugin in lock.get("plugins", []):
        if not isinstance(plugin, Mapping):
            continue
        artifact = plugin.get("artifact")
        if not isinstance(artifact, Mapping) or artifact.get("mode") != mode:
            continue
        resolved = plugin.get("resolved")
        result.append(
            {
                "name": plugin.get("name"),
                "version": resolved.get("version") if isinstance(resolved, Mapping) else None,
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
    resolved = plugin.get("resolved")
    expected_version = resolved.get("version") if isinstance(resolved, Mapping) else None
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
    return {"name": name, "version": installed["version"], "mode": plugin["artifact"]["mode"]}


def _metadata_payload(plan: ImportPlan, data: PackData, installed: tuple[dict[str, Any], ...], pack_digest: str) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "status": "prepared",
        "pack": {"sha256": pack_digest, "path": str(plan.pack_path)},
        "profile": {"name": plan.profile_name, "path": str(plan.profile_path)},
        "overwrite": plan.overwrite,
        "plugins": list(installed),
        "requiredSecrets": list(data.manifest.get("requiredSecrets", [])),
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
            _write_file(temp_profile, relative, content)

        installed: dict[str, dict[str, Any]] = {}
        lock_plugins = [plugin for plugin in data.plugins_lock.get("plugins", []) if isinstance(plugin, Mapping)]

        # Network reference installs run first: npm reconciles the whole
        # Profile tree at the temporary prefix and prunes packages that are not
        # part of its resolution.  Manually placed packages (embedded extracts
        # and local reference copies) must therefore be written only after every
        # npm operation has finished, or npm would delete them.
        for plugin in lock_plugins:
            artifact = plugin.get("artifact")
            if not isinstance(artifact, Mapping) or artifact.get("mode") != "reference-only":
                continue
            name = str(plugin["name"])
            if options.reference_installer is not None or name in options.reference_plugin_sources:
                continue  # handled by the local-source pass below
            if not (options.allow_network_reference_install and name in network_plugins):
                continue
            try:
                network_installs.append(_install_network_reference(temp_profile, plugin, options))
            except PackImportError as error:
                if plugin.get("required") is True:
                    raise
                warnings.append(error.as_dict())
                continue
            installed[name] = _verify_identity(temp_profile, plugin)

        # Embedded artifacts are self-contained package tarballs.  Collect
        # them, install the eligible dependency closure through the package
        # manager BEFORE any manual placement so a reconciling npm run cannot
        # prune manually placed packages, then extract whatever npm did not
        # place (workspace-protocol packages whose closure is supplied by the
        # DSH installation anchor).
        embedded_artifacts: list[tuple[dict[str, Any], bytes]] = []
        for plugin in lock_plugins:
            artifact = plugin.get("artifact")
            if not isinstance(artifact, Mapping) or artifact.get("mode") != "embedded":
                continue
            name = str(plugin["name"])
            path = artifact.get("path")
            if not isinstance(path, str):
                raise PackImportError(
                    f"embedded artifact path missing for {name}",
                    stage="embedded-install",
                    code="ARTIFACT_PATH_MISSING",
                )
            content = data.plugin_artifacts.get(path[len("plugins/"):])
            if content is None:
                raise PackImportError(
                    f"embedded artifact missing for {name}: {path}",
                    stage="embedded-install",
                    code="REQUIRED_ARTIFACT_MISSING",
                )
            embedded_artifacts.append((plugin, content))
        _install_embedded_dependencies(temp_profile, embedded_artifacts, options)
        for plugin, _content in embedded_artifacts:
            name = str(plugin["name"])
            if not _package_install_path(temp_profile, name).exists():
                _extract_embedded_artifact(temp_profile, plugin, _content)
            installed[name] = _verify_identity(temp_profile, plugin)

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
                installed[name] = _verify_identity(temp_profile, plugin)
                continue
            if name in options.reference_plugin_sources:
                _copy_reference_source(temp_profile, plugin, Path(options.reference_plugin_sources[name]))
                installed[name] = _verify_identity(temp_profile, plugin)
                continue
            if options.allow_network_reference_install and name in network_plugins:
                continue  # already installed and verified in the network pass
            if plugin.get("required") is True:
                raise PackImportError(
                    f"required reference-only plugin was not installed: {name}",
                    stage="reference-install",
                    code="PLUGIN_MISSING",
                    details={"plugin": name},
                )

        # Re-verify every installed package after the final install pass so a
        # package-manager reconciliation that pruned a manually placed package
        # is caught here instead of surfacing as a Profile that cannot boot.
        for plugin in lock_plugins:
            artifact = plugin.get("artifact")
            if not isinstance(artifact, Mapping) or artifact.get("mode") not in ("embedded", "reference-only"):
                continue
            name = str(plugin["name"])
            if name not in installed:
                continue
            installed[name] = _verify_identity(temp_profile, plugin)

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
        temp_profile.rename(final_profile)
        temp_profile = None
        final_created = True

        metadata_parent.mkdir(parents=True, exist_ok=True)
        plan.metadata_path.mkdir(parents=False, exist_ok=False)
        metadata_created = True
        (plan.metadata_path / "manifest.json").write_bytes(json.dumps(data.manifest, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n")
        (plan.metadata_path / "plugins.lock.json").write_bytes(json.dumps(data.plugins_lock, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n")
        (plan.metadata_path / "prepared.json").write_bytes(
            json.dumps(_metadata_payload(plan, data, tuple(installed.values()), pack_digest), ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"
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
            installed_plugins=tuple(installed.values()),
            network_installs=tuple(network_installs),
            warnings=tuple(warnings),
        )
    except PackImportError:
        _cleanup(temp_profile)
        if final_created:
            _cleanup(plan.profile_path)
        if metadata_created:
            _cleanup(plan.metadata_path)
        if original_profile_backup is not None and original_profile_backup.exists() and not plan.profile_path.exists():
            original_profile_backup.rename(plan.profile_path)
        if original_metadata_backup is not None and original_metadata_backup.exists() and not plan.metadata_path.exists():
            original_metadata_backup.rename(plan.metadata_path)
        if not metadata_parent_existed:
            _cleanup_empty(metadata_parent)
        if not metadata_root_existed:
            _cleanup_empty(metadata_root)
        raise
    except (OSError, tarfile.TarError, ValueError) as error:
        _cleanup(temp_profile)
        if final_created:
            _cleanup(plan.profile_path)
        if metadata_created:
            _cleanup(plan.metadata_path)
        if original_profile_backup is not None and original_profile_backup.exists() and not plan.profile_path.exists():
            original_profile_backup.rename(plan.profile_path)
        if original_metadata_backup is not None and original_metadata_backup.exists() and not plan.metadata_path.exists():
            original_metadata_backup.rename(plan.metadata_path)
        if not metadata_parent_existed:
            _cleanup_empty(metadata_parent)
        if not metadata_root_existed:
            _cleanup_empty(metadata_root)
        raise PackImportError(
            "Import failed unexpectedly",
            stage="commit",
            code="IMPORT_FAILED",
            details={
                "item": "prepared metadata / Profile commit",
                "expected": {"operation": "write prepared metadata and commit the new Profile"},
                "observed": {"error": str(error)},
                "evidence": {"profilePath": str(plan.profile_path), "metadataPath": str(plan.metadata_path)},
                "impact": "Import failed during commit and was rolled back",
                "error": str(error),
            },
        ) from error


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

