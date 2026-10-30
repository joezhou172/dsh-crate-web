"""Preview 发布契约与打包后检查；不安装依赖，不调用模型。"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import re
from release_guard import PACKAGE, inspect_tarball
ROOT = Path(__file__).resolve().parents[1]


def validate_metadata(pkg, ref_type="", ref_name=""):
    version = pkg.get("version", "")
    if pkg.get("name") != PACKAGE:
        raise ValueError("npm 包名与发布目标不符")
    if pkg.get("repository", {}).get("url") not in {
        "https://github.com/joezhou172/dsh-crate-web.git",
        "git+https://github.com/joezhou172/dsh-crate-web.git",
    }:
        raise ValueError("repository.url 必须对应现有 Trusted Publisher 的真实仓库")
    if not re.fullmatch(r"\d+\.\d+\.\d+-[0-9A-Za-z.-]+", version):
        raise ValueError("此工作流仅发布 Preview，版本必须带 prerelease 后缀")
    if pkg.get("publishConfig") != {"access": "public", "tag": "preview"}:
        raise ValueError("发布必须明确指定 public / preview")
    if ref_type == "tag" and ref_name != "v" + version:
        raise ValueError("Git 标签与 npm 版本不一致")
    return version


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--pack-report", type=Path)
    p.add_argument("--output", type=Path)
    p.add_argument("--github-output", type=Path)
    a = p.parse_args()
    pkg = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    version = validate_metadata(pkg, os.environ.get("RELEASE_REF_TYPE", ""), os.environ.get("RELEASE_REF_NAME", ""))
    core = ROOT / "core/dsh_pack"
    if not (core / "__main__.py").is_file():
        raise ValueError("发布仓库缺少权威 Core 源码")
    core_version = re.search(r'__version__\s*=\s*[\'"]([^\'"]+)', (core / "_version.py").read_text(encoding="utf-8"))
    compat = json.loads((ROOT / "skills/dsh-crate-troubleshooting/compatibility.json").read_text(encoding="utf-8"))
    if not core_version or core_version.group(1) != version or compat["skillVersion"] != version:
        raise ValueError("npm / Core / Skill 版本不一致")
    if a.pack_report:
        entries = json.loads(a.pack_report.read_text(encoding="utf-8"))
        if len(entries) != 1:
            raise ValueError("应当只有一个 npm 制品")
        filename = entries[0]["filename"]
        if Path(filename).name != filename or not filename.endswith(".tgz"):
            raise ValueError("npm 制品文件名非法")
        report = inspect_tarball(a.pack_report.parent / filename)
        if report["version"] != version or report["status"] != "PASS":
            print(json.dumps(report["findings"], ensure_ascii=False))
            raise ValueError("最终 npm 制品检查失败")
        report["filename"] = filename
        if a.output:
            a.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if a.github_output:
            with a.github_output.open("a", encoding="utf-8") as stream:
                stream.write("sha256=" + report["sha256"] + "\n")
        print(json.dumps({k: v for k, v in report.items() if k not in {"files", "findings"}}, ensure_ascii=False))
    else:
        print(json.dumps({"version": version, "distTag": "preview", "versionAlignment": "PASS"}))


if __name__ == "__main__":
    main()
