"""发布前检查：只输出位置和规则，不输出疑似凭据或文件内容。"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile
import zipfile

PACKAGE = "dsh-crate-web"
FIXTURES = {
    "SENSITIVE_FIXTURE_VALUE", "sensitive-fixture-value", "fixture-pass",
    "fixture-secret-value", "CRATE_VERIFY_NO_MODEL_REQUESTS",
}
TOKEN = re.compile(rb"(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{30,}|npm_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_-]{20,})")
PEM = re.compile(rb"-----BEGIN ([A-Z ]*PRIVATE KEY)-----\s*[A-Za-z0-9+/=\r\n]{64,}-----END \1-----")
ASSIGN = re.compile(rb'''(?i)(?:api[_-]?key|access[_-]?token|auth[_-]?token|password|client[_-]?secret)["']?\s*[:=]\s*["']([^"'\r\n]{12,})["']''')
BEARER = re.compile(rb"(?i)Bearer[ \t]+([A-Za-z0-9_./+=-]{24,})")
FORBIDDEN_PARTS = {"node_modules", "__pycache__", ".git", ".vibe-wise", ".understand-anything", "outputs", "work"}
WINDOWS_TERMINAL_ROOT = "packaging/windows-terminal/"
WINDOWS_TERMINAL_FILES = {WINDOWS_TERMINAL_ROOT + name for name in {
    "build.py", "manifest.json", "README.md",
    "dsh__node_modules__@deepseek-ai__dsh-sandbox-local__lib__index.js.patch",
    "dsh__node_modules__@deepseek-ai__dsh-subprocess-local__lib__index.js.patch",
    "dsh__node_modules__@deepseek-ai__dsh-terminal-bash__lib__index.js.patch",
    "dsh__node_modules__node-pty__lib__windowsPtyAgent.js.patch",
    "dsh__node_modules__node-pty__lib__windowsTerminal.js.patch",
}}


def inspect_windows_terminal_assets(payloads):
    findings = [{"path": path, "rule": "missing-required-file"}
                for path in sorted(WINDOWS_TERMINAL_FILES - payloads.keys())]
    path = WINDOWS_TERMINAL_ROOT + "manifest.json"
    if path not in payloads:
        return findings
    try:
        manifest = json.loads(payloads[path])
        if manifest["schemaVersion"] != 1:
            raise ValueError("unsupported schema")
        expected = {name for name in WINDOWS_TERMINAL_FILES if name.endswith(".patch")}
        seen = set()
        for row in manifest["patches"]:
            name = WINDOWS_TERMINAL_ROOT + row["patch"]
            if name not in expected or name in seen:
                raise ValueError("unexpected patch")
            seen.add(name)
            if name in payloads and hashlib.sha256(payloads[name]).hexdigest() != row["patchSha256"]:
                findings.append({"path": name, "rule": "windows-terminal-patch-hash"})
        if seen != expected:
            raise ValueError("incomplete patch set")
    except (KeyError, TypeError, ValueError, UnicodeError):
        findings.append({"path": path, "rule": "windows-terminal-manifest"})
    return findings


def scan_blob(name: str, data: bytes, known_secrets=()):
    findings = []
    def add(rule, offset):
        findings.append({"path": name, "line": data.count(b"\n", 0, offset) + 1, "rule": rule})
    for rule, pattern in (("credential-token", TOKEN), ("private-key", PEM)):
        for match in pattern.finditer(data):
            add(rule, match.start())
    for rule, pattern in (("credential-literal", ASSIGN), ("bearer-literal", BEARER)):
        for match in pattern.finditer(data):
            value = match.group(1).decode("utf-8", errors="replace")
            if value in FIXTURES or value.startswith(("${", "{{")):
                continue
            entropy = -sum((value.count(c) / len(value)) * math.log2(value.count(c) / len(value)) for c in set(value))
            if (any(c.isdigit() for c in value) and any(c.isalpha() for c in value)
                    or len(value) >= 20 and entropy >= 3.5 and not any(c.isspace() for c in value)):
                add(rule, match.start())
    for secret in known_secrets:
        value = secret.encode() if isinstance(secret, str) else secret
        if len(value) >= 8 and value in data:
            add("known-local-credential", data.index(value))
    if name.endswith(".zip") or data.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                for entry in archive.infolist():
                    if not entry.is_dir():
                        findings.extend(scan_blob(name + "!" + entry.filename, archive.read(entry), known_secrets))
        except zipfile.BadZipFile:
            add("invalid-zip", 0)
    return findings


def environment_secrets():
    return [v for k, v in os.environ.items()
            if re.search(r"(?i)(?:api.?key|token|password|client.?secret)", k) and len(v) >= 8]


def scan_git(root: Path, revision=None, known_secrets=()):
    command = ["git", "ls-tree", "-rz", "--full-tree", revision] if revision else ["git", "ls-files", "-sz"]
    entries = subprocess.check_output(command, cwd=root).split(b"\0")
    findings, count, size = [], 0, 0
    cache = {}
    for entry in entries:
        if not entry:
            continue
        info, raw_name = entry.split(b"\t", 1)
        fields = info.split()
        mode, oid = fields[0], fields[2] if revision else fields[1]
        name = raw_name.decode("utf-8")
        if mode == b"160000":
            findings.append({"path": name, "rule": "unscanned-submodule"})
            continue
        if oid not in cache:
            cache[oid] = subprocess.check_output(["git", "cat-file", "blob", oid.decode()], cwd=root)
        data = cache[oid]
        findings.extend(scan_blob(name, data, known_secrets))
        count += 1
        size += len(data)
    return {"status": "FAIL" if findings else "PASS", "fileCount": count, "bytes": size, "findings": findings}


def inspect_tarball(path: Path, known_secrets=()):
    findings, files, payloads = [], [], {}
    with tarfile.open(path, "r:gz") as archive:
        for member in archive.getmembers():
            name = member.name
            p = PurePosixPath(name)
            if (not name.startswith("package/") or p.is_absolute() or ".." in p.parts
                    or "\\" in name or not (member.isfile() or member.isdir())):
                findings.append({"path": name, "rule": "unsafe-tar-member"})
                continue
            if not member.isfile():
                continue
            relative = name[len("package/"):]
            parts = PurePosixPath(relative).parts
            allowed = (relative in {"package.json", "README.md", "README.zh-CN.md", "LICENSE", "THIRD-PARTY-LICENSE.txt", "cordis.patch.yml",
                                      "restart-helper.mjs", "verify-desktop.mjs", "desktop-patch-helper.mjs", "runtime-inventory.mjs", "merge-config.mjs", "open-profile-runner.mjs"}
                       or relative in {"lib/index.js", "lib/client.js", "lib/index.d.ts", "lib/client.d.ts"}
                       or relative in WINDOWS_TERMINAL_FILES
                       or (relative.startswith("core/dsh_pack/") and relative.endswith(".py"))
                       or relative.startswith("runtime/python/")
                       or relative in {"skills/dsh-crate-troubleshooting/SKILL.md", "skills/dsh-crate-troubleshooting/compatibility.json"}
                       or (relative.startswith("skills/dsh-crate-troubleshooting/reference/") and relative.endswith(".md")))
            if (not allowed or any(part in FORBIDDEN_PARTS or part.startswith(".env") for part in parts)
                    or relative.endswith((".log", ".pyc", ".pyo", ".map", ".npmrc"))):
                findings.append({"path": relative, "rule": "unnecessary-package-file"})
            data = archive.extractfile(member).read()
            if relative in payloads:
                findings.append({"path": relative, "rule": "duplicate-package-file"})
            payloads[relative] = data
            files.append({"path": relative, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
            findings.extend(scan_blob(relative, data, known_secrets))
    required = {"package.json", "README.md", "cordis.patch.yml", "lib/index.js", "lib/client.js", "lib/index.d.ts",
                "core/dsh_pack/__main__.py", "core/dsh_pack/importer.py", "core/dsh_pack/verify.py",
                "restart-helper.mjs", "verify-desktop.mjs", "desktop-patch-helper.mjs", "runtime-inventory.mjs",
                "runtime/python/python.exe", "runtime/python/python314.zip", "runtime/python/python314._pth",
                "runtime/python/LICENSE.txt", "THIRD-PARTY-LICENSE.txt"}
    for missing in sorted(required - payloads.keys()):
        findings.append({"path": missing, "rule": "missing-required-file"})
    findings.extend(inspect_windows_terminal_assets(payloads))
    pkg = json.loads(payloads.get("package.json", b"{}"))
    if pkg.get("name") != PACKAGE or pkg.get("publishConfig", {}).get("tag") != "preview":
        findings.append({"path": "package.json", "rule": "unexpected-package-or-tag"})
    if not re.fullmatch(r"\d+\.\d+\.\d+-[0-9A-Za-z.-]+", pkg.get("version", "")):
        findings.append({"path": "package.json", "rule": "preview-version-required"})
    return {"status": "FAIL" if findings else "PASS", "package": pkg.get("name"), "version": pkg.get("version"),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "fileCount": len(files),
            "packedBytes": path.stat().st_size, "unpackedBytes": sum(x["bytes"] for x in files),
            "files": files, "findings": findings}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    git = sub.add_parser("git")
    git.add_argument("--root", type=Path, default=Path.cwd())
    git.add_argument("--revision")
    pack = sub.add_parser("tarball")
    pack.add_argument("path", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    secrets = environment_secrets()
    report = scan_git(args.root, args.revision, secrets) if args.action == "git" else inspect_tarball(args.path, secrets)
    if args.report:
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "files"}, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
