"""本地导入快照；不导出凭据，不追随链接，不删除失败证据。"""
from __future__ import annotations
import hashlib
import json
import os
import shutil
import time
import uuid
from pathlib import Path
from .errors import PackImportError


def inventory(root: Path):
    if root.is_symlink() or root.is_junction():
        raise PackImportError("快照根目录不能是链接", stage="snapshot", code="SNAPSHOT_UNSAFE_PATH")
    if not root.exists():
        return None
    result = {}
    def visit(directory):
        for path in sorted(directory.iterdir()):
            key = path.relative_to(root).as_posix()
            if path.is_symlink() or path.is_junction():
                # 保存链接本身；不读链接目标中的数据。
                result[key] = {"link": os.readlink(path), "junction": path.is_junction()}
            elif path.is_dir():
                result[key] = {"directory": True}
                visit(path)
            elif path.is_file():
                result[key] = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            else:
                raise PackImportError("快照包含不支持的文件类型", stage="snapshot", code="SNAPSHOT_UNSUPPORTED_FILE")
    visit(root)
    return result


def save_json(path, value):
    temp = path.with_suffix('.tmp')
    with temp.open('w', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    # Windows 的索引器/安全软件可能短暂占用新日志。仍只用原子替换，
    # 不先删除旧日志；重试耗尽后保留原异常供导入诊断与恢复使用。
    for attempt in range(8):
        try:
            os.replace(temp, path)
            break
        except OSError as error:
            if getattr(error, 'winerror', None) not in {5, 32, 33} or attempt == 7:
                raise
            time.sleep(min(0.025 * (2 ** attempt), 0.2))


class Snapshot:
    """快照校验后才能提交；原目录通过同卷重命名保留，恢复也使用重命名。"""
    def __init__(self, home: Path, target: Path):
        self.home = home.resolve()
        self.target = target
        if target.parent.resolve() not in {self.home / 'profiles', self.home / '.dsh-pack' / 'imports'} or target.is_symlink() or target.is_junction():
            raise PackImportError("目标不在 Profile 根目录内", stage="snapshot", code="SNAPSHOT_UNSAFE_PATH")
        self.root = self.home / '.dsh-pack' / 'snapshots' / uuid.uuid4().hex
        for parent in [self.home / '.dsh-pack', self.home / '.dsh-pack' / 'snapshots']:
            if parent.is_symlink() or parent.is_junction():
                raise PackImportError("快照目录不能重定向", stage="snapshot", code="SNAPSHOT_UNSAFE_PATH")
        self.before = inventory(target)
        self.state = {"status": "preparing", "target": str(target), "before": self.before}
        self.root.mkdir(parents=True, exist_ok=False)
        self.journal = self.root / 'journal.json'
        save_json(self.journal, self.state)
        for name, row in (self.before or {}).items():
            if 'sha256' not in row:
                continue
            dest = self.root / 'files' / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target / name, dest)
            if hashlib.sha256(dest.read_bytes()).hexdigest() != row['sha256']:
                raise PackImportError("快照文件校验失败", stage="snapshot", code="SNAPSHOT_HASH_MISMATCH")
        if inventory(target) != self.before:
            raise PackImportError("目标环境在快照期间发生变化", stage="snapshot", code="TARGET_CHANGED")
        self.state['status'] = 'ready'
        save_json(self.journal, self.state)

    def commit(self, prepared: Path):
        if inventory(self.target) != self.before:
            raise PackImportError("目标环境在准备期间发生变化，请重新预览", stage="commit", code="TARGET_CHANGED")
        if prepared.parent.resolve() != self.target.parent.resolve() or prepared.is_symlink() or prepared.is_junction():
            raise PackImportError("准备目录越界", stage="commit", code="SNAPSHOT_UNSAFE_PATH")
        self.state.update(status='committing', prepared=str(prepared))
        self.state['preparedInventory'] = inventory(prepared)
        save_json(self.journal, self.state)
        try:
            if self.before is not None:
                self.target.rename(self.root / 'original')
            prepared.rename(self.target)
            self.state['status'] = 'committed'
            save_json(self.journal, self.state)
        except Exception as error:
            self.rollback()
            raise PackImportError("提交失败，已恢复导入前环境", stage="commit", code="IMPORT_ROLLED_BACK",
                                  details={"snapshot": str(self.root), "originalError": str(error), "rollback": "PASS"}) from error

    def rollback(self):
        try:
            original = self.root / 'original'
            if original.exists():
                if inventory(original) != self.before:
                    raise OSError('原目录备份与快照不一致')
                if self.target.exists():
                    self.target.rename(self.root / ('failed-' + uuid.uuid4().hex))
                original.rename(self.target)
            elif self.before is None and self.target.exists():
                if self.state.get('status') not in {'committing', 'committed', 'recovery-failed'} or inventory(self.target) != self.state.get('preparedInventory'):
                    raise OSError('目标不是本事务提交的目录，保留现场以免覆盖其他修改')
                self.target.rename(self.root / ('failed-' + uuid.uuid4().hex))
            if inventory(self.target) != self.before:
                raise OSError('恢复后校验不一致')
            self.state['status'] = 'restored'
            save_json(self.journal, self.state)
        except Exception as error:
            self.state.update(status='recovery-failed', recoveryError=str(error))
            save_json(self.journal, self.state)
            raise PackImportError("自动恢复未完成，快照和失败目录已保留", stage="rollback", code="ROLLBACK_FAILED",
                                  details={"snapshot": str(self.root), "error": str(error)}) from error

    @classmethod
    def reopen(cls, home, root):
        home, root = Path(home).resolve(), Path(root).resolve()
        if root.parent != home / '.dsh-pack' / 'snapshots':
            raise ValueError('snapshot outside Home')
        obj = object.__new__(cls)
        obj.home, obj.root, obj.journal = home, root, root / 'journal.json'
        obj.state = json.loads(obj.journal.read_text(encoding='utf-8'))
        obj.target, obj.before = Path(obj.state['target']), obj.state['before']
        if obj.target.parent.resolve() not in {home / 'profiles', home / '.dsh-pack' / 'imports'}:
            raise ValueError('snapshot target outside Home')
        return obj
