"""增量合并计划；准备完整新树后提交，目标始终由快照保护。"""
from __future__ import annotations
import copy
import json
import os
import subprocess
from contextlib import contextmanager
from pathlib import Path
from .errors import PackImportError
from .pack import PackData, sha256_bytes


def merge_json(target, source, mode):
    if isinstance(target, dict) and isinstance(source, dict):
        result = copy.deepcopy(target)
        for key, value in source.items():
            result[key] = merge_json(result[key], value, mode) if key in result else copy.deepcopy(value)
        return result
    return copy.deepcopy(target if mode == 'add' else source)


def merge_configuration(name, target, source, mode, command=None):
    if target == source:
        return target
    if name.endswith('.json'):
        return json.dumps(merge_json(json.loads(target), json.loads(source), mode), ensure_ascii=False, indent=2).encode()
    if name.endswith(('.yml', '.yaml')):
        if not command:
            raise PackImportError('此配置需要宿主 YAML 合并器', stage='planning', code='CONFIG_MERGER_UNAVAILABLE', details={'item': name})
        run = subprocess.run(command, input=json.dumps({'target': target.decode('utf-8'), 'source': source.decode('utf-8'), 'mode': mode}),
                             encoding='utf-8', capture_output=True, timeout=30, shell=False,
                             env={**os.environ, 'ELECTRON_RUN_AS_NODE': '1'})
        if run.returncode:
            raise PackImportError('配置无法可靠合并', stage='planning', code='CONFIG_MERGE_CONFLICT', details={'item': name, 'stderr': run.stderr})
        return json.loads(run.stdout)['content'].encode('utf-8')
    return target if mode == 'add' else source


def merge_packs(target: PackData, source: PackData, mode: str, command=None):
    if mode not in {'add', 'update'}:
        raise ValueError('invalid incremental mode')
    if source.user_data:
        raise PackImportError('增量导入暂不合并 Home 数据，请使用仅插件包', stage='planning', code='INCREMENTAL_HOME_DATA_UNSUPPORTED')
    merged = copy.deepcopy(target)
    old = {row['name']: row for row in merged.plugins_lock['plugins']}
    incoming = {row['name']: row for row in source.plugins_lock['plugins']}
    changes = []
    for name, row in incoming.items():
        previous = old.get(name)
        action = 'add' if previous is None else 'keep' if mode == 'add' else 'update'
        changes.append({'name': name, 'action': action, 'before': previous, 'after': row if action != 'keep' else previous})
        if action == 'keep':
            continue
        old[name] = copy.deepcopy(row)
        if row['artifact']['mode'] == 'embedded':
            key = row['artifact']['path'].removeprefix('plugins/')
            merged.plugin_artifacts[key] = source.plugin_artifacts[key]
    target_pkg = json.loads(target.profile_files['package.json'])
    source_pkg = json.loads(source.profile_files['package.json'])
    package = merge_json(target_pkg, source_pkg, mode)
    package['name'] = target_pkg.get('name', source_pkg.get('name'))
    bundles = list(target_pkg.get('dsh', {}).get('profile', {}).get('bundles', []))
    for row in incoming.values():
        name = row['name']
        if mode == 'update' and name in bundles and not row.get('bundle', {}).get('enabled'):
            bundles.remove(name)
        if name in bundles or not row.get('bundle', {}).get('enabled'):
            continue
        if name not in {p['name'] for p in target.plugins_lock['plugins']} or mode == 'update':
            bundles.append(name)
    package.setdefault('dsh', {}).setdefault('profile', {})['bundles'] = bundles
    for name, row in old.items():
        # 已有 Bundle 顺序保留；包中缺失的插件不删除。
        enabled = name in bundles
        row['bundle']['enabled'] = enabled
        row['bundle']['order'] = bundles.index(name) if enabled else None
        if not enabled:
            row['bundle']['patch'] = None
    files = copy.deepcopy(target.profile_files)
    config_changes = []
    for name, content in source.profile_files.items():
        if name in {'package.json', 'pnpm-lock.yaml', 'package-lock.json'} or name.startswith('.dsh-crate/'):
            continue
        previous = files.get(name)
        files[name] = content if previous is None else merge_configuration(name, previous, content, mode, command)
        if files[name] != previous:
            config_changes.append({'path': name, 'action': 'add' if previous is None else 'merge',
                                   'beforeSha256': sha256_bytes(previous) if previous is not None else None,
                                   'afterSha256': sha256_bytes(files[name])})
    files['package.json'] = json.dumps(package, ensure_ascii=False, indent=2).encode()
    merged.profile_files = files
    merged.plugins_lock['plugins'] = list(old.values())
    if any(isinstance(row['bundle'].get('patch'), list) for row in old.values()):
        merged.plugins_lock['schemaVersion'] = 2
        merged.manifest['schemaVersion'] = max(3, merged.manifest['schemaVersion'])
    used = {row['artifact']['path'].removeprefix('plugins/') for row in old.values() if row['artifact']['mode'] == 'embedded'}
    merged.plugin_artifacts = {name: value for name, value in merged.plugin_artifacts.items() if name in used}
    merged.manifest['requiredSecrets'] = sorted(set(target.manifest.get('requiredSecrets', [])) | set(source.manifest.get('requiredSecrets', [])))
    return merged, {'mode': mode, 'plugins': changes, 'configuration': config_changes, 'snapshotRequired': True}


def _target(home, name):
    from .importer import _validate_profile_name
    _validate_profile_name(name)
    target = Path(home).resolve() / 'profiles' / name
    if not target.is_dir() or target.is_symlink() or target.is_junction():
        raise PackImportError('请选择已有的普通 Profile 目录', stage='planning', code='INCREMENTAL_TARGET_INVALID')
    if os.environ.get('DSH_PACK_ACTIVE_PROFILE') == name:
        raise PackImportError('目标环境正在运行，请切换到另一个环境后再导入', stage='planning', code='TARGET_PROFILE_RUNNING')
    return target


def plan_incremental(source, home, name, mode, options, directory):
    from .snapshot import inventory
    from .export import export_profile, ExportOptions
    from .pack import read, create
    from .importer import create_import_plan
    from dataclasses import replace
    import uuid
    target = _target(home, name)
    stage_name = 'crate-stage-' + uuid.uuid4().hex
    create_import_plan(source, home, options=replace(options, target_profile_name=stage_name, overwrite_existing_profile=False, overwrite_confirmation=None))
    before = inventory(target)
    import platform
    environment = copy.deepcopy(dict(options.current_environment))
    environment['schemaVersion'] = 1
    environment.setdefault('os', {}).setdefault('version', platform.release())
    environment['os'].setdefault('arch', platform.machine())
    baseline = export_profile(target, Path(directory) / 'baseline.dshcrate', options=ExportOptions(
        environment=environment, export_mode='freeze', compression='fast')).data
    command = json.loads(os.environ['DSH_PACK_CONFIG_MERGE_COMMAND']) if os.environ.get('DSH_PACK_CONFIG_MERGE_COMMAND') else None
    merged, preview = merge_packs(baseline, read(source), mode, command)
    path = create(merged, Path(directory) / 'merged.dshcrate', compression='fast')
    create_import_plan(path, home, options=replace(options, target_profile_name=stage_name, overwrite_existing_profile=False, overwrite_confirmation=None))
    if inventory(target) != before:
        raise PackImportError('目标环境已变化，请重新预览', stage='planning', code='TARGET_CHANGED')
    token = sha256_bytes(json.dumps({'target': str(target), 'files': before, 'source': sha256_bytes(Path(source).read_bytes()),
                                   'mode': mode, 'environment': dict(options.current_environment)}, sort_keys=True).encode())
    preview.update(targetProfile=name, planToken=token, canContinue=True)
    return preview, path, stage_name


def execute_incremental(source, home, name, mode, options, token, directory):
    from .snapshot import Snapshot, save_json
    from .importer import import_pack
    from dataclasses import replace
    preview, path, stage_name = plan_incremental(source, home, name, mode, options, directory)
    if not token or token != preview['planToken']:
        raise PackImportError('导入计划已变化，请重新预览并确认', stage='planning', code='IMPORT_PLAN_CHANGED')
    target = _target(home, name)
    metadata = Path(home).resolve() / '.dsh-pack' / 'imports' / name
    snapshot = Snapshot(Path(home), target)
    metadata_snapshot = Snapshot(Path(home), metadata)
    journal = snapshot.root / 'transaction.json'
    transaction = {'status': 'active', 'target': name, 'snapshots': [str(snapshot.root), str(metadata_snapshot.root)]}
    save_json(journal, transaction)
    try:
        prepared = import_pack(path, home, options=replace(options, target_profile_name=stage_name,
                              overwrite_existing_profile=False, overwrite_confirmation=None))
        preserve_local_files(target, prepared.profile_path)
        finalize_metadata(prepared.metadata_path, target)
        snapshot.commit(prepared.profile_path)
        metadata_snapshot.commit(prepared.metadata_path)
        transaction['status'] = 'complete'
        save_json(journal, transaction)
        result = prepared.as_dict()
        result.update(profilePath=str(target), metadataPath=str(metadata), incremental=preview,
                      snapshot={'profile': str(snapshot.root), 'metadata': str(metadata_snapshot.root), 'status': 'retained'})
        result['plan'].update(profileName=name, profilePath=str(target), metadataPath=str(metadata))
        return result
    except Exception as error:
        recovery = []
        for saved in [metadata_snapshot, snapshot]:
            try:
                saved.rollback()
            except Exception as failure:
                recovery.append(str(failure))
        transaction['status'] = 'recovery-failed' if recovery else 'restored'
        save_json(journal, transaction)
        raise PackImportError('增量导入失败，已恢复原环境' if not recovery else '增量导入失败，自动恢复未完成',
                              stage='rollback', code='IMPORT_ROLLED_BACK' if not recovery else 'ROLLBACK_FAILED',
                              details={'snapshot': str(snapshot.root), 'originalError': str(error),
                                       'rollback': 'PASS' if not recovery else 'FAIL', 'recoveryErrors': recovery}) from error


def recover_interrupted(home, name):
    from .snapshot import Snapshot, save_json
    for path in (Path(home) / '.dsh-pack' / 'snapshots').glob('*/transaction.json'):
        transaction = json.loads(path.read_text(encoding='utf-8'))
        if transaction.get('target') != name or transaction.get('status') in {'complete', 'restored'}:
            continue
        for root in reversed(transaction['snapshots']):
            Snapshot.reopen(home, root).rollback()
        transaction['status'] = 'restored'
        save_json(path, transaction)


@contextmanager
def target_lock(home, name):
    """系统文件锁随进程退出释放；恢复日志在下一次执行前处理。"""
    from .importer import _validate_profile_name
    _validate_profile_name(name)
    root = Path(home).resolve() / '.dsh-pack' / 'locks'
    if any(p.is_symlink() or p.is_junction() for p in [root.parent, root]):
        raise PackImportError('锁目录不能重定向', stage='planning', code='SNAPSHOT_UNSAFE_PATH')
    root.mkdir(parents=True, exist_ok=True)
    path = root / (name + '.lock')
    if path.is_symlink():
        raise PackImportError('锁文件不能重定向', stage='planning', code='SNAPSHOT_UNSAFE_PATH')
    with path.open('a+b') as stream:
        stream.seek(0); stream.write(b'0'); stream.flush(); stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise PackImportError('已有导入操作，请等待完成', stage='planning', code='IMPORT_BUSY') from error
        if os.environ.get('DSH_PACK_ACTIVE_PROFILE') == name:
            raise PackImportError('请先切换到其他环境', stage='planning', code='TARGET_PROFILE_RUNNING')
        recover_interrupted(home, name)
        yield


def locked_plan(source, home, name, mode, options, directory):
    with target_lock(home, name):
        return plan_incremental(source, home, name, mode, options, directory)


def locked_execute(source, home, name, mode, options, token, directory):
    with target_lock(home, name):
        return execute_incremental(source, home, name, mode, options, token, directory)


def protected_import(source, home, options):
    from .importer import create_import_plan
    # 自动命名先选定名称，再在锁内重新预检查；显式名称可先恢复中断事务。
    name = options.target_profile_name or create_import_plan(source, home, options=options).profile_name
    from dataclasses import replace
    with target_lock(home, name):
        return _protected_import(source, home, replace(options, target_profile_name=name))


def finalize_metadata(directory, target):
    from .snapshot import save_json
    path = directory / 'prepared.json'
    value = json.loads(path.read_text(encoding='utf-8'))
    value['profile'] = {'name': target.name, 'path': str(target)}
    save_json(path, value)


def preserve_local_files(target, prepared):
    """保留未进入 Pack 的本地文件；依赖树由安装器重建，不追随链接。"""
    import shutil
    def visit(source, destination):
        for item in source.iterdir():
            if source == target and item.name in {'node_modules', 'package.json', 'pnpm-lock.yaml', 'package-lock.json'}:
                continue
            dest = destination / item.name
            if item.is_symlink() or item.is_junction() or dest.is_symlink() or dest.is_junction():
                raise PackImportError('本地文件含链接，无法安全合并', stage='prepare', code='LOCAL_FILE_LINK_UNSUPPORTED', details={'path': str(item.relative_to(target))})
            if item.is_dir():
                if dest.exists() and not dest.is_dir():
                    raise PackImportError('本地目录与导入文件冲突', stage='prepare', code='LOCAL_FILE_CONFLICT')
                dest.mkdir(exist_ok=True)
                visit(item, dest)
            elif not dest.exists():
                shutil.copy2(item, dest)
    visit(target, prepared)


def _protected_import(source, home, options):
    """新建/覆盖导入也先快照；含 Home 数据的包不能绕过快照覆盖范围。"""
    from .pack import read
    from .importer import create_import_plan, import_pack
    from .snapshot import Snapshot, save_json
    from dataclasses import replace
    import uuid
    plan = create_import_plan(source, home, options=options)
    if read(source).user_data:
        raise PackImportError('该包包含 Home 数据，当前快照仅覆盖 Profile，请先导入仅插件包',
                              stage='snapshot', code='SNAPSHOT_HOME_DATA_UNSUPPORTED')
    if options.overwrite_existing_profile and options.overwrite_confirmation != 'OVERWRITE':
        raise PackImportError('覆盖需要确认', stage='planning', code='OVERWRITE_CONFIRMATION_REQUIRED')
    if os.environ.get('DSH_PACK_ACTIVE_PROFILE') == plan.profile_name:
        raise PackImportError('目标环境正在运行，请先切换', stage='planning', code='TARGET_PROFILE_RUNNING')
    snapshot = Snapshot(Path(home), plan.profile_path)
    metadata_snapshot = Snapshot(Path(home), plan.metadata_path)
    journal = snapshot.root / 'transaction.json'
    transaction = {'status': 'active', 'target': plan.profile_name, 'snapshots': [str(snapshot.root), str(metadata_snapshot.root)]}
    save_json(journal, transaction)
    try:
        prepared = import_pack(source, home, options=replace(options, target_profile_name='crate-stage-' + uuid.uuid4().hex,
                               overwrite_existing_profile=False, overwrite_confirmation=None))
        finalize_metadata(prepared.metadata_path, plan.profile_path)
        snapshot.commit(prepared.profile_path)
        metadata_snapshot.commit(prepared.metadata_path)
        transaction['status'] = 'complete'
        save_json(journal, transaction)
        result = prepared.as_dict()
        result.update(profilePath=str(plan.profile_path), metadataPath=str(plan.metadata_path), plan=plan.as_dict(),
                      snapshot={'profile': str(snapshot.root), 'metadata': str(metadata_snapshot.root), 'status': 'retained'})
        return result
    except Exception as error:
        failures = []
        for saved in [metadata_snapshot, snapshot]:
            try:
                saved.rollback()
            except Exception as recovery:
                failures.append(str(recovery))
        transaction['status'] = 'recovery-failed' if failures else 'restored'
        save_json(journal, transaction)
        raise PackImportError('导入失败，已恢复导入前状态' if not failures else '导入失败，恢复未完成', stage='rollback',
                              code='IMPORT_ROLLED_BACK' if not failures else 'ROLLBACK_FAILED',
                              details={'snapshot': str(snapshot.root), 'originalError': error.as_dict() if isinstance(error, PackImportError) else str(error),
                                       'rollback': 'FAIL' if failures else 'PASS', 'recoveryErrors': failures}) from error
