"""显式的 0.2.1-rc.5 -> 0.2.2-rc.1 官方 Bundle 制品适配。

源包永不改写；目标制品必须逐文件匹配宿主提供的哈希证据。
第三方插件保持原样，适配后的包仍走完整 Preflight / Import。
"""
from __future__ import annotations

import copy
import io
import gzip
import json
import tarfile
import tempfile
from contextlib import contextmanager
from pathlib import Path

from .errors import PackImportError
from .pack import create, read, sha256_bytes
from .validation import validate_archive_path

SUPPORTED = ("0.2.1-rc.5", "0.2.2-rc.1")


def _fail(message):
    raise PackImportError(message, stage="compatibility", code="HOST_ADAPTATION_BLOCKED")


def adapt_data(data, target_version, host_bundles, modules):
    source_version = data.manifest.get("environment", {}).get("dsh", {}).get("version")
    if source_version == target_version:
        return data, None
    if (source_version, target_version) != SUPPORTED:
        _fail(f"尚未支持此跨版本路径：{source_version} -> {target_version}")
    if not host_bundles or not modules:
        _fail("缺少目标 DSH 官方制品及文件校验证据")
    result = copy.deepcopy(data)
    manifest = json.loads(result.profile_files["package.json"])
    changes = []
    for row in result.plugins_lock["plugins"]:
        if row.get("runtime", {}).get("source") != "installation-anchor":
            continue
        name = row["name"]
        if not name.startswith("@deepseek-ai/"):
            _fail("不能自动替换非官方安装锚点插件")
        host = host_bundles.get(name, {})
        package = host.get("manifest", {})
        files = host.get("files", {})
        if package.get("name") != name or package.get("version") != target_version or not files:
            _fail(f"目标宿主没有对应的官方 Bundle：{name}")
        root = Path(modules).joinpath(*name.split("/"))
        payloads = {}
        for relative, expected in files.items():
            validate_archive_path(relative)
            path = root / relative
            if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
                _fail(f"官方制品路径不安全：{name}")
            content = path.read_bytes()
            if sha256_bytes(content) != expected:
                _fail(f"目标官方文件校验失败：{name}/{relative}")
            payloads[relative] = content
        if json.loads(payloads.get("package.json", b"{}")) != package:
            _fail(f"目标官方 manifest 不一致：{name}")
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w") as archive:
            for relative, content in sorted(payloads.items()):
                info = tarfile.TarInfo("package/" + relative)
                info.size = len(content)
                info.mode = 0o644
                archive.addfile(info, io.BytesIO(content))
        content = gzip.compress(buffer.getvalue(), mtime=0)
        old = row.get("artifact", {}).get("path", "")
        if old.startswith("plugins/"):
            result.plugin_artifacts.pop(old[len("plugins/"):], None)
        filename = name.replace("@", "").replace("/", "-") + "-" + target_version + ".tgz"
        result.plugin_artifacts[filename] = content
        row["artifact"] = {"mode": "embedded", "path": "plugins/" + filename, "sha256": sha256_bytes(content)}
        row["requested"] = {"sourceType": "registry", "specifier": target_version}
        row["resolved"] = {"version": "unknown", "locator": "unknown"}
        row["runtime"]["version"] = target_version
        if row.get("bundle", {}).get("enabled"):
            row["bundle"]["patch"] = package.get("dsh", {}).get("bundle", {}).get("patch")
        if name in manifest.get("dependencies", {}):
            manifest["dependencies"][name] = target_version
        changes.append({"name": name, "from": source_version, "to": target_version,
                        "source": "verified-target-installation", "sha256": sha256_bytes(content)})
    if not changes:
        _fail("源包没有可核验的官方 Bundle，不能仅改写版本要求")
    if any(isinstance(row.get('bundle', {}).get('patch'), list) for row in result.plugins_lock['plugins']):
        result.plugins_lock['schemaVersion'] = 2
        result.manifest['schemaVersion'] = max(3, result.manifest['schemaVersion'])
    result.profile_files["package.json"] = json.dumps(manifest, ensure_ascii=False).encode()
    result.manifest["environment"]["dsh"]["version"] = target_version
    for dep in result.manifest.get("completeness", {}).get("hostDependencies", []):
        if dep.get("name") == "DSH runtime":
            dep["version"] = target_version
    return result, {"from": source_version, "to": target_version, "changes": changes,
                    "thirdPartyPlugins": "unchanged", "runtimeVerification": "UNTESTED"}


@contextmanager
def adapted_pack(source, target_version, host_bundles, modules):
    data, report = adapt_data(read(source), target_version, host_bundles, modules)
    if report is None:
        yield str(source), None
        return
    with tempfile.TemporaryDirectory(prefix="dsh-crate-adapt-") as directory:
        path = create(data, Path(directory) / "adapted.dshcrate", compression="fast")
        report["sourceSha256"] = sha256_bytes(Path(source).read_bytes())
        report["adaptedSha256"] = sha256_bytes(path.read_bytes())
        yield str(path), report
