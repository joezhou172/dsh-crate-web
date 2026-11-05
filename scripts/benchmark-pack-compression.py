"""Controlled local benchmark. No install, publish, model call or source modification.
Run: python scripts/benchmark-pack-compression.py --output outputs/size-benchmark
"""
import argparse
import gzip
import hashlib
import io
import json
import platform
import statistics
import sys
import tarfile
import tempfile
import time
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))
from dsh_pack.export import ExportOptions, export_profile, _npm_command, _npm_pack
from dsh_pack.pack import read
from dsh_pack.size_preview import build_preview


def measure(source, out):
    with zipfile.ZipFile(source) as archive:
        entries = {name: archive.read(name) for name in archive.namelist()}
    methods = [("deflate-1", zipfile.ZIP_DEFLATED, 1), ("deflate-6", zipfile.ZIP_DEFLATED, 6),
               ("deflate-9", zipfile.ZIP_DEFLATED, 9), ("store-tgz", zipfile.ZIP_DEFLATED, 6),
               ("lzma", zipfile.ZIP_LZMA, None), ("bzip2-9", zipfile.ZIP_BZIP2, 9)]
    if hasattr(zipfile, "ZIP_ZSTANDARD"):
        methods += [("zstd-3", zipfile.ZIP_ZSTANDARD, 3), ("zstd-19", zipfile.ZIP_ZSTANDARD, 19)]
    rows = []
    for label, method, level in methods:
        encoded, decoded = [], []
        for _ in range(3):
            start = time.perf_counter()
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w", allowZip64=False) as archive:
                for name, content in entries.items():
                    info = zipfile.ZipInfo(name, (1980,1,1,0,0,0)); info.create_system = 0; info.external_attr = 0o600 << 16
                    compression = zipfile.ZIP_STORED if label == "store-tgz" and name.endswith(".tgz") else method
                    archive.writestr(info, content, compress_type=compression, compresslevel=level if compression != zipfile.ZIP_STORED else None)
            encoded.append(time.perf_counter() - start)
            start = time.perf_counter()
            with zipfile.ZipFile(io.BytesIO(buffer.getvalue())) as archive:
                assert entries == {name: archive.read(name) for name in archive.namelist()}
            decoded.append(time.perf_counter() - start)
        candidate = out / (source.stem + "-" + label + ".dshcrate")
        candidate.write_bytes(buffer.getvalue())
        read(candidate)  # Existing integrity and schema reader, not a DSH runtime verification.
        rows.append({"method":label,"bytes":len(buffer.getvalue()),"encodeMs":round(statistics.median(encoded)*1000,2),
                     "decodeMs":round(statistics.median(decoded)*1000,2),"byteEquality":"PASS","coreRead":"PASS"})
    groups = {}
    for name, content in entries.items():
        groups.setdefault(hashlib.sha256(content).hexdigest(), []).append(name)
    return {"sourceBytes":source.stat().st_size,"rows":rows,"identicalEntryGroups":[names for names in groups.values() if len(names)>1]}


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--output",type=Path,required=True); parser.add_argument("--artifact", type=Path, help="Existing locally packed npm artifact"); parser.add_argument("--pnpm-command", help="JSON argv for an existing local pnpm entry"); args=parser.parse_args()
    out = args.output.resolve(); out.mkdir(parents=True,exist_ok=True)
    artifact = args.artifact.read_bytes() if args.artifact else _npm_pack(ROOT, "dsh-crate-web", tuple(json.loads(args.pnpm_command)) if args.pnpm_command else _npm_command(None))
    (out / "local-package.tgz").write_bytes(artifact)
    with tarfile.open(fileobj=io.BytesIO(artifact),mode="r:gz") as archive:
        members = [(entry, archive.extractfile(entry).read()) for entry in archive if entry.isfile()]
    runtime = sum(len(data) for entry,data in members if entry.name.startswith("package/runtime/python/"))
    hypothetical = io.BytesIO()
    with tarfile.open(fileobj=hypothetical,mode="w:gz",compresslevel=9) as archive:
        for entry,data in members:
            if not entry.name.startswith("package/runtime/python/"):
                archive.addfile(entry,io.BytesIO(data))
    results = {"python":platform.python_version(),"os":platform.platform(),"iterations":3,
               "artifactBytes":len(artifact),"artifactSha256":hashlib.sha256(artifact).hexdigest(),
               "runtimeRawBytes":runtime,"packageRawBytes":sum(len(data) for _,data in members),
               "withoutRuntimeHypotheticalBytes":len(hypothetical.getvalue()),"samples":{}}
    with tempfile.TemporaryDirectory(prefix="crate-benchmark-") as directory:
        profile = Path(directory)/"profiles"/"sample"; package=profile/"node_modules"/"dsh-crate-web"; package.mkdir(parents=True)
        (profile/"package.json").write_text(json.dumps({"name":"sample","dependencies":{"dsh-crate-web":"0.1.2-preview.6"}}))
        for filename in ("package.json","cordis.patch.yml"):
            (package/filename).write_bytes((ROOT/filename).read_bytes())
        environment={"schemaVersion":1,"os":{"name":"Windows","version":"fixture","arch":"x64"},"node":{"version":"unknown"},"dsh":{"version":"unknown"}}
        with patch("dsh_pack.export._npm_pack",return_value=artifact):
            for mode in ("freeze","share"):
                options=ExportOptions(environment=environment,export_mode=mode)
                path=out/(mode+".dshcrate")
                export_profile(profile,path,options=options)
                preview=build_preview(profile,options=options)
                assert preview["sizePreview"]["archiveBytes"]==path.stat().st_size
                (out/(mode+"-preview.json")).write_text(json.dumps(preview,ensure_ascii=False,indent=2),encoding="utf-8")
                results["samples"][mode]=measure(path,out)
            # Controlled text-heavy configuration, never personal conversation data.
            (profile/"sample.txt").write_text("".join(json.dumps({"index":i,"message":"controlled repeated configuration text","digest":hashlib.sha256(str(i).encode()).hexdigest()})+"\n" for i in range(10000)))
            path=out/"text-heavy.dshcrate"
            export_profile(profile,path,options=ExportOptions(environment=environment,export_mode="share"))
            results["samples"]["text-heavy"]=measure(path,out)
    (out/"results.json").write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(results,ensure_ascii=False))

if __name__=="__main__": main()
