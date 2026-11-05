"""发行候选边界与字节保留；不安装、不发布。"""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("runtime_variants",ROOT/"scripts/build-runtime-variants.py")
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)


def source(path, extra=None):
    files={name:b"fixture" for name in builder.REQUIRED | builder.OMIT}
    files.update({"package/"+name:b"fixture" for name in ("lib/index.js","lib/client.js","core/dsh_pack/__main__.py","cordis.patch.yml")})
    files["package/package.json"]=json.dumps({"name":"dsh-crate-web","version":"0.1.2-preview.6","files":["runtime/python","core"]}).encode()
    with tarfile.open(path,"w:gz") as archive:
        for name,data in files.items():
            info=tarfile.TarInfo(name);info.size=len(data);archive.addfile(info,io.BytesIO(data))
        if extra:
            info,data=extra;info.size=len(data);archive.addfile(info,io.BytesIO(data))
    return files


class RuntimeVariantTests(unittest.TestCase):
    def test_variants_preserve_source_and_nonmanifest_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);original=root/"source.tgz";files=source(original);before=original.read_bytes()
            report=builder.build_variants(original,root/"out")
            self.assertEqual(original.read_bytes(),before)
            for row in report["variants"]:
                with tarfile.open(root/"out"/row["file"]) as archive:
                    entries={m.name:archive.extractfile(m).read() for m in archive}
                self.assertTrue(json.loads(entries["package/package.json"])["private"])
                removed={x["path"] for x in row["removed"]}
                self.assertEqual(set(entries),set(files)-removed)
                for name,value in entries.items():
                    if name!="package/package.json":self.assertEqual(value,files[name])
                if row["variant"]=="compact":self.assertEqual(removed,builder.OMIT)
                if row["variant"]=="lite":self.assertFalse(any(n.startswith(builder.RUNTIME) for n in entries))
            second=builder.build_variants(original,root/"again")
            self.assertEqual([r["sha256"] for r in report["variants"]],[r["sha256"] for r in second["variants"]])

    def test_existing_output_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);original=root/"source.tgz";source(original)
            out=root/"out";out.mkdir();(out/"keep").write_text("keep")
            with self.assertRaises(ValueError):builder.build_variants(original,out)
            self.assertEqual((out/"keep").read_text(),"keep")

    def test_unsafe_duplicate_and_link_inputs_rejected(self):
        for name,kind in [("package/../escape",tarfile.REGTYPE),("package/lib/index.js",tarfile.REGTYPE),
                          ("package/LIB/index.js",tarfile.REGTYPE),("package/link",tarfile.SYMTYPE),
                          ("package//alias",tarfile.REGTYPE),("package/C:bad",tarfile.REGTYPE)]:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root=Path(directory);info=tarfile.TarInfo(name);info.type=kind;info.linkname="outside"
                original=root/"source.tgz";source(original,(info,b""))
                with self.assertRaises(ValueError):builder.build_variants(original,root/"out")
                self.assertFalse((root/"out").exists())

    def test_unknown_runtime_layout_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);original=root/"source.tgz"
            with tarfile.open(original,"w:gz") as archive:
                info=tarfile.TarInfo("package/package.json");data=b'{"name":"dsh-crate-web"}';info.size=len(data);archive.addfile(info,io.BytesIO(data))
            with self.assertRaises(ValueError):builder.build_variants(original,root/"out")
            self.assertFalse((root/"out").exists())

if __name__=="__main__":unittest.main()
