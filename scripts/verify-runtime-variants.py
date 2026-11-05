"""在新目录验证本地候选，显式运行随包/系统 Python，不接触真实 DSH Home。"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--candidates',required=True,type=Path);parser.add_argument('--output',required=True,type=Path);parser.add_argument('--system-python',required=True,type=Path);parser.add_argument('--npm',required=True,type=Path)
    args=parser.parse_args()
    for field in ("candidates","output","system_python","npm"):setattr(args,field,getattr(args,field).resolve())
    args.output.mkdir(parents=True,exist_ok=False)
    manifest=json.loads((args.candidates/'manifest.json').read_text());results=[]
    for item in manifest['variants']:
        variant=item['variant']
        if variant not in {'full','compact','lite'} or Path(item['file']).name != item['file']:raise ValueError('invalid candidate manifest')
        archive_path=args.candidates/item['file']
        assert hashlib.sha256(archive_path.read_bytes()).hexdigest()==item['sha256']
        destination=args.output/variant;destination.mkdir()
        with tarfile.open(archive_path,'r:gz') as archive:archive.extractall(destination,filter='data')
        package=destination/'package';tests=package/'tests';tests.mkdir()
        for name in ('test_size_preview.py','test_release_export.py','test_release_adapter.py'):
            shutil.copyfile(ROOT/'tests'/name,tests/name)
        executable=args.system_python if variant=='lite' else package/'runtime'/'python'/'python.exe'
        environment={k:v for k,v in os.environ.items() if k not in {'PYTHONPATH','PYTHONHOME','DSH_HOME'}}
        # The self-contained candidates cannot discover a system Python via PATH.
        environment['PATH']=str(args.npm.parent)+os.pathsep+str(Path(os.environ['SystemRoot'])/'System32')
        environment['ComSpec']=str(Path(os.environ['SystemRoot'])/'System32'/'cmd.exe')
        report=destination/'probe.json'
        commands=[['-I',str(ROOT/'tests/runtime_variant_probe.py'),'--package',str(package),'--npm',str(args.npm),'--report',str(report)],['-I','-m','unittest','discover','-s',str(tests),'-v']]
        codes=[]
        for index,arguments in enumerate(commands):
            run=subprocess.run([str(executable),*arguments],cwd=package,env=environment,capture_output=True,text=True,timeout=90)
            (destination/('run-'+str(index)+'.log')).write_text(run.stdout+'\n'+run.stderr,encoding='utf-8');codes.append(run.returncode)
        results.append({'variant':variant,'status':'PASS' if codes==[0,0] else 'FAIL','exitCodes':codes,'realDshBoot':'UNTESTED'})
    (args.output/'verification.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(results))
    return int(any(row['status']=='FAIL' for row in results))

if __name__=='__main__':raise SystemExit(main())
