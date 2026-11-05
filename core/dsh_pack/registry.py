"""Read registry metadata and fetch exact artifacts without installing or running scripts."""
from __future__ import annotations
import base64
import hashlib
import io
import json
import os
import re
import subprocess
import tarfile
import tempfile
from pathlib import Path
from .errors import ExportError
from .compression import MAX_FILE

def package_name(name):
    if not isinstance(name, str) or len(name) > 214 or not re.fullmatch(r"(?:@[a-z0-9][a-z0-9._-]*/)?[a-z0-9][a-z0-9._-]*", name):
        raise ExportError("Invalid npm package name")
    return name

def exact_version(version):
    if not isinstance(version, str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?", version):
        raise ExportError("Select an exact published version")
    return version

def _run(profile, arguments, npm_command=None):
    from .export import _npm_command
    executable = _npm_command(npm_command)
    prefix = list(executable) if isinstance(executable, tuple) else [executable]
    if isinstance(executable, str) and executable.lower().endswith(".cmd"):
        root = Path(executable).parent
        cli = root / "node_modules/npm/bin/npm-cli.js"
        node = root / "node.exe"
        if cli.is_file() and node.is_file():
            prefix = [str(node), str(cli)]
    with tempfile.TemporaryDirectory(prefix="crate-registry-") as temp:
        command = [*prefix, *arguments, "--json"]
        if not isinstance(executable, tuple):
            command += ["--ignore-scripts", "--cache", temp]
        try:
            result = subprocess.run(command, cwd=profile, env=dict(os.environ, ELECTRON_RUN_AS_NODE="1",
                npm_config_ignore_scripts="true", npm_config_update_notifier="false"),
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120, check=False)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ExportError("Registry request failed or timed out; retry or keep installed content") from error
        # Never echo registry stderr: private URLs / tokens may occur in npm diagnostics.
        if result.returncode:
            raise ExportError("Registry request failed; check package, version, network and registry access")
        try:
            return json.loads(result.stdout)
        except ValueError as error:
            raise ExportError("Registry returned invalid JSON") from error

def versions(profile, name, npm_command=None):
    name = package_name(name)
    values = _run(profile, ["view", name, "versions"], npm_command)
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list) or len(values) > 50000:
        raise ExportError("Registry returned an invalid version list")
    return {"name": name, "versions": [exact_version(v) for v in values], "source": "configured-registry"}

def fetch(profile, name, version, npm_command=None):
    from .export import _validate_tarball
    package_name(name); exact_version(version)
    metadata = _run(profile, ["view", name + "@" + version], npm_command)
    if not isinstance(metadata, dict) or metadata.get("name") != name or metadata.get("version") != version:
        raise ExportError("Registry identity differs from selected package/version")
    from urllib.parse import urlsplit
    source_url = metadata.get("dist", {}).get("tarball", "")
    source = urlsplit(source_url)
    if source.scheme != "https" or not source.hostname or source.username or source.password or source.query or source.fragment:
        raise ExportError("Artifact source must be a portable HTTPS URL without credentials or query tokens")
    integrity = metadata.get("dist", {}).get("integrity")
    if not isinstance(integrity, str) or not integrity.startswith("sha512-"):
        raise ExportError("Registry artifact requires SHA-512 integrity")
    with tempfile.TemporaryDirectory(prefix="crate-download-") as temp:
        from .export import _npm_command
        if isinstance(_npm_command(npm_command), tuple):
            # pnpm does not implement npm pack <registry-spec>. Public HTTPS
            # artifacts can be fetched directly; private auth is not guessed.
            from urllib.request import urlopen
            from urllib.parse import urlsplit
            url = metadata.get("dist", {}).get("tarball", "")
            parsed = urlsplit(url)
            if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
                raise ExportError("Registry requires an HTTPS artifact URL without credentials")
            try:
                with urlopen(url, timeout=60) as response:
                    content = response.read(MAX_FILE + 1)
                if len(content) > MAX_FILE:
                    raise ExportError("Registry artifact exceeds size limit")
                (Path(temp) / "download.tgz").write_bytes(content)
            except OSError as error:
                raise ExportError("Cannot fetch registry artifact; private downloads require npm with configured access") from error
        else:
            _run(profile, ["pack", name + "@" + version, "--pack-destination", temp], npm_command)
        files = list(Path(temp).glob("*.tgz"))
        if len(files) != 1 or files[0].stat().st_size > MAX_FILE:
            raise ExportError("Registry artifact missing or exceeds size limit")
        content = files[0].read_bytes()
    if "sha512-" + base64.b64encode(hashlib.sha512(content).digest()).decode() not in integrity.split():
        raise ExportError("Registry artifact integrity mismatch")
    import gzip
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(content)) as stream:
            raw = stream.read(MAX_FILE + 1)
        if len(raw) > MAX_FILE:
            raise ExportError("Registry artifact expands beyond size limit")
    except (OSError, EOFError) as error:
        raise ExportError("Invalid registry gzip artifact") from error
    _validate_tarball(content, name)
    with tarfile.open(fileobj=io.BytesIO(content), mode="r:gz") as archive:
        seen = set()
        total = 0
        for member in archive:
            if member.name.casefold() in seen or not (member.isfile() or member.isdir()):
                raise ExportError("Registry artifact contains duplicate paths or links")
            seen.add(member.name.casefold())
            total += member.size
            if total > MAX_FILE:
                raise ExportError("Registry artifact expands beyond size limit")
        member = archive.getmember("package/package.json")
        if not member.isfile() or member.size > 2 * 1024 * 1024:
            raise ExportError("Invalid registry package manifest")
        manifest = json.loads(archive.extractfile(member).read())
    if manifest.get("name") != name or manifest.get("version") != version:
        raise ExportError("Downloaded package identity mismatch")
    return manifest, content, integrity, source_url
