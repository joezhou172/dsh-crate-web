"""对精确匹配的 Windows 桌面创建独立修复副本；只用 Python 标准库。"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import struct

ROOT = Path(__file__).resolve().parent


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_hash(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def safe_name(name):
    if not isinstance(name, str) or not name or '\\' in name:
        raise ValueError('非法资源相对路径')
    path = PurePosixPath(name)
    if path.is_absolute() or ':' in name or any(p in ('', '.', '..') for p in name.split('/')):
        raise ValueError('非法资源相对路径')
    return name


def leaves(header, prefix=''):
    for key, node in header.get('files', {}).items():
        name = prefix + key
        safe_name(name)
        if 'files' in node:
            yield from leaves(node, name + '/')
        else:
            yield name, node


class Asar:
    def __init__(self, path):
        self.path = Path(path)
        self.file = self.path.open('rb')
        try:
            a, n, c, size = struct.unpack('<4I', self.file.read(16))
            if a != 4 or size > 64 * 1024 * 1024 or n < 8 + size or c < 4 + size:
                raise ValueError('不支持的 ASAR 头')
            raw = self.file.read(size)
            if len(raw) != size:
                raise ValueError('ASAR 头不完整')
            self.header_hash = digest(raw)
            self.header = json.loads(raw)
            self.base = 8 + n
        except BaseException:
            self.close()
            raise

    def entry(self, name):
        node = self.header
        for part in safe_name(name).split('/'):
            node = node['files'][part]
        return node

    def read(self, name, seen=()):
        if name in seen or len(seen) > 64:
            raise ValueError('ASAR 链接循环')
        entry = self.entry(name)
        if 'link' in entry:
            return self.read(entry['link'], (*seen, name))
        if entry.get('unpacked'):
            return Path(str(self.path) + '.unpacked').joinpath(*name.split('/')).read_bytes()
        self.file.seek(self.base + int(entry['offset']))
        data = self.file.read(entry['size'])
        if len(data) != entry['size']:
            raise ValueError('ASAR 内容不完整')
        return data

    def close(self):
        self.file.close()


def apply_patch(source, patch):
    """精确应用统一 diff；行号、旧内容和 hunk 数量均核对，不模糊匹配。"""
    original = source.splitlines(keepends=True)
    result, position, index, hunks = [], 0, 0, 0
    lines = patch.splitlines(keepends=True)
    while index < len(lines):
        line = lines[index]
        if not line.startswith('@@ '):
            index += 1
            continue
        match = re.fullmatch(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@[^\r\n]*\n?', line)
        if not match:
            raise ValueError('非法补丁 hunk')
        start = int(match[1]) - 1
        if start < position or start > len(original):
            raise ValueError('补丁 hunk 越界或重叠')
        result.extend(original[position:start])
        position, index, old_count, new_count = start, index + 1, 0, 0
        hunks += 1
        while index < len(lines) and not lines[index].startswith('@@ '):
            line = lines[index]
            index += 1
            if not line or line[0] not in ' +-':
                raise ValueError('非法补丁内容')
            kind, text = line[0], line[1:]
            if kind in ' -':
                if position >= len(original) or original[position] != text:
                    raise ValueError('补丁上下文不匹配')
                position += 1
                old_count += 1
            if kind in ' +':
                result.append(text)
                new_count += 1
        if old_count != int(match[2] or 1) or new_count != int(match[4] or 1):
            raise ValueError('补丁行数不匹配')
    if not hunks:
        raise ValueError('空补丁')
    result.extend(original[position:])
    return ''.join(result)


def patched_modules(reader, manifest, asset_root=ROOT):
    changes = {}
    for row in manifest['patches']:
        name = safe_name(row['path'])
        if name in changes or reader.entry(name).get('unpacked') or 'link' in reader.entry(name):
            raise ValueError('补丁目标重复或不是 packed 普通文件')
        original = reader.read(name)
        patch = (asset_root / safe_name(row['patch'])).read_bytes()
        if digest(original) != row['beforeSha256'] or digest(patch) != row['patchSha256']:
            raise ValueError('模块或补丁身份不匹配: ' + name)
        normalized = original.decode('utf8').replace('\r\n', '\n')
        text = apply_patch(normalized if normalized.endswith('\n') else normalized + '\n', patch.decode('utf8'))
        if not row['outputFinalNewline']:
            text = text.removesuffix('\n')
        if row['outputNewline'] == 'CRLF':
            text = text.replace('\n', '\r\n')
        elif row['outputNewline'] != 'LF':
            raise ValueError('未知输出换行格式')
        raw = text.encode('utf8')
        if digest(raw) != row['afterSha256']:
            raise ValueError('补丁输出身份不匹配: ' + name)
        changes[name] = raw
    return changes


def rewrite_asar(reader, destination, changes):
    header = copy.deepcopy(reader.header)
    packed = []
    for name, node in leaves(header):
        if name in changes:
            data = changes[name]
            node['size'] = len(data)
            if 'integrity' in node:
                integrity = node['integrity']
                block = integrity['blockSize']
                if block <= 0:
                    raise ValueError('非法 ASAR blockSize')
                integrity['hash'] = digest(data)
                integrity['blocks'] = [digest(data[i:i + block]) for i in range(0, len(data), block)]
        if 'offset' in node:
            packed.append((int(reader.entry(name)['offset']), name, node))
    packed.sort()
    offset = 0
    for _, name, node in packed:
        node['offset'] = str(offset)
        offset += node['size']
    raw = json.dumps(header, ensure_ascii=False, separators=(',', ':')).encode()
    padded = (len(raw) + 3) & ~3
    with Path(destination).open('wb') as output:
        output.write(struct.pack('<4I', 4, 8 + padded, 4 + padded, len(raw)) + raw + b'\0' * (padded - len(raw)))
        for _, name, node in packed:
            output.write(changes[name] if name in changes else reader.read(name))
    return digest(raw)


def patch_integrity(executable, spec, new_hash):
    """精确输入已锁定，唯一更新已核对的 ELECTRONASAR 完整性资源。"""
    raw = executable.read_bytes()
    offset, size = spec['resourceOffset'], spec['resourceBytes']
    old = spec['oldHeaderSha256'].encode()
    section = raw[offset:offset + size]
    if len(section) != size or section.count(old) != 1 or len(new_hash) != len(old):
        raise ValueError('EXE/ASAR 完整性资源不匹配')
    executable.write_bytes(raw[:offset] + section.replace(old, new_hash.encode()) + raw[offset + size:])


def plain_tree(path):
    for item in [path, *path.rglob('*')]:
        if item.is_symlink() or item.is_junction():
            raise ValueError('目录含重解析点')


def materialize(source, destination):
    source_arg, destination_arg = Path(source).absolute(), Path(destination).absolute()
    for path in (source_arg, destination_arg):
        for ancestor in (path, *path.parents):
            if ancestor.is_symlink() or ancestor.is_junction():
                raise ValueError('输入或输出路径含重解析点')
    source, destination = source_arg.resolve(), destination_arg.resolve()
    if destination.exists() or destination.is_relative_to(source) or source.is_relative_to(destination):
        raise ValueError('目标已存在或与输入嵌套，拒绝覆盖')
    manifest = json.loads((ROOT / 'manifest.json').read_text('utf8'))
    if manifest['schemaVersion'] != 1:
        raise ValueError('不支持的 manifest 版本')
    if file_hash(source / 'DeepSeek Harness.exe') != manifest['inputExeSha256'] or file_hash(source / 'resources/app.asar') != manifest['inputAsarSha256']:
        raise ValueError('官方输入身份不匹配；同一版本名不能代替文件身份')
    if file_hash(source / safe_name(manifest['consoleNode']['path'])) != manifest['consoleNode']['sha256']:
        raise ValueError('随包控制台 Node 身份不匹配')
    plain_tree(source)
    reader = Asar(source / 'resources/app.asar')
    try:
        if reader.header_hash != manifest['exeIntegrity']['oldHeaderSha256']:
            raise ValueError('原 ASAR header 身份不匹配')
        changes = patched_modules(reader, manifest)
        resources = {}
        for name, expected in manifest['aclFiles'].items():
            safe_name(name)
            raw = reader.read('dsh/' + name)
            if digest(raw) != expected:
                raise ValueError('官方 ACL 依赖身份不匹配')
            resources[name] = raw
        # 所有内容先核对；新副本不使用硬链接，不修改原安装或用户 Home。
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, destination, symlinks=False)
        header_hash = rewrite_asar(reader, destination / 'resources/app.asar', changes)
        patch_integrity(destination / 'DeepSeek Harness.exe', manifest['exeIntegrity'], header_hash)
        resource_root = destination / 'resources/runtime' / safe_name(manifest['aclResourceDirectory'])
        resource_root.mkdir(exist_ok=False)
        for name, raw in resources.items():
            target = resource_root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as stream:
                stream.write(raw)
        receipt = {'status': 'BUILT_NOT_TESTED', 'manifestSha256': file_hash(ROOT / 'manifest.json'),
                   'changedModules': list(changes), 'testHooksIncluded': False,
                   'outputExeSha256': file_hash(destination / 'DeepSeek Harness.exe'),
                   'outputAsarSha256': file_hash(destination / 'resources/app.asar'),
                   'integrityDisabled': False, 'originalInstallationChanged': False,
                   'modelsRequested': 0, 'desktopStarted': False}
        with (destination / 'crate-terminal-fix-receipt.json').open('x', encoding='utf8') as stream:
            json.dump(receipt, stream, ensure_ascii=False, indent=2)
        return receipt
    finally:
        reader.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--destination', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(materialize(args.source, args.destination), ensure_ascii=False))
