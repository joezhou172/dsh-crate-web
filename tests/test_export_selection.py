import copy
import gzip
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from test_size_preview import fixture, artifact, snapshot, ENV
from dsh_pack.export import ExportOptions, export_profile
from dsh_pack.pack import read, create
from dsh_pack.size_preview import build_preview
from dsh_pack.errors import DshPackError, ExportError
from dsh_pack.compression import decode

def row(name, included=True, version=None):
    return {"name": name, "included": included, "selection": {"kind": "registry", "version": version} if version else {"kind": "installed"},
            "artifactMode": "embedded", "activateOnImport": False}

class ExportSelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.profile = fixture(self.root)
        self.content = artifact(self.profile / "node_modules/fixture-plugin")
        self.npm = patch("dsh_pack.export._npm_command", return_value="fixture-npm"); self.npm.start(); self.addCleanup(self.npm.stop)
        self.pack = patch("dsh_pack.export._npm_pack", return_value=self.content); self.pack.start(); self.addCleanup(self.pack.stop)

    def test_both_codecs_restore_exact_tar_and_preview_is_frozen(self):
        before = snapshot(self.profile)
        for mode in ("fast", "compact"):
            path = self.root / (mode + ".dshcrate")
            options = ExportOptions(environment=ENV, selections=(row("fixture-plugin"),), compression=mode)
            preview = build_preview(self.profile, options=options, frozen_output=path)
            loaded = read(path)
            self.assertEqual(loaded.manifest["schemaVersion"], 4)
            self.assertEqual(preview["sizePreview"]["archiveBytes"], path.stat().st_size)
            self.assertFalse(preview["sizePreview"]["finalSizeMayChange"])
            self.assertEqual(gzip.decompress(next(iter(loaded.plugin_artifacts.values()))), gzip.decompress(self.content))
            # Reader output can be written again without corrupting identities.
            create(loaded, self.root / "reexport.dshcrate")
            read(self.root / "reexport.dshcrate")
        self.assertEqual(snapshot(self.profile), before)

    def test_exclusion_and_remote_only_addition_do_not_install(self):
        before = snapshot(self.profile)
        manifest = {"name": "new-plugin", "version": "2.0.0"}
        pkg = self.root / "remote"; pkg.mkdir()
        (pkg / "package.json").write_text(json.dumps(manifest))
        content = artifact(pkg)
        with patch("dsh_pack.export_selection.fetch", return_value=(manifest, content, "sha512-test", "https://registry.npmjs.org/new-plugin/-/new-plugin-2.0.0.tgz")):
            result = export_profile(self.profile, self.root / "selected.dshcrate", options=ExportOptions(
                environment=ENV, selections=(row("fixture-plugin", False), row("new-plugin", version="2.0.0")), compression="fast"))
        data = read(result.path)
        self.assertEqual([p["name"] for p in data.plugins_lock["plugins"]], ["new-plugin"])
        self.assertEqual(json.loads(data.profile_files["package.json"])["dependencies"], {"new-plugin": "2.0.0"})
        self.assertEqual(data.plugins_lock["plugins"][0]["runtime"]["version"], "unknown")
        self.assertEqual(snapshot(self.profile), before)

    def test_dependency_and_config_references_block_exclusion(self):
        other = self.profile / "node_modules/other"; other.mkdir()
        (other / "package.json").write_text(json.dumps({"name":"other","version":"1.0.0","dependencies":{"fixture-plugin":"1.0.0"}}))
        p = self.profile / "package.json"; value=json.loads(p.read_text()); value["dependencies"]["other"]="1.0.0"; p.write_text(json.dumps(value))
        options=ExportOptions(environment=ENV,selections=(row("fixture-plugin",False),row("other")))
        with self.assertRaisesRegex(ExportError,"requires excluded"):
            export_profile(self.profile,self.root/"bad.dshcrate",options=options)
        (self.profile/"cordis.patch.yml").write_text("name: fixture-plugin")
        with self.assertRaisesRegex(ExportError,"Configuration references"):
            export_profile(self.profile,self.root/"bad.dshcrate",options=options)

    def test_transport_corruption_and_resource_limits(self):
        path=self.root/"pack.dshcrate"
        export_profile(self.profile,path,options=ExportOptions(environment=ENV,export_mode="freeze",compression="fast"))
        with zipfile.ZipFile(path) as z: entries={n:z.read(n) for n in z.namelist()}
        manifest=json.loads(entries["manifest.json"]); lock=json.loads(entries["plugins.lock.json"])
        transport=manifest["transport"]
        for change in ("codec", "mode", "length", "hash", "truncated", "concatenated", "size"):
            t=copy.deepcopy(transport); e=dict(entries); record=next(iter(t["artifacts"].values()))
            if change=="codec": t["codec"]="unknown"
            elif change=="mode": t["mode"]=[]
            elif change=="length": record["tarBytes"]-=1
            elif change=="hash": record["tarSha256"]="0"*64
            elif change=="size": record["tarBytes"]=2**40
            else:
                import hashlib
                content=e[record["path"]]
                e[record["path"]]=content[:-3] if change=="truncated" else content+content
                record["transportBytes"]=len(e[record["path"]]); record["transportSha256"]=hashlib.sha256(e[record["path"]]).hexdigest()
            with self.subTest(change=change), self.assertRaises(DshPackError): decode(e,t,lock)

    def test_new_codec_preflight_uses_decoded_artifacts(self):
        from dsh_pack.preflight import inspect_pack, PreflightContext
        result=export_profile(self.profile,self.root/"new.dshcrate",options=ExportOptions(environment=ENV,export_mode="freeze",compression="fast"))
        pre=inspect_pack(result.path,context=PreflightContext(current_environment=ENV,available_secrets=set()))
        self.assertFalse(any(f.code == "REQUIRED_ARTIFACT_MISSING" for f in pre.findings))
        self.assertEqual(pre.status,"READY")

    def test_registry_integrity_mismatch_blocks_before_export(self):
        from dsh_pack.registry import fetch
        import base64
        metadata={"name":"fixture-plugin","version":"1.0.0","dist":{"integrity":"sha512-"+base64.b64encode(b"wrong").decode(),
                 "tarball":"https://registry.npmjs.org/fixture-plugin/-/fixture-plugin-1.0.0.tgz"}}
        def command(profile,args,npm=None):
            if args[0]=="view": return metadata
            Path(args[args.index("--pack-destination")+1],"fixture.tgz").write_bytes(self.content)
            return []
        with patch("dsh_pack.registry._run",side_effect=command):
            with self.assertRaisesRegex(ExportError,"integrity mismatch"):
                fetch(self.profile,"fixture-plugin","1.0.0")

    def test_missing_zstd_fails_without_final_file(self):
        with patch("dsh_pack.compression.zstd_module",side_effect=ExportError("Zstd unavailable")):
            with self.assertRaisesRegex(ExportError,"Zstd unavailable"):
                export_profile(self.profile,self.root/"missing.dshcrate",options=ExportOptions(environment=ENV,export_mode="freeze",compression="fast"))
        self.assertFalse((self.root/"missing.dshcrate").exists())

    def test_windows_commit_retries_only_bounded_sharing_failures(self):
        from dsh_pack.importer import _commit_prepared_profile
        from unittest.mock import Mock
        error=PermissionError("controlled Windows file hold")
        error.winerror=5
        source=Mock();target=Mock();target.exists.return_value=False
        source.rename.side_effect=[error,None]
        with patch("time.sleep"):
            _commit_prepared_profile(source,target)
        self.assertEqual(source.rename.call_count,2)
        source.reset_mock();source.rename.side_effect=error
        with patch("time.sleep"),self.assertRaises(PermissionError):
            _commit_prepared_profile(source,target)
        self.assertEqual(source.rename.call_count,5)
        source.reset_mock();target.exists.return_value=True
        with self.assertRaises(DshPackError):
            _commit_prepared_profile(source,target)
        source.rename.assert_not_called()

    def test_old_format_still_reads(self):
        result=export_profile(self.profile,self.root/"old.dshcrate",options=ExportOptions(environment=ENV,export_mode="freeze"))
        self.assertEqual(read(result.path).manifest["schemaVersion"],2)

if __name__ == "__main__": unittest.main()
