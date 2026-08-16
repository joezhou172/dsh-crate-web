"""Safe ZIP container operations for the Phase 1 DSH Pack format."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import DuplicateEntryError, IntegrityError, PackFormatError, PathSafetyError
from .validation import (
    validate_archive_path,
    validate_manifest,
    validate_payload_key,
    validate_plugins_lock,
)


def sha256_bytes(data: bytes) -> str:
    """Return the lowercase SHA-256 digest for one byte sequence."""

    return hashlib.sha256(data).hexdigest()


def _file_bytes(value: Any, path: str) -> bytes:
    if isinstance(value, str):
        return value.encode("utf-8")
    if isinstance(value, bytes):
        return value
    if isinstance(value, (bytearray, memoryview)):
        return bytes(value)
    raise TypeError(f"{path} values must be str or bytes")


def _file_map(value: Any, path: str, root: str) -> dict[str, bytes]:
    if not isinstance(value, dict):
        raise TypeError(f"{path} must be a mapping of relative paths to bytes")
    result: dict[str, bytes] = {}
    for key, content in value.items():
        archive_path = validate_payload_key(key, root, path)
        relative = archive_path[len(root) + 1:]
        if relative in result:
            raise DuplicateEntryError(f"duplicate logical Pack member: {archive_path}")
        result[relative] = _file_bytes(content, f"{path}[{key!r}]")
    return result


@dataclass
class PackData:
    """Semantic Pack data independent of ZIP ordering or compression."""

    manifest: dict[str, Any]
    profile_files: dict[str, bytes | str]
    plugins_lock: dict[str, Any]
    plugin_artifacts: dict[str, bytes | str]


def _normalise_data(data: PackData) -> tuple[dict[str, Any], dict[str, bytes], dict[str, Any], dict[str, bytes]]:
    if not isinstance(data, PackData):
        raise TypeError("create() expects PackData")
    manifest = copy.deepcopy(data.manifest)
    profile_files = _file_map(data.profile_files, "profile_files", "profile")
    plugin_artifacts = _file_map(data.plugin_artifacts, "plugin_artifacts", "plugins")
    plugins_lock = copy.deepcopy(data.plugins_lock)
    if not profile_files:
        raise PackFormatError("profile/ must contain at least one file")
    validate_manifest(manifest)
    artifact_paths = {f"plugins/{name}" for name in plugin_artifacts}
    validate_plugins_lock(plugins_lock, artifact_paths=artifact_paths)
    _validate_artifact_hashes(plugins_lock, plugin_artifacts)
    return manifest, profile_files, plugins_lock, plugin_artifacts


def _validate_artifact_hashes(plugins_lock: dict[str, Any], plugin_artifacts: dict[str, bytes]) -> None:
    for index, plugin in enumerate(plugins_lock["plugins"]):
        artifact = plugin["artifact"]
        if artifact["mode"] != "embedded":
            continue
        path = artifact["path"]
        relative = path[len("plugins/"):]
        actual = sha256_bytes(plugin_artifacts[relative])
        if actual != artifact["sha256"]:
            raise IntegrityError(
                f"plugins.lock.plugins[{index}].artifact.sha256 does not match {path}"
            )


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _payload_entries(
    profile_files: dict[str, bytes],
    plugins_lock_bytes: bytes,
    plugin_artifacts: dict[str, bytes],
) -> dict[str, bytes]:
    entries: dict[str, bytes] = {"plugins.lock.json": plugins_lock_bytes}
    entries.update({f"profile/{name}": content for name, content in profile_files.items()})
    entries.update({f"plugins/{name}": content for name, content in plugin_artifacts.items()})
    return dict(sorted(entries.items()))


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 0
    info.external_attr = 0o600 << 16
    return info


def create(data: PackData, destination: str | os.PathLike[str]) -> Path:
    """Create one `.dshcrate` atomically and return its path.

    The manifest integrity table covers every member except `manifest.json`
    itself; self-hashing the manifest would be circular. ZIP member order is
    deterministic but is not part of the Pack semantics.
    """

    manifest, profile_files, plugins_lock, plugin_artifacts = _normalise_data(data)
    lock_bytes = _json_bytes(plugins_lock)
    entries = _payload_entries(profile_files, lock_bytes, plugin_artifacts)
    manifest["integrity"] = {
        "algorithm": "sha256",
        "files": {name: sha256_bytes(content) for name, content in entries.items()},
    }
    validate_manifest(manifest, require_integrity=True)
    manifest_bytes = _json_bytes(manifest)

    destination_path = Path(destination)
    if not destination_path.name:
        raise PackFormatError("destination must be a file path")
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=f".{destination_path.name}.", suffix=".tmp",
            dir=destination_path.parent, delete=False,
        ) as temp:
            temp_path = Path(temp.name)
        with zipfile.ZipFile(temp_path, mode="w", compression=zipfile.ZIP_DEFLATED, allowZip64=False) as archive:
            archive.writestr(_zip_info("manifest.json"), manifest_bytes)
            for name, content in entries.items():
                archive.writestr(_zip_info(name), content)
        os.replace(temp_path, destination_path)
        temp_path = None
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass
    return destination_path


def _validate_archive_member(name: str) -> str:
    canonical = validate_archive_path(name)
    if canonical == "manifest.json" or canonical == "plugins.lock.json":
        return canonical
    if canonical.startswith("profile/") or canonical.startswith("plugins/"):
        return canonical
    raise PathSafetyError(f"unsupported Pack member path: {name!r}")


def _read_json(content: bytes, name: str) -> dict[str, Any]:
    try:
        value = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PackFormatError(f"{name} is not valid UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise PackFormatError(f"{name} must contain a JSON object")
    return value


def _read_entries(source: Path) -> dict[str, bytes]:
    try:
        archive = zipfile.ZipFile(source, mode="r")
    except (FileNotFoundError, zipfile.BadZipFile, OSError) as error:
        raise PackFormatError(f"cannot open Pack ZIP: {source}") from error
    with archive:
        entries: dict[str, bytes] = {}
        for info in archive.infolist():
            if info.is_dir() or info.filename.endswith("/"):
                raise PathSafetyError(f"directory ZIP members are not allowed: {info.filename!r}")
            name = _validate_archive_member(info.filename)
            if name in entries:
                raise DuplicateEntryError(f"duplicate ZIP member: {name}")
            try:
                entries[name] = archive.read(info)
            except (OSError, RuntimeError, zipfile.BadZipFile) as error:
                raise PackFormatError(f"cannot read ZIP member: {name}") from error
    return entries


def _verify_integrity(manifest: dict[str, Any], entries: dict[str, bytes]) -> None:
    files = manifest["integrity"]["files"]
    actual_files = set(entries) - {"manifest.json"}
    declared_files = set(files)
    if declared_files != actual_files:
        missing = sorted(declared_files - actual_files)
        unexpected = sorted(actual_files - declared_files)
        raise IntegrityError(f"integrity file set mismatch; missing={missing}, unexpected={unexpected}")
    for name, expected in files.items():
        actual = sha256_bytes(entries[name])
        if actual != expected:
            raise IntegrityError(f"SHA-256 mismatch for {name}: expected {expected}, got {actual}")


def read(source: str | os.PathLike[str]) -> PackData:
    """Read, validate, and return semantic data from one `.dshcrate`."""

    source_path = Path(source)
    entries = _read_entries(source_path)
    if "manifest.json" not in entries:
        raise PackFormatError("Pack is missing manifest.json")
    if "plugins.lock.json" not in entries:
        raise PackFormatError("Pack is missing plugins.lock.json")
    if not any(name.startswith("profile/") for name in entries):
        raise PackFormatError("Pack is missing profile/ files")

    manifest = _read_json(entries["manifest.json"], "manifest.json")
    validate_manifest(manifest, require_integrity=True)
    _verify_integrity(manifest, entries)
    plugins_lock = _read_json(entries["plugins.lock.json"], "plugins.lock.json")
    profile_files = {
        name[len("profile/"):]: content
        for name, content in entries.items()
        if name.startswith("profile/")
    }
    plugin_artifacts = {
        name[len("plugins/"):]: content
        for name, content in entries.items()
        if name.startswith("plugins/")
    }
    validate_plugins_lock(
        plugins_lock,
        artifact_paths={f"plugins/{name}" for name in plugin_artifacts},
    )
    _validate_artifact_hashes(plugins_lock, plugin_artifacts)
    return PackData(
        manifest=manifest,
        profile_files=profile_files,
        plugins_lock=plugins_lock,
        plugin_artifacts=plugin_artifacts,
    )
