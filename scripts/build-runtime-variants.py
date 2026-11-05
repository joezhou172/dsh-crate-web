"""生成本地发行候选；不下载、不发布、不改输入包或原始运行时。"""
from __future__ import annotations
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import tarfile

RUNTIME = "package/runtime/python/"
OMIT = frozenset({RUNTIME + "_sqlite3.pyd", RUNTIME + "sqlite3.dll"})
REQUIRED = {RUNTIME + name for name in ("python.exe", "python314.dll", "python314.zip", "python314._pth", "LICENSE.txt", "_ssl.pyd", "libssl-3.dll", "libcrypto-3.dll", "_ctypes.pyd", "libffi-8.dll")}
MAX_BYTES = 150 * 1024 * 1024


def load_source(source: Path):
    payloads = {}
    modes = {}
    total = 0
    seen = set()
    with tarfile.open(source, "r:gz") as archive:
        for member in archive:
            path = PurePosixPath(member.name)
            if (not member.name.startswith("package/") or "\\" in member.name or ":" in member.name
                    or any(part in {".", "..", ""} for part in member.name.rstrip("/").split("/")) or path.is_absolute()):
                raise ValueError("unsafe package member path")
            if member.name.rstrip("/").casefold() in seen:
                raise ValueError("duplicate or case-colliding package member")
            seen.add(member.name.rstrip("/").casefold())
            if member.isdir():
                continue
            if not member.isfile() or member.name in payloads:
                raise ValueError("non-regular or duplicate package member")
            total += member.size
            if member.size < 0 or total > MAX_BYTES or len(payloads) >= 10000:
                raise ValueError("package exceeds candidate builder limits")
            payloads[member.name] = archive.extractfile(member).read()
            modes[member.name] = member.mode & 0o777
    if REQUIRED - payloads.keys() or OMIT - payloads.keys():
        raise ValueError("expected complete Python 3.14 Windows runtime layout")
    package = json.loads(payloads["package/package.json"])
    if package.get("name") != "dsh-crate-web":
        raise ValueError("wrong source package")
    if package.get("dshCrateDistribution"):
        raise ValueError("source must be an original full package, not a variant")
    if not all("package/" + name in payloads for name in ("lib/index.js", "lib/client.js", "core/dsh_pack/__main__.py", "cordis.patch.yml")):
        raise ValueError("incomplete Crate package")
    return payloads, modes, package


def build_variants(source: Path, output: Path):
    source = source.resolve()
    if output.exists():
        raise ValueError("output directory must not already exist")
    payloads, modes, package = load_source(source)
    source_digest = hashlib.sha256(source.read_bytes()).hexdigest()
    # Exclusive directory creation prevents accidental replacement of a previous run.
    output.mkdir(parents=True, exist_ok=False)
    reports = []
    for variant in ("full", "compact", "lite"):
        removed = {name for name in payloads if (variant == "lite" and name.startswith(RUNTIME)) or (variant == "compact" and name in OMIT)}
        selected = {name: value for name, value in payloads.items() if name not in removed}
        manifest = dict(package)
        manifest["private"] = True
        manifest["dshCrateDistribution"] = {"variant":variant,"candidate":True,"sourceSha256":source_digest,
                                             "pythonRequirement":"external Python 3.14 tested" if variant == "lite" else "bundled Windows Python 3.14"}
        selected["package/package.json"] = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode()
        destination = output / ("dsh-crate-web-" + variant + "-candidate.tgz")
        with destination.open("xb") as file:
            with gzip.GzipFile(filename="", fileobj=file, mode="wb", mtime=0, compresslevel=9) as compressed:
                with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as archive:
                    for name, value in sorted(selected.items()):
                        entry = tarfile.TarInfo(name); entry.size = len(value); entry.mode = modes[name]
                        archive.addfile(entry, io.BytesIO(value))
        reports.append({"variant":variant,"file":destination.name,"bytes":destination.stat().st_size,
                        "sha256":hashlib.sha256(destination.read_bytes()).hexdigest(),
                        "removed":[{"path":name,"bytes":len(payloads[name]),"sha256":hashlib.sha256(payloads[name]).hexdigest()} for name in sorted(removed)],
                        "retained":[{"path":name,"bytes":len(value),"sha256":hashlib.sha256(value).hexdigest()} for name,value in sorted(selected.items())],
                        "changed":["package/package.json"],"runtimeVerification":"UNTESTED"})
    report = {"sourceSha256":source_digest,"sourceBytes":source.stat().st_size,"variants":reports}
    (output / "manifest.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source",required=True,type=Path)
    parser.add_argument("--output",required=True,type=Path)
    args=parser.parse_args()
    report=build_variants(args.source,args.output)
    print(json.dumps({"sourceBytes":report["sourceBytes"],"variants":[{k:v for k,v in row.items() if k in {"variant","file","bytes","runtimeVerification"}} for row in report["variants"]]},ensure_ascii=False))

if __name__ == "__main__": main()
