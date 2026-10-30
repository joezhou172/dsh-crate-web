"""Opt-in portable data for released v0/v4 JSONL and JSON storage layouts.

Plugin storage ownership must be explicitly selected; filenames never imply it.
"""
from __future__ import annotations
import hashlib
import json
import ntpath
import os
import posixpath
import re
from pathlib import Path
from typing import Any, Mapping, Sequence
from .errors import ExportError, PackImportError, SchemaValidationError
from .validation import validate_archive_path

KINDS = {"conversation", "plugin-config", "plugin-workflow", "plugin-data"}
CLASSES = {"portable", "reference-only", "secret-name-only", "excluded", "unsupported"}
MAX_DATA_BYTES = 32 * 1024 * 1024
MAX_TOTAL_BYTES = 128 * 1024 * 1024
_SECRET_KEY = re.compile(r"(?i)^(?:.*[_-])?(?:api[_-]?key|access[_-]?token|auth[_-]?token|secret|password|credential|cookie|authorization|private[_-]?key)s?$")
_SECRET_TEXT = re.compile(
    r"(?i)(?:-----BEGIN (?:[A-Z ]*PRIVATE KEY)-----|"
    r"\bBearer\s+[A-Za-z0-9._~+/=-]{8,}|"
    r"\b(?:sk-|ghp_|github_pat_)[A-Za-z0-9_-]{12,}|"
    r"(?<![A-Za-z0-9_])(?:api[_-]?key|access[_-]?token|password|authorization|cookie)"
    r"\s*[\"']?\s*[:=]\s*[\"']?(?!\$\{)[^\s\"',}\]]{4,})"
)
_PLACEHOLDER = re.compile(r"^\$\{[A-Za-z_][A-Za-z0-9_]*\}$")
_SESSION_NAMES = {"session.jsonl": 0, "session.v4.jsonl": 4}


def _session_generation(filename: str) -> int | None:
    return _SESSION_NAMES.get(filename.removesuffix(".zstd"))


def _safe_integer(value: Any, *, minimum: int = 0) -> bool:
    return type(value) is int and minimum <= value <= 2**53 - 1


def _validate_v4_session(header: Mapping[str, Any], events: Sequence[Any]) -> None:
    """Inspect released framing and closed turn boundaries without rewriting it.

    Source: official 0.2.1-rc.2 session-format-v3-to-v4 physical codec delegates
    to released v2 framing. Empty and metadata-only sessions are valid artifacts;
    an open turn, step, seed boundary or torn physical tail is not portable.
    Plugin payload interpretation and runtime restoration remain Verify's job.
    """
    required = {"type", "version", "id", "createdAt", "isSeeded", "delegationDepth"}
    allowed = required | {"cwd", "parentSession", "origin", "agentPreset"}
    if (not required.issubset(header) or not set(header).issubset(allowed)
            or type(header.get("isSeeded")) is not bool
            or not _safe_integer(header.get("createdAt"))
            or not _safe_integer(header.get("delegationDepth"))
            or any(key in header and not isinstance(header[key], str)
                   for key in ("cwd", "parentSession", "agentPreset"))
            or ("cwd" in header and not (ntpath.isabs(header["cwd"]) or posixpath.isabs(header["cwd"])))
            or ("origin" in header and header["origin"] != "subagent")):
        raise ExportError("unsupported v4 session header; a matching DSH adapter is required")
    event_required = {"type", "seq", "time", "data"}
    event_allowed = event_required | {"ignorable", "sourceEventSeqs", "surfaceOp"}
    turn = step = None
    next_turn = next_step = 1
    inherited_marker = False
    for index, event in enumerate(events):
        if (not isinstance(event, dict) or not event_required.issubset(event)
                or not set(event).issubset(event_allowed)
                or not isinstance(event["type"], str) or not event["type"]
                or not _safe_integer(event["seq"]) or event["seq"] != index
                or not _safe_integer(event["time"], minimum=-(2**53 - 1))
                or not isinstance(event["data"], dict)
                or ("ignorable" in event and event["ignorable"] is not True)):
            raise ExportError("invalid v4 session event envelope or sequence")
        name, data = event["type"], event["data"]
        if name == "turn/start":
            if turn is not None or not _safe_integer(data.get("turn"), minimum=1) or data["turn"] != next_turn:
                raise ExportError("invalid v4 session turn boundary")
            turn, next_step = next_turn, 1
        elif name == "turn/end":
            if (turn is None or not _safe_integer(data.get("turn"), minimum=1)
                    or data["turn"] != turn or step is not None
                    or not isinstance(data.get("reason"), dict)
                    or not isinstance(data["reason"].get("kind"), str)):
                raise ExportError("invalid or unfinished v4 session turn")
            turn, next_turn = None, next_turn + 1
        elif name == "step/start":
            if (turn is None or not _safe_integer(data.get("turn"), minimum=1)
                    or data["turn"] != turn or step is not None
                    or not _safe_integer(data.get("step"), minimum=1) or data["step"] != next_step):
                raise ExportError("invalid v4 session step boundary")
            step = next_step
        elif name == "step/end":
            if (turn is None or not _safe_integer(data.get("turn"), minimum=1) or data["turn"] != turn
                    or step is None or not _safe_integer(data.get("step"), minimum=1) or data["step"] != step):
                raise ExportError("invalid v4 session step boundary")
            step, next_step = None, next_step + 1
        elif name == "session/end-seed" and data.get("inherited") is True:
            inherited_marker = True
    if turn is not None or step is not None:
        raise ExportError("session has an unfinished turn; stop it before export")
    if header["isSeeded"] != inherited_marker:
        raise ExportError("v4 session seed header and inherited boundary disagree")


def _hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def safe_relative(value: Any) -> str:
    path = validate_archive_path(value)
    forbidden = {"node_modules", "cache", "logs", "tmp", "temp", ".git", ".dsh-pack"}
    for part in path.split("/"):
        if (part.casefold() in forbidden or part.endswith((" ", "."))
                or ":" in part or any(ord(c) < 32 for c in part)
                or re.fullmatch(r"(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?", part)):
            raise ExportError("unsafe portable data path")
    return path


def _inside(root: Path, relative: str) -> Path:
    path = root / safe_relative(relative)
    current = path
    while current != root:
        if current.is_symlink() or (hasattr(current, "is_junction") and current.is_junction()):
            raise ExportError("portable data may not traverse symbolic links or junctions")
        current = current.parent
    if not path.resolve().is_relative_to(root.resolve()):
        raise ExportError("portable data escapes its root")
    return path


def source_home(profile: Path) -> Path:
    profile = profile.resolve()
    if profile.parent.name != "profiles":
        raise ExportError("selected Home data requires DSH_HOME/profiles/<name>")
    return profile.parent.parent


def assert_private_values_absent(content: bytes, label: str) -> None:
    """Refuse recognizable credentials; no secret value is included in errors."""
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ExportError(f"unsupported non-text data requires a dedicated adapter: {label}") from error
    if _SECRET_TEXT.search(text):
        raise ExportError(f"credential-like content detected: {label}")
    values = []
    try:
        values.append(json.loads(text))
    except json.JSONDecodeError:
        for line in text.splitlines():
            try:
                values.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    def check(value):
        if isinstance(value, dict):
            for key, child in value.items():
                normalized = re.sub(r"(?<=[a-z])(?=[A-Z])", "_", key)
                if (_SECRET_KEY.match(normalized) and isinstance(child, str)
                        and child and not _PLACEHOLDER.fullmatch(child)):
                    raise ExportError(f"credential field detected: {label}")
                check(child)
        elif isinstance(value, list):
            for child in value:
                check(child)
    for value in values:
        check(value)


def _logical_session(content: bytes, path: str) -> bytes:
    if not path.endswith(".zstd"):
        return content
    try:
        from compression import zstd
    except ImportError as error:
        raise ExportError("Zstandard inspection requires Python 3.14; compressed data was not exported") from error
    import io
    try:
        with zstd.ZstdFile(io.BytesIO(content), "rb") as reader:
            decoded = reader.read(MAX_DATA_BYTES + 1)
    except (zstd.ZstdError, EOFError, OSError) as error:
        raise ExportError("invalid compressed session") from error
    if len(decoded) > MAX_DATA_BYTES:
        raise ExportError("session exceeds the logical data size limit")
    return decoded


def _validate_data(content: bytes, item: Mapping[str, Any]) -> None:
    path, kind = item["path"], item["kind"]
    parts = path.split("/")
    if kind == "conversation":
        generation = _session_generation(parts[-1])
        if len(parts) != 4 or parts[0] != "sessions" or generation is None:
            raise ExportError("unsupported session layout; select a project/session transcript")
        logical = _logical_session(content, path)
        assert_private_values_absent(logical, path)
        try:
            rows = [json.loads(line) for line in logical.decode("utf-8").splitlines()]
        except (ValueError, UnicodeDecodeError) as error:
            raise ExportError("invalid JSONL session") from error
        if not rows or not isinstance(rows[0], dict):
            raise ExportError("session header missing")
        header = rows[0]
        if (header.get("type") != "session" or type(header.get("version")) is not int or header["version"] != generation
                or not isinstance(header.get("id"), str) or not header["id"]
                or type(header.get("createdAt")) is not int
                or type(header.get("delegationDepth")) is not int
                or header["delegationDepth"] < 0):
            raise ExportError("unsupported session header; a matching DSH adapter is required")
        if generation == 4:
            if not logical.endswith(b"\n"):
                raise ExportError("v4 session has an incomplete JSONL record; stop its writer before export")
            _validate_v4_session(header, rows[1:])
            return
        if len(rows) < 2 or not isinstance(rows[-1], dict) or rows[-1].get("type") != "turn/end":
            raise ExportError("session has no completed turn; stop it before export")
    else:
        if len(parts) != 2 or parts[0] != "storages" or not parts[1].endswith(".json"):
            raise ExportError("only explicitly owned JSON storage units are supported")
        assert_private_values_absent(content, path)
        try:
            value = json.loads(content)
        except ValueError as error:
            raise ExportError("plugin data must be valid JSON") from error
        if not isinstance(value, dict):
            raise ExportError("plugin storage unit must be a JSON object")


def discover(profile: Path) -> list[dict[str, Any]]:
    home = source_home(profile)
    result = []
    for root_name in ("sessions", "storages"):
        root = home / root_name
        if not root.exists():
            continue
        _inside(home, root_name)
        for directory, dirs, files in os.walk(root, followlinks=False):
            dirs[:] = [d for d in dirs if not (Path(directory)/d).is_symlink()
                       and not (hasattr(Path(directory)/d, "is_junction") and (Path(directory)/d).is_junction())]
            for name in sorted(files):
                relative = (Path(directory)/name).relative_to(home).as_posix()
                try:
                    path = _inside(home, relative)
                except ExportError:
                    continue
                session = root_name == "sessions" and _session_generation(name) is not None and len(relative.split("/")) == 4
                session_candidate = (root_name == "sessions" and len(relative.split("/")) == 4
                                     and re.fullmatch(r"session(?:\.v[1-9][0-9]*)?\.jsonl(?:\.zstd)?", name) is not None)
                unit = root_name == "storages" and len(relative.split("/")) == 2 and name.endswith(".json")
                result.append({
                    "path": relative, "kind": "conversation" if session_candidate else "plugin-data",
                    "classification": "excluded" if session else "unsupported",
                    "selectable": session or unit,
                    "reason": ("not selected" if session else
                               "unsupported session generation; a matching DSH adapter is required" if session_candidate else
                               "explicit plugin ownership and storage contract required"),
                    "bytes": path.stat().st_size,
                })
                if len(result) > 2000:
                    raise ExportError("data inventory is too large; use a dedicated adapter")
    return sorted(result, key=lambda row: row["path"])


def collect(profile: Path, selection: Sequence[Mapping[str, Any]], owners: set[str]):
    files: dict[str, bytes] = {}
    items = []
    if not selection:
        return files, items
    home = source_home(profile)
    total = 0
    seen = set()
    for raw in selection:
        if not isinstance(raw, dict) or set(raw) != {"path", "kind", "owner"}:
            raise ExportError("data selections require exactly path, kind and owner")
        path = safe_relative(raw["path"])
        kind, owner = raw["kind"], raw["owner"]
        if not isinstance(kind, str) or kind not in KINDS or not isinstance(owner, str):
            raise ExportError("invalid portable data selection")
        if kind == "conversation":
            if owner != "@deepseek-ai/dsh-session-persistence-jsonl":
                raise ExportError("conversation selection requires the official JSONL backend")
        elif owner not in owners:
            raise ExportError("selected storage owner is absent from the Profile")
        if path.casefold() in seen:
            raise ExportError("duplicate portable data path")
        seen.add(path.casefold())
        source = _inside(home, path)
        before = source.stat()
        if not source.is_file() or before.st_size > MAX_DATA_BYTES:
            raise ExportError("unsupported data file or size")
        with source.open("rb") as stream:
            content = stream.read(MAX_DATA_BYTES + 1)
        after = source.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ExportError("selected data changed during export; stop its writer and retry")
        total += len(content)
        if len(content) > MAX_DATA_BYTES or total > MAX_TOTAL_BYTES:
            raise ExportError("selected data exceeds the export size limit")
        _validate_data(content, raw)
        item = {**raw, "classification": "portable", "bytes": len(content), "sha256": _hash(content)}
        files[path] = content
        items.append(item)
    return files, items


def validate_inventory(manifest: Mapping[str, Any], files: Mapping[str, bytes], plugins_lock: Mapping[str, Any] | None = None) -> None:
    inventory = manifest.get("dataInventory", [])
    if not isinstance(inventory, list):
        raise SchemaValidationError("dataInventory must be an array")
    selected = {}
    raw_plugins = (plugins_lock or {}).get("plugins", [])
    owners = {row["name"] for row in raw_plugins if isinstance(row, dict) and isinstance(row.get("name"), str)} if isinstance(raw_plugins, list) else set()
    if len(inventory) > 4000:
        raise SchemaValidationError("data inventory exceeds its entry limit")
    for item in inventory:
        if not isinstance(item, dict) or not isinstance(item.get("classification"), str) or item["classification"] not in CLASSES:
            raise SchemaValidationError("invalid data inventory entry")
        if item["classification"] != "portable":
            continue
        if set(item) != {"path", "kind", "owner", "classification", "bytes", "sha256"}:
            raise SchemaValidationError("invalid portable inventory fields")
        path = safe_relative(item["path"])
        if not isinstance(item["kind"], str) or item["kind"] not in KINDS or not isinstance(item["owner"], str) or not item["owner"]:
            raise SchemaValidationError("invalid portable data owner or kind")
        if item["kind"] != "conversation" and plugins_lock is not None and item["owner"] not in owners:
            raise SchemaValidationError("portable storage owner is absent from plugins.lock")
        if item["kind"] == "conversation" and item["owner"] != "@deepseek-ai/dsh-session-persistence-jsonl":
            raise SchemaValidationError("unsupported conversation owner")
        if path.casefold() in {p.casefold() for p in selected}:
            raise SchemaValidationError("duplicate portable inventory path")
        selected[path] = item
    if set(selected) != set(files):
        raise SchemaValidationError("portable data must exactly match its inventory")
    if files and manifest.get("schemaVersion") not in {2, 3}:
        raise SchemaValidationError("portable data requires schema version 2 or 3")
    if sum(len(content) for content in files.values()) > MAX_TOTAL_BYTES:
        raise SchemaValidationError("portable data exceeds its total size limit")
    for path, content in files.items():
        if len(content) > MAX_DATA_BYTES:
            raise SchemaValidationError("portable data exceeds its file size limit")
        item = selected[path]
        if type(item["bytes"]) is not int or item["bytes"] != len(content) or item["sha256"] != _hash(content):
            raise SchemaValidationError("portable data identity mismatch")
        _validate_data(content, item)


def check_targets(home: Path, files: Mapping[str, bytes], *, overwrite: bool = False) -> None:
    if files and overwrite:
        raise PackImportError("portable Home data requires a new Profile", stage="planning",
                              code="PORTABLE_DATA_OVERWRITE_FORBIDDEN")
    for path in files:
        try:
            target = _inside(home, path)
        except ExportError as error:
            raise PackImportError(str(error), stage="planning", code="PORTABLE_DATA_PATH_UNSAFE") from error
        if target.exists():
            raise PackImportError("portable data target already exists; use a fresh DSH_HOME",
                                  stage="planning", code="PORTABLE_DATA_EXISTS", details={
                                      "item": path,
                                      "suggestedNextStep": "请使用独立且全新的 DSH_HOME 恢复此包。会话和插件数据属于整个 Home；仅更换 Profile 名称无法避开现有数据。原 Home 不会被覆盖。",
                                  })


def restore_files(home: Path, files: Mapping[str, bytes], created: list[Path], directories: list[Path]) -> None:
    """Write absent files only; the importer owns rollback of this exact list."""
    for path, content in files.items():
        target = _inside(home, path)
        missing = []
        parent = target.parent
        while not parent.exists():
            missing.append(parent)
            parent = parent.parent
        for directory in reversed(missing):
            directory.mkdir(exist_ok=False)
            directories.append(directory)
        with target.open("xb") as stream:
            created.append(target)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())


def rollback_files(created: list[Path], directories: list[Path]) -> None:
    for path in reversed(created):
        path.unlink(missing_ok=True)
    for path in reversed(directories):
        try:
            path.rmdir()
        except FileNotFoundError:
            pass
