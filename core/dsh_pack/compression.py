"""Versioned Zstd transport. Install artifacts remain deterministic npm tgz files."""
from __future__ import annotations
import gzip
import hashlib
import io
import os
from pathlib import Path
import subprocess
import sys
from .errors import PackFormatError, IntegrityError

MAX_FILE = 128 * 1024 * 1024
MAX_TOTAL = 512 * 1024 * 1024
MODES = {"fast": 9, "compact": 19}

def digest(value):
    return hashlib.sha256(value).hexdigest()

def _bundled_compressor():
    if sys.platform == "win32":
        runtime = Path(__file__).resolve().parents[2] / "runtime/python/python.exe"
        if runtime.is_file() and not runtime.samefile(sys.executable):
            return runtime
    return None

def _install_gzip(raw, runtime=None):
    if runtime is None:
        return gzip.compress(raw, compresslevel=6, mtime=0)
    # zlib and zlib-ng need not produce identical DEFLATE streams. Use only
    # the package's own runtime; pack data crosses this boundary as stdin.
    command = "import gzip, sys; sys.stdout.buffer.write(gzip.compress(sys.stdin.buffer.read(), compresslevel=6, mtime=0))"
    try:
        return subprocess.run(
            [str(runtime), "-I", "-S", "-B", "-c", command], input=raw,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=True,
            env={k: v for k, v in os.environ.items() if k.upper() == "SYSTEMROOT"},
            cwd=runtime.parent, timeout=120, creationflags=subprocess.CREATE_NO_WINDOW,
        ).stdout
    except (OSError, subprocess.SubprocessError) as error:
        raise PackFormatError("bundled gzip compressor could not reconstruct install artifact") from error

def zstd_module():
    try:
        from compression import zstd
        return zstd
    except ImportError as error:
        raise PackFormatError("Zstd requires Python 3.14 with compression.zstd; upgrade the Crate runtime") from error

def validate_transport(value):
    if not isinstance(value, dict) or set(value) != {"codec", "mode", "artifacts"}:
        raise PackFormatError("invalid transport declaration")
    if value["codec"] != "zstd-tar-v1" or not isinstance(value["mode"], str) or value["mode"] not in MODES:
        raise PackFormatError("unsupported transport codec or mode")
    if not isinstance(value["artifacts"], dict):
        raise PackFormatError("invalid transport artifacts")
    from .validation import validate_archive_path
    seen = set()
    total = 0
    for logical, row in value["artifacts"].items():
        validate_archive_path(logical, expected_root="plugins")
        if not isinstance(row, dict) or set(row) != {"path", "sourceSha256", "tarSha256", "tarBytes", "transportSha256", "transportBytes", "installSha256"}:
            raise PackFormatError("invalid transport artifact identity")
        validate_archive_path(row["path"], expected_root="plugins")
        if row["path"].casefold() in seen:
            raise PackFormatError("duplicate transport path")
        seen.add(row["path"].casefold())
        for key in ("sourceSha256", "tarSha256", "transportSha256", "installSha256"):
            import re
            if not isinstance(row[key], str) or not re.fullmatch("[0-9a-f]{64}", row[key]):
                raise PackFormatError("invalid transport hash")
        for key in ("tarBytes", "transportBytes"):
            if type(row[key]) is not int or not 0 < row[key] <= MAX_FILE:
                raise PackFormatError("transport resource limit exceeded")
        total += row["tarBytes"]
    if total > MAX_TOTAL:
        raise PackFormatError("transport total resource limit exceeded")

def encode(artifacts, lock, mode):
    if mode not in MODES:
        raise PackFormatError("unsupported compression mode")
    zstd = zstd_module()
    entries, rows = {}, {}
    total = 0
    for name, source in artifacts.items():
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(source)) as stream:
                raw = stream.read(MAX_FILE + 1)
        except (OSError, EOFError) as error:
            raise PackFormatError("invalid npm gzip artifact") from error
        total += len(raw)
        if len(raw) > MAX_FILE or total > MAX_TOTAL:
            raise PackFormatError("artifact resource limit exceeded")
        install = _install_gzip(raw, _bundled_compressor())
        encoded = zstd.compress(raw, level=MODES[mode])
        logical = "plugins/" + name
        path = logical + ".tar.zst"
        entries[path] = encoded
        rows[logical] = {"path": path, "sourceSha256": digest(source),
                         "tarSha256": digest(raw), "tarBytes": len(raw),
                         "transportSha256": digest(encoded), "transportBytes": len(encoded),
                         "installSha256": digest(install)}
        for plugin in lock["plugins"]:
            if plugin["artifact"].get("path") == logical:
                plugin["artifact"]["sha256"] = digest(install)
    transport = {"codec": "zstd-tar-v1", "mode": mode, "artifacts": rows}
    validate_transport(transport)
    return entries, transport

def decode(entries, transport, lock):
    validate_transport(transport)
    zstd = zstd_module()
    rows = transport["artifacts"]
    expected = {p["artifact"]["path"]: p["artifact"]["sha256"] for p in lock["plugins"] if p["artifact"]["mode"] == "embedded"}
    if set(rows) != set(expected):
        raise PackFormatError("transport and plugin lock disagree")
    if {k for k in entries if k.startswith("plugins/")} != {r["path"] for r in rows.values()}:
        raise PackFormatError("unexpected or missing transport artifact")
    result = {}
    for logical, row in rows.items():
        encoded = entries[row["path"]]
        if len(encoded) != row["transportBytes"] or digest(encoded) != row["transportSha256"]:
            raise IntegrityError("transport identity mismatch: " + logical)
        try:
            decoder = zstd.ZstdDecompressor(options={zstd.DecompressionParameter.window_log_max: 27})
            raw = decoder.decompress(encoded, max_length=row["tarBytes"] + 1)
            if not decoder.eof or decoder.unused_data or len(raw) != row["tarBytes"]:
                raise PackFormatError("truncated, concatenated or oversized Zstd frame: " + logical)
        except zstd.ZstdError as error:
            raise PackFormatError("invalid Zstd artifact: " + logical) from error
        if digest(raw) != row["tarSha256"]:
            raise IntegrityError("tar identity mismatch: " + logical)
        if row["installSha256"] != expected[logical]:
            raise IntegrityError("install identity mismatch: " + logical)
        install = _install_gzip(raw)
        if digest(install) != expected[logical]:
            runtime = _bundled_compressor()
            if runtime is None:
                raise IntegrityError("install identity mismatch: " + logical)
            install = _install_gzip(raw, runtime)
            if digest(install) != expected[logical]:
                raise IntegrityError("install identity mismatch: " + logical)
        result[logical[len("plugins/"):]] = install
    return result
