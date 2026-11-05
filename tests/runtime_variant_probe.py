"""隔离候选的真实文件工作流；不能当作真实 DSH 验收。"""
import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile

parser=argparse.ArgumentParser();parser.add_argument("--package",required=True,type=Path);parser.add_argument("--npm",required=True);parser.add_argument("--report",required=True,type=Path)
args=parser.parse_args();root=args.package.resolve();sys.path.insert(0,str(root/"core"))
from dsh_pack import export, importer, preflight, pack, size_preview
from dsh_pack.errors import PackImportError
checks={}
for module in (export,importer,preflight,pack,size_preview):
    assert Path(module.__file__).resolve().is_relative_to(root/"core")
checks["candidateCoreOnly"]="PASS"
import ssl, socket, ctypes, bz2, lzma, compression.zstd, zipfile
ssl.create_default_context();ctypes.WinDLL("kernel32",use_last_error=True)
with socket.socket() as server:
    server.bind(("127.0.0.1",0));server.listen(1)
    with socket.create_connection(server.getsockname(),timeout=3) as client:
        conn,_=server.accept()
        with conn:
            client.sendall(b"fixture");assert conn.recv(7)==b"fixture"
for codec in (bz2,lzma,compression.zstd):assert codec.decompress(codec.compress(b"controlled data"))==b"controlled data"
checks["sslContextSocketCtypesCodecs"]="PASS"
os.environ['ComSpec']=str(Path(os.environ['SystemRoot'])/'System32'/'cmd.exe')
os.environ['npm_config_offline']='true'
ENV={"schemaVersion":1,"os":{"name":"windows","version":"fixture","arch":"x64"},"node":{"version":"24.13.0"},"dsh":{"version":"unknown"}}
with tempfile.TemporaryDirectory(prefix="crate-runtime-probe-") as directory:
    home=Path(directory);os.environ['DSH_HOME']=str(home/'source-home')
    profile=home/'source-home'/'profiles'/'sample';plugin=profile/'node_modules'/'fixture-plugin';plugin.mkdir(parents=True)
    (profile/'package.json').write_text(json.dumps({"name":"sample","dependencies":{"fixture-plugin":"1.0.0"}}))
    (plugin/'package.json').write_text(json.dumps({"name":"fixture-plugin","version":"1.0.0","scripts":{"prepack":"node -e \"require('fs').writeFileSync('UNEXPECTED_SCRIPT','bad')\""}}))
    (plugin/'index.js').write_text('export default {}')
    before={str(p.relative_to(profile)):hashlib.sha256(p.read_bytes()).hexdigest() for p in profile.rglob('*') if p.is_file()}
    for mode in ('freeze','share'):
        options=export.ExportOptions(environment=ENV,npm_command=args.npm,export_mode=mode)
        result=export.export_profile(profile,home/(mode+'.dshcrate'),options=options)
        measured=size_preview.build_preview(profile,options=options)
        assert measured['sizePreview']['archiveBytes']==result.path.stat().st_size
        inspection=preflight.inspect_pack(result.path,context=preflight.PreflightContext(current_environment=ENV,available_plugins={'fixture-plugin':'1.0.0'},available_secrets=set()))
        assert inspection.status=='READY', inspection.as_dict()
        target=home/('target-'+mode)
        imported=importer.import_pack(result.path,target,options=importer.ImportOptions(current_environment=ENV,allow_network_reference_install=False,reference_plugin_sources={'fixture-plugin':plugin},available_secrets=set()))
        assert json.loads((imported.profile_path/'node_modules'/'fixture-plugin'/'package.json').read_text())['version']=='1.0.0'
        assert not (plugin/'UNEXPECTED_SCRIPT').exists()
        original={str(p.relative_to(imported.profile_path)):p.read_bytes() for p in imported.profile_path.rglob('*') if p.is_file()}
        try:importer.import_pack(result.path,target,options=importer.ImportOptions(current_environment=ENV,allow_network_reference_install=False,reference_plugin_sources={'fixture-plugin':plugin},available_secrets=set()))
        except PackImportError:pass
        else:raise AssertionError('duplicate target was accepted')
        assert original=={str(p.relative_to(imported.profile_path)):p.read_bytes() for p in imported.profile_path.rglob('*') if p.is_file()}
        checks[mode+'ExportPreviewInspectImportAndDuplicateRefusal']='PASS'
    after={str(p.relative_to(profile)):hashlib.sha256(p.read_bytes()).hexdigest() for p in profile.rglob('*') if p.is_file()}
    assert before==after
    checks['sourceUnchangedAndScriptsDisabled']='PASS'
    bad=home/'broken.dshcrate';bad.write_bytes(b'not a zip')
    assert preflight.inspect_pack(bad).status!='READY'
    checks['corruptArchiveRejected']='PASS'
report={"status":"PASS","python":sys.version,"executable":sys.executable,"checks":checks,"loadedNativeModules":sorted(name for name,module in sys.modules.items() if str(getattr(module,'__file__','')).endswith('.pyd')),"realDshBoot":"UNTESTED","modelRequests":0}
args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(checks))
