"""配套补丁工具包入口；不搜索或自动选择用户安装。"""
import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path

def running(target):
    shell=Path(os.environ.get('SystemRoot',r'C:\Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'
    query="$ErrorActionPreference='Stop'; @(Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -eq $env:CRATE_PATCH_EXE }).Count"
    result=subprocess.run([str(shell),'-NoProfile','-NonInteractive','-Command',query],env=dict(os.environ,CRATE_PATCH_EXE=str(target/'DeepSeek Harness.exe')),capture_output=True,text=True,creationflags=subprocess.CREATE_NO_WINDOW,timeout=30)
    if result.returncode:raise RuntimeError('无法确认目标进程状态，未修改程序')
    return int(result.stdout.strip())>0

def wait_for_exit(target,timeout):
    deadline=time.monotonic()+timeout
    while running(target):
        if time.monotonic()>=deadline:raise RuntimeError('等待正常退出超时，未创建快照、未修改程序，也未强制结束进程')
        time.sleep(1)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['apply','restore'])
    parser.add_argument('--root',type=Path)
    parser.add_argument('--yes',action='store_true')
    parser.add_argument('--wait-for-exit',action='store_true',help='确认等待正常退出；不会强制结束进程')
    parser.add_argument('--wait-timeout',type=int,default=120)
    parser.add_argument('--restart',action='store_true',help='操作完成后启动此 Desktop')
    args=parser.parse_args()
    target=args.root
    if target is None:
        print('仅支持已核对版本及哈希的 Windows DSH；运行中会先确认正常退出。')
        target=Path(input('粘贴 DeepSeek Harness.exe 的完整路径（或安装文件夹）：\n').strip().strip('"'))
    if target.suffix.lower()=='.exe': target=target.parent
    target=target.absolute()
    for p in [target,*target.parents]:
        if p.is_symlink() or p.is_junction():raise RuntimeError('拒绝链接安装目录')
    target=target.resolve(strict=True)
    print(('恢复官方程序：' if args.action=='restore' else '应用桌面启动补丁：')+str(target))
    print('仅修改该安装的 app.asar；不复制或覆盖你的环境、会话或凭据。')
    if not args.yes and input('确认请输入 YES，其他输入取消：').strip()!='YES':
        print('已取消，未修改。');return 0
    spec=importlib.util.spec_from_file_location('crate_desktop_patcher',Path(__file__).with_name('desktop-profile-patch.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    if running(target):
        if not args.wait_for_exit:
            if args.yes:raise RuntimeError('目标正在运行；请明确使用 --wait-for-exit，或交互确认正常退出')
            if input('当前无法在线保证补丁一致性。确认正常关闭后快照请输入 YES，其他输入取消：').strip()!='YES':
                print('已取消，未修改。');return 0
        print('请在 DSH 菜单中选择退出（只点窗口叉可能仍在托盘运行）。等待退出后才快照；不会强制结束。',flush=True)
        wait_for_exit(target,args.wait_timeout)
    archive=target/'resources/app.asar'; receipt=target/'resources/crate-profile-patch.json'
    for p in [archive.parent,archive,receipt,target/'.crate-patch-snapshots']:
        if p.is_symlink() or p.is_junction():raise RuntimeError('拒绝链接补丁文件')
    current=module.digest(archive)
    prior=json.loads(receipt.read_text(encoding='utf-8')) if receipt.exists() else None
    original = module.SUPPORTED_BUILDS.get(prior.get('version')) if prior else None
    if current not in module.SUPPORTED_BUILDS.values() and (not original or prior.get('originalSha256')!=original or current!=prior.get('patchedSha256') or module.digest(target/'resources/app.asar.crate-original')!=original):
        raise RuntimeError('未知程序版本或补丁状态，未修改')
    snapshot=target/'.crate-patch-snapshots'/uuid.uuid4().hex;snapshot.mkdir(parents=True)
    shutil.copy2(archive,snapshot/'app.asar')
    if receipt.exists():shutil.copy2(receipt,snapshot/'receipt.json')
    if module.digest(snapshot/'app.asar')!=current:raise RuntimeError('补丁快照校验失败，未修改')
    if running(target):raise RuntimeError('快照期间目标重新启动，未修改程序')
    try:
        if args.action=='apply' and current not in module.SUPPORTED_BUILDS.values():module.patch(target,True,installed=True,confirm=True)
        result=module.patch(target,args.action=='restore',installed=True,confirm=True)
    except Exception:
        if running(target):raise RuntimeError('补丁失败且目标重新运行，未冒险覆盖；快照保留于 '+str(snapshot))
        temp=archive.with_suffix('.asar.recovery');shutil.copy2(snapshot/'app.asar',temp);temp.replace(archive)
        if (snapshot/'receipt.json').exists():shutil.copy2(snapshot/'receipt.json',receipt)
        elif receipt.exists():receipt.rename(snapshot/'failed-receipt.json')
        raise
    result['snapshot']=str(snapshot)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    if args.restart:subprocess.Popen([str(target/'DeepSeek Harness.exe')],cwd=target)
    print('完成。可以重新打开 DSH，已有环境和界面状态保留。');return 0

if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as error:
        print('操作未完成：'+str(error));raise SystemExit(1)
