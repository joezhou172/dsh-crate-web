"""只新增不得用旧 Profile 文件覆盖刚验证的宿主内置组件。"""
import copy
import gzip
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'core'))
from test_size_preview import ENV, artifact
from dsh_pack.export import export_profile, ExportOptions
from dsh_pack.importer import ImportOptions
from dsh_pack.incremental import plan_incremental, execute_incremental
from dsh_pack.pack import read, sha256_bytes
from dsh_pack.snapshot import inventory
from dsh_pack.errors import PackImportError


def deterministic_artifact(*args, **kwargs):
    # 模拟 npm 可重复制品，避免 gzip 当前秒被误判为宿主内容变化。
    return gzip.compress(gzip.decompress(artifact(*args, **kwargs)),mtime=0)


class HostRetentionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.home = self.root/'home'
        self.target = self.home/'profiles/target'; self.target.mkdir(parents=True)
        self.name = '@deepseek-ai/dsh-web-app'
        self.modules = self.root/'host/node_modules'
        def package(root, name, version):
            folder = root/name; folder.mkdir(parents=True)
            (folder/'package.json').write_text(json.dumps({'name':name,'version':version,'dsh':{'bundle':{'patch':'./cordis.patch.yml'}}}))
            (folder/'cordis.patch.yml').write_text('- insert:\n  - id: '+name.replace('/','-')+'\n    name: '+name+'\n')
            (folder/'index.js').write_text('export default '+json.dumps(version))
            return folder
        host = package(self.modules,self.name,'0.2.2-rc.3')
        package(self.target/'node_modules',self.name,'0.2.2-rc.1')
        third = package(self.target/'node_modules','third-party','1.0.0')
        (third/'local-only.txt').write_text('keep exact third-party local patch')
        (self.target/'package.json').write_text(json.dumps({'name':'target','dependencies':{self.name:'0.2.2-rc.1','third-party':'1.0.0'},'dsh':{'profile':{'bundles':[self.name,'third-party']}}}))
        source = self.root/'source'; source.mkdir()
        package(source/'node_modules','third-party','2.0.0'); package(source/'node_modules','new-plugin','1.0.0')
        (source/'package.json').write_text(json.dumps({'name':'source','dependencies':{self.name:'0.2.2-rc.3','third-party':'2.0.0','new-plugin':'1.0.0'},'dsh':{'profile':{'bundles':[self.name,'third-party','new-plugin']}}}))
        self.env = copy.deepcopy(ENV); self.env['dsh']['version']='0.2.2-rc.3'
        files={p.name:sha256_bytes(p.read_bytes()) for p in host.iterdir()}
        self.host={self.name:{'manifest':json.loads((host/'package.json').read_bytes()),'files':files,'dependencies':{}}}
        self.options=ImportOptions(current_environment=self.env,host_bundles=self.host,allow_environment_difference=True)
        self.patches=[patch.dict('os.environ',{'DSH_PACK_RUNTIME_MODULES':str(self.modules)}),patch('dsh_pack.export._npm_command',return_value='fixture-npm'),patch('dsh_pack.export._npm_pack',side_effect=deterministic_artifact)]
        for p in self.patches:p.start();self.addCleanup(p.stop)
        self.source=export_profile(source,self.root/'source.dshcrate',options=ExportOptions(environment=self.env,export_mode='freeze')).path

    def test_add_keeps_third_party_but_uses_verified_host_after_commit(self):
        before=inventory(self.target); work=self.root/'plan'; work.mkdir()
        preview,path,_=plan_incremental(self.source,self.home,'target','add',self.options,work)
        web=next(r for r in read(path).plugins_lock['plugins'] if r['name']==self.name)
        self.assertEqual(web['runtime']['version'],'0.2.2-rc.3')
        self.assertEqual(inventory(self.target),before)
        run=self.root/'run';run.mkdir()
        result=execute_incremental(self.source,self.home,'target','add',self.options,preview['planToken'],run)
        actual=json.loads((self.target/'node_modules'/self.name/'package.json').read_bytes())
        self.assertEqual(actual['version'],'0.2.2-rc.3')
        self.assertEqual(json.loads((self.target/'node_modules/third-party/package.json').read_bytes())['version'],'1.0.0')
        self.assertEqual((self.target/'node_modules/third-party/local-only.txt').read_text(),'keep exact third-party local patch')
        self.assertTrue((self.target/'node_modules/new-plugin/package.json').is_file())
        changes=result['incremental']['hostRuntimeAdaptations']
        self.assertEqual([(c['name'],c['from'],c['to']) for c in changes],[(self.name,'0.2.2-rc.1','0.2.2-rc.3')])

    def test_invalid_host_evidence_blocks_without_changing_target(self):
        self.host[self.name]['files']['index.js']='0'*64
        before=inventory(self.target); work=self.root/'plan'; work.mkdir()
        with self.assertRaises(PackImportError) as raised:
            plan_incremental(self.source,self.home,'target','add',self.options,work)
        self.assertEqual(raised.exception.code,'HOST_BUNDLE_MISMATCH')
        self.assertEqual(inventory(self.target),before)

    def test_failed_commit_restores_old_host_and_third_party_files(self):
        before=inventory(self.target); work=self.root/'plan'; work.mkdir()
        preview,_,_=plan_incremental(self.source,self.home,'target','add',self.options,work)
        run=self.root/'run';run.mkdir()
        from dsh_pack.snapshot import Snapshot
        original=Snapshot.commit
        committed=[]
        def failing_commit(snapshot, prepared):
            if snapshot.target == self.target:
                original(snapshot,prepared)
                committed.append(json.loads((self.target/'node_modules'/self.name/'package.json').read_bytes())['version'])
                raise OSError('controlled post-profile-commit failure')
            return original(snapshot,prepared)
        with patch.object(Snapshot,'commit',failing_commit),self.assertRaises(PackImportError) as raised:
            execute_incremental(self.source,self.home,'target','add',self.options,preview['planToken'],run)
        diagnostic=raised.exception.as_dict()
        self.assertEqual(raised.exception.code,'IMPORT_ROLLED_BACK',diagnostic)
        self.assertEqual(raised.exception.details.get('originalError'),
                         'controlled post-profile-commit failure',diagnostic)
        self.assertEqual(inventory(self.target),before)
        self.assertEqual(committed,['0.2.2-rc.3'],diagnostic)

    def test_failure_before_swap_removes_owned_stage_and_allows_retry(self):
        before = inventory(self.target)
        neighbor = self.target.parent / ('crate-stage-' + '0' * 32)
        neighbor.mkdir()
        metadata = self.home / '.dsh-pack/imports'
        neighbor_metadata = metadata / neighbor.name
        neighbor_metadata.mkdir(parents=True)
        work = self.root / 'preview'; work.mkdir()
        preview, _, _ = plan_incremental(self.source, self.home, 'target', 'add', self.options, work)
        run = self.root / 'failure'; run.mkdir()
        with patch('dsh_pack.snapshot.Snapshot.commit', side_effect=OSError('before swap')), self.assertRaises(PackImportError):
            execute_incremental(self.source, self.home, 'target', 'add', self.options, preview['planToken'], run)
        self.assertEqual(inventory(self.target), before)
        self.assertEqual(set(self.target.parent.iterdir()), {self.target, neighbor})
        self.assertEqual(set(metadata.iterdir()), {neighbor_metadata})
        run = self.root / 'retry'; run.mkdir()
        execute_incremental(self.source, self.home, 'target', 'add', self.options, preview['planToken'], run)
        self.assertEqual(set(self.target.parent.iterdir()), {self.target, neighbor})
        self.assertEqual(set(metadata.iterdir()), {metadata / 'target', neighbor_metadata})


if __name__=='__main__':unittest.main()
