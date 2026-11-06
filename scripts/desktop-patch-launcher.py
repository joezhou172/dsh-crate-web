"""配套补丁工具包入口；不搜索或自动选择用户安装。"""
import argparse
import importlib.util
import json
from pathlib import Path

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['apply','restore'])
    parser.add_argument('--root',type=Path)
    parser.add_argument('--yes',action='store_true')
    args=parser.parse_args()
    target=args.root
    if target is None:
        print('请先完全退出 DSH。仅支持已验证的 Windows DSH 0.2.2-rc.1。')
        target=Path(input('粘贴 DeepSeek Harness.exe 的完整路径（或安装文件夹）：\n').strip().strip('"'))
    if target.suffix.lower()=='.exe': target=target.parent
    print(('恢复官方程序：' if args.action=='restore' else '应用桌面启动补丁：')+str(target))
    print('仅修改该安装的 app.asar；不复制或覆盖你的环境、会话或凭据。')
    if not args.yes and input('确认请输入 YES，其他输入取消：').strip()!='YES':
        print('已取消，未修改。');return 0
    spec=importlib.util.spec_from_file_location('crate_desktop_patcher',Path(__file__).with_name('desktop-profile-patch.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    result=module.patch(target,args.action=='restore',installed=True,confirm=True)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    print('完成。可以重新打开 DSH。');return 0

if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as error:
        print('操作未完成：'+str(error));raise SystemExit(1)
