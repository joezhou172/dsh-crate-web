"""默认仅处理隔离副本；用户显式选择 --installed --confirm 后可处理精确匹配的安装。"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import struct
import os
import subprocess

OFFICIAL_SHA256 = '5fa8a6b21bceb8f3e99e30efa2270efd0cc773a11e42aa0488f804a64b34e637'
REPO = Path(__file__).resolve().parents[1]
MAIN = 'lib/main.js'
HOST = 'dsh/node_modules/@deepseek-ai/dsh-desktop-host/lib/index.js'

def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('官方源码锚点不唯一或已改变；拒绝修改')
    return text.replace(old, new, 1)

def edit(main, host):
    main = 'import { desktopSelection, registerDesktopLifecycle, handleDesktopHostMessage, handleDesktopFailure } from "./crate-desktop-profile.mjs";\n' + main
    main = once(main, 'function reportFatal(error, source) {', 'function reportFatal(error, source) {\n\tif (handleDesktopFailure(error)) return;')
    main = once(main, 'function resolveDesktopPaths(dshHome = resolveDshHome()) {\n\treturn {\n\t\tprofile: join(dshHome, "profiles", "desktop"),\n\t\tlock: join(dshHome, "profiles", "desktop", "lock")', 'function resolveDesktopPaths(dshHome = resolveDshHome()) {\n\tconst selected = desktopSelection(dshHome);\n\treturn {\n\t\tprofile: join(dshHome, "profiles", selected),\n\t\tlock: join(dshHome, "profiles", selected, "lock")')
    main = once(main, 'child.on("message", (message) => {', 'child.on("message", (message) => {\n\t\t\tif (handleDesktopHostMessage(message, child)) return;')
    anchor = '\tconst platformView = new DesktopPlatformView('
    setup = '''\tregisterDesktopLifecycle({
        stop: async () => {
            requireCleanStop = true;
            updateStopFailure = void 0;
            try { await backend.stop(); if (updateStopFailure) throw updateStopFailure; }
            finally { requireCleanStop = false; }
        },
        restart: () => { app.relaunch(); quitWithoutConfirmation(); }
    });
'''
    main = once(main, anchor, setup + anchor)
    host = once(host, '\tconst projectDir = process.argv[3];', '\tconst projectDir = process.argv[3];\n\tconst crateProfileName = projectDir.replaceAll("\\\\", "/").split("/").at(-1);\n\tprocess.env.DSH_PROFILE = crateProfileName;\n\tprocess.env.DSH_CRATE_DESKTOP_ADAPTER = "1";')
    host = once(host, '\t\tprofile: "desktop",', '\t\tprofile: crateProfileName,')
    return main.encode(), host.encode()

def patch(root, restore=False, *, installed=False, confirm=False):
    if installed and not confirm:
        raise ValueError('安装目录操作必须明确确认')
    for parent in [root.absolute(), *root.absolute().parents]:
        if parent.is_symlink() or (hasattr(parent, 'is_junction') and parent.is_junction()):
            raise ValueError('拒绝链接或重解析安装目录')
    root = root.resolve(strict=True)
    allowed = (REPO / 'work').resolve()
    if not installed and (not root.is_relative_to(allowed) or root == allowed or not (root / '.crate-isolated-desktop').is_file()):
        raise ValueError('必须是 work 内显式标记的独立桌面副本')
    if installed:
        executable = root / 'DeepSeek Harness.exe'
        if not executable.is_file():
            raise ValueError('请选择包含 DeepSeek Harness.exe 的安装目录')
        if os.name != 'nt':
            raise ValueError('安装目录补丁仅支持 Windows')
        env = dict(os.environ, CRATE_PATCH_EXE=str(executable))
        command = "$ErrorActionPreference='Stop'; if (@(Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -eq $env:CRATE_PATCH_EXE }).Count -gt 0) { exit 9 }"
        shell = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
        probe = subprocess.run([str(shell), '-NoProfile', '-NonInteractive', '-Command', command], env=env, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=30)
        if probe.returncode != 0:
            raise ValueError('请完全退出目标 DSH 后重试；无法确认进程状态时也不会修改')
    archive = root / 'resources/app.asar'
    backup = root / 'resources/app.asar.crate-original'
    receipt = root / 'resources/crate-profile-patch.json'
    for path in [root/'resources', archive, backup, receipt]:
        if path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()):
            raise ValueError('拒绝链接或重解析补丁文件')
    if restore:
        info = json.loads(receipt.read_text())
        if digest(archive) != info['patchedSha256'] or digest(backup) != OFFICIAL_SHA256:
            raise ValueError('桌面或备份已发生变化；拒绝恢复覆盖')
        shutil.copyfile(backup, archive)
        return {'status': 'restored', 'sha256': digest(archive)}
    if digest(archive) != OFFICIAL_SHA256:
        raise ValueError('只支持已核对的官方 0.2.2-rc.1 桌面包；拒绝未知版本或重复修改')
    if backup.exists() and digest(backup) != OFFICIAL_SHA256:
        raise ValueError('备份内容不符')
    if not backup.exists(): shutil.copyfile(archive, backup)
    with archive.open('rb') as source:
        sizes = struct.unpack('<4I', source.read(16))
        tree = json.loads(source.read(sizes[3]))
        offset = 8 + sizes[1]
        def node(path):
            entry = tree
            for part in path.split('/'): entry = entry['files'][part]
            return entry
        def read(path):
            entry = node(path); source.seek(offset + int(entry['offset'])); return source.read(entry['size'])
        package = json.loads(read('package.json'))
        if package['version'] != '0.2.2-rc.1': raise ValueError('桌面版本不符')
        main, host = edit(read(MAIN).decode(), read(HOST).decode())
        changes = {MAIN: main, HOST: host, 'lib/crate-desktop-profile.mjs': (REPO / 'desktop-profile-adapter.mjs').read_bytes()}
        original = copy.deepcopy(tree)
        tree['files']['lib']['files']['crate-desktop-profile.mjs'] = {}
        entries = []
        position = 0
        def visit(current, prefix=''):
            nonlocal position
            for name, entry in current['files'].items():
                path = prefix + name
                if 'files' in entry: visit(entry, path + '/'); continue
                if entry.get('unpacked') or 'link' in entry: continue
                old_offset = entry.get('offset')
                if path in changes:
                    data = changes[path]; entry['size'] = len(data)
                    block = 4194304
                    entry['integrity'] = {'algorithm':'SHA256','hash':hashlib.sha256(data).hexdigest(),'blockSize':block,'blocks':[hashlib.sha256(data[i:i+block]).hexdigest() for i in range(0,len(data),block)]}
                entry['offset'] = str(position); position += entry['size']
                entries.append((path, old_offset, entry['size']))
        visit(tree)
        header = json.dumps(tree, separators=(',', ':'), ensure_ascii=False).encode()
        payload = struct.pack('<I', len(header)) + header
        payload += b'\0' * ((-len(payload)) % 4)
        pickle = struct.pack('<I', len(payload)) + payload
        temp = archive.with_suffix('.asar.staging')
        with temp.open('wb') as dest:
            dest.write(struct.pack('<II', 4, len(pickle))); dest.write(pickle)
            for path, old_offset, size in entries:
                if path in changes: dest.write(changes[path])
                else:
                    source.seek(offset + int(old_offset)); dest.write(source.read(size))
    temp.replace(archive)
    report = {'status':'patched','version':package['version'],'originalSha256':OFFICIAL_SHA256,'patchedSha256':digest(archive),'files':list(changes),'scope':'explicit-installation' if installed else 'isolated-copy-only'}
    receipt.write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('--restore', action='store_true')
    parser.add_argument('--installed', action='store_true')
    parser.add_argument('--confirm', action='store_true')
    args = parser.parse_args()
    try:
        print(json.dumps(patch(args.root, args.restore, installed=args.installed, confirm=args.confirm), ensure_ascii=False))
    except Exception as error:
        print(json.dumps({'status':'failed','message':str(error)}, ensure_ascii=False))
        raise SystemExit(1)
