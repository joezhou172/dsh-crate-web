import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'core'))
from dsh_pack.maintenance import run
from dsh_pack.snapshot import Snapshot, inventory, save_json

class MaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.target = self.home / 'profiles/desktop'; self.target.mkdir(parents=True)
        (self.target/'config.json').write_text('original')
        self.directory = self.home/'.dsh-pack/maintenance/test'; self.directory.mkdir(parents=True)
        self.job = self.directory/'job.json'
        save_json(self.job, {'home':str(self.home), 'target':'desktop', 'args':['import',str(self.directory/'absent.dshcrate'),'--dsh-home',str(self.home),'--target-profile','desktop','--overwrite','--confirm-overwrite','--json']})
    def test_running_target_never_snapshots(self):
        (self.target/'lock').write_text('running')
        with self.assertRaisesRegex(ValueError,'运行锁'): run(self.job)
        self.assertFalse((self.home/'.dsh-pack/snapshots').exists())
    def test_failed_import_keeps_original_and_retains_snapshot(self):
        before=inventory(self.target)
        result=run(self.job)
        self.assertEqual(result['status'],'restored')
        self.assertTrue(result['restored'])
        self.assertEqual(inventory(self.target),before)
        self.assertTrue(Path(result['preSnapshot']).is_dir())
    def test_boot_failure_restores_committed_profile(self):
        before=inventory(self.target); saved=Snapshot(self.home,self.target)
        prepared=self.home/'profiles/prepared'; prepared.mkdir(); (prepared/'config.json').write_text('broken')
        saved.commit(prepared)
        save_json(self.directory/'result.json',{'status':'awaiting-boot','before':before,'result':{'snapshot':{'profile':str(saved.root)}}})
        self.assertEqual(run(self.job,rollback=True)['status'],'restored')
        self.assertEqual(inventory(self.target),before)
    def test_crash_after_commit_before_result_is_recovered(self):
        before=inventory(self.target); saved=Snapshot(self.home,self.target)
        prepared=self.home/'profiles/prepared'; prepared.mkdir(); (prepared/'config.json').write_text('new')
        saved.commit(prepared)
        save_json(saved.root/'transaction.json',{'status':'complete','target':'desktop','maintenanceJob':self.directory.name,'snapshots':[str(saved.root)]})
        save_json(self.directory/'result.json',{'status':'snapshot','before':before})
        self.assertTrue(run(self.job,rollback=True)['restored'])
        self.assertEqual(inventory(self.target),before)

if __name__=='__main__': unittest.main()
