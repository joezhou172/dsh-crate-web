"""Inspector 适用条件与真实端点归属；静态检查不启动桌面。"""
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
import sys
from unittest.mock import Mock, patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'core'))
from dsh_pack.desktop_verify import DesktopVerifyAdapter

class InventoryTests(unittest.TestCase):
    def surface(self, inspector):
        adapter=object.__new__(DesktopVerifyAdapter)
        adapter.generation=1;adapter.process=Mock(pid=10);adapter.lock=threading.RLock()
        adapter.owned={10: None};adapter._bind=Mock()
        adapter.endpoints={'cdp-1':100,'web-1':101,'inspector-1':102}
        adapter._rpc=Mock(return_value={'webPort':101,'runtimePid':10,**({'inspector':inspector} if inspector is not None else {})})
        return adapter

    def test_absent_inspector_does_not_require_a_listener(self):
        adapter=self.surface({'inventoryComplete':True,'applicable':False,'reason':'not-declared'})
        with patch('dsh_pack.desktop_verify.process_tree',return_value={10}),patch('dsh_pack.desktop_verify.tcp_rows',return_value=[{'localPort':p,'state':'LISTEN','pid':10} for p in [100,101]]):
            evidence=adapter._surface()['endpoints']
        self.assertEqual(next(x for x in evidence if x['name']=='inspector-1')['status'],'NOT_APPLICABLE')

    def test_declared_inspector_missing_or_foreign_listener_still_fails(self):
        for foreign in [False,True]:
            adapter=self.surface({'inventoryComplete':True,'applicable':True,'reason':'enabled'})
            table=[{'localPort':p,'state':'LISTEN','pid':10} for p in [100,101]]
            if foreign:table.append({'localPort':102,'state':'LISTEN','pid':999})
            with self.subTest(foreign=foreign),patch('dsh_pack.desktop_verify.process_tree',return_value={10}),patch('dsh_pack.desktop_verify.tcp_rows',return_value=table):
                with self.assertRaisesRegex(RuntimeError,'listener not confirmed: inspector-1'):adapter._surface()

    def test_unknown_or_partial_inventory_cannot_skip_inspector(self):
        for value in [None,{}, {'inventoryComplete':False,'applicable':False},{'inventoryComplete':True,'applicable':None}]:
            adapter=self.surface(value)
            with self.subTest(value=value),patch('dsh_pack.desktop_verify.process_tree',return_value={10}),patch('dsh_pack.desktop_verify.tcp_rows',return_value=[]):
                with self.assertRaisesRegex(RuntimeError,'Inspector applicability not confirmed'):adapter._surface()

    def test_actual_source_and_shipped_api_inventory_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            subprocess.run(['node','--disable-warning=ExperimentalWarning','tests/runtime_inventory_contract.mjs',directory],cwd=ROOT,check=True,capture_output=True,text=True)

if __name__=='__main__':unittest.main()
