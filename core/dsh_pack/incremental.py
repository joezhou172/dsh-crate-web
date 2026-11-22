"""增量合并计划；准备完整新树后提交，目标始终由快照保护。"""
from __future__ import annotations
import copy
import json
import os
import re
import shutil
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
    package_name = target_pkg.get('name') or source_pkg.get('name')
    if package_name is None:
        # 私有环境可以没有包名；写成 null 会令 Node 报 ERR_INVALID_PACKAGE_CONFIG。
        package.pop('name', None)
    else:
        package['name'] = package_name
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


def _retired_bundle_evidence(options):
    """询问已选定宿主的官方只读适配器，不从包名或缺失推断退役。"""
    if not options.patch_adapter_command:
        return None
    try:
        run = subprocess.run([*options.patch_adapter_command, '--retired-bundles'], capture_output=True,
                             timeout=30, env={**os.environ, 'ELECTRON_RUN_AS_NODE': '1'})
        value = json.loads(run.stdout.decode('utf-8'))
        import re
        names = value.get('retiredBundles')
        if (run.returncode or value.get('source') != 'official-retired-bundles'
                or value.get('runtimeVersion') != options.current_environment.get('dsh', {}).get('version')
                or not isinstance(names, list) or len(names) != len(set(names))
                or any(not isinstance(n, str) or not n.startswith('@deepseek-ai/') or
                       n in {'@deepseek-ai/dsh-base', '@deepseek-ai/dsh-web-app'} for n in names)
                or any(not isinstance(value.get(k), str) or not re.fullmatch('[a-f0-9]{64}', value[k])
                       for k in ('catalogSha256', 'bootSha256'))):
            raise ValueError('invalid official retirement evidence')
        return value
    except (OSError, ValueError, TypeError, AttributeError, subprocess.TimeoutExpired) as error:
        raise PackImportError('无法核验目标宿主的官方退役 Bundle 目录', stage='planning',
                              code='HOST_RETIREMENT_EVIDENCE_INVALID') from error


def plan_incremental(source, home, name, mode, options, directory):
    from .snapshot import inventory
    from .export import export_profile, ExportOptions
    from .pack import read, create
    from .importer import create_import_plan, _host_dependency_overrides
    from dataclasses import replace
    import uuid
    target = _target(home, name)
    stage_name = 'crate-stage-' + uuid.uuid4().hex
    if "modelApi" in read(source).manifest:
        raise PackImportError("Model API settings require a new Profile", stage="planning", code="MODEL_API_NEW_PROFILE_ONLY")
    from .model_api import project
    stripped, _, _ = project(target, ())
    if stripped is not None and stripped != (target / "cordis.patch.yml").read_bytes():
        raise PackImportError("Existing model settings must be preserved; use a new Profile", stage="planning", code="MODEL_API_TARGET_PROTECTED")
    create_import_plan(source, home, options=replace(options, target_profile_name=stage_name, overwrite_existing_profile=False, overwrite_confirmation=None))
    before = inventory(target)
    import platform
    environment = copy.deepcopy(dict(options.current_environment))
    environment['schemaVersion'] = 1
    environment.setdefault('os', {}).setdefault('version', platform.release())
    environment['os'].setdefault('arch', platform.machine())
    from .errors import ExportError
    retirement = _retired_bundle_evidence(options)
    retired_names = retirement['retiredBundles'] if retirement else []
    original_bundles = json.loads((target / 'package.json').read_bytes()).get('dsh', {}).get('profile', {}).get('bundles', [])
    disabled_retired = [n for n in original_bundles if n in retired_names]
    try:
        baseline = export_profile(target, Path(directory) / 'baseline.dshcrate', options=ExportOptions(
            environment=environment, export_mode='freeze', compression='fast', retired_bundles=tuple(retired_names))).data
    except ExportError as error:
        raise PackImportError('无法准备现有环境的增量基线', stage='planning',
                              code='INCREMENTAL_BASELINE_FAILED', details={'originalError': error.as_dict()}) from error
    command = json.loads(os.environ['DSH_PACK_CONFIG_MERGE_COMMAND']) if os.environ.get('DSH_PACK_CONFIG_MERGE_COMMAND') else None
    merged, preview = merge_packs(baseline, read(source), mode, command)
    if disabled_retired:
        preview['retiredBundles'] = [{'name': n, 'action': 'disable', 'artifact': 'retained',
                                     'reason': 'OFFICIAL_BUNDLE_RETIRED'} for n in disabled_retired]
        preview['retirementEvidence'] = retirement
    rejected = {row['name'] for row in (options.compatibility_report or {}).get('skippedPlugins', [])}
    retained_rejected = rejected & {row['name'] for row in baseline.plugins_lock['plugins']}
    if retained_rejected and mode == 'update':
        for filename, content in baseline.profile_files.items():
            if filename not in {'package.json', 'pnpm-lock.yaml', 'package-lock.json'} and not filename.startswith('.dsh-crate/'):
                merged.profile_files[filename] = content
        preview['configuration'] = [row for row in preview['configuration'] if row['path'] not in baseline.profile_files]
        preview['configurationPreserved'] = True
    preview['retainedRejectedPlugins'] = sorted(retained_rejected)
    replaced = {row['name'] for row in preview['plugins'] if row['action'] != 'keep'}
    preview['retainedPlugins'] = [row['name'] for row in baseline.plugins_lock['plugins'] if row['name'] not in replaced]
    # 校验实际宿主制品后，不能再用 Profile 中的旧副本覆盖准备好的安装锚点。
    # 第三方保留逻辑不变；旧官方副本仍在事务快照中。
    host_adaptations = []
    if options.host_bundles is not None:
        _host_dependency_overrides(merged, options)
        for row in merged.plugins_lock['plugins']:
            if (row['name'] not in preview['retainedPlugins']
                    or not row.get('bundle', {}).get('enabled')
                    or row.get('runtime', {}).get('source') != 'installation-anchor'
                    or row.get('artifact', {}).get('mode') != 'embedded'):
                continue
            manifest = target / 'node_modules' / row['name'] / 'package.json'
            previous = json.loads(manifest.read_bytes()).get('version') if manifest.is_file() else None
            host_adaptations.append({'name': row['name'], 'from': previous,
                                     'to': row['runtime']['version'],
                                     'reason': 'VERIFIED_HOST_RUNTIME',
                                     'artifactSha256': row['artifact']['sha256']})
        anchored = {row['name'] for row in host_adaptations}
        preview['retainedPlugins'] = [name for name in preview['retainedPlugins'] if name not in anchored]
    preview['hostRuntimeAdaptations'] = host_adaptations
    path = create(merged, Path(directory) / 'merged.dshcrate', compression='fast')
    create_import_plan(path, home, options=replace(options, target_profile_name=stage_name, overwrite_existing_profile=False, overwrite_confirmation=None))
    if inventory(target) != before:
        raise PackImportError('目标环境已变化，请重新预览', stage='planning', code='TARGET_CHANGED')
    token = sha256_bytes(json.dumps({'target': str(target), 'files': before, 'source': sha256_bytes(Path(source).read_bytes()),
                                   'mode': mode, 'environment': dict(options.current_environment),
                                   'retirementEvidence': retirement,
                                   'hostRuntimeAdaptations': host_adaptations}, sort_keys=True).encode())
    preview.update(targetProfile=name, planToken=token, canContinue=True)
    return preview, path, stage_name


def _remember_stage(journal, transaction, prepared, stage_name):
    if not re.fullmatch(r'crate-stage-[0-9a-f]{32}', stage_name) or stage_name == transaction['target']:
        raise ValueError('invalid transaction stage name')
    identities = []
    for path in (prepared.profile_path, prepared.metadata_path):
        if path.name != stage_name or path.is_symlink() or path.is_junction():
            raise ValueError('unexpected prepared directory')
        info = path.stat()
        if not info.st_ino:
            raise ValueError('cannot identify prepared directory')
        identities.append([info.st_dev, info.st_ino])
    transaction['stage'] = {'name': stage_name, 'identities': identities}
    from .snapshot import save_json
    save_json(journal, transaction)


def _cleanup_stage(home, transaction):
    stage = transaction.get('stage')
    if not stage:
        return
    name = stage['name']
    if not re.fullmatch(r'crate-stage-[0-9a-f]{32}', name) or name == transaction['target']:
        raise ValueError('invalid transaction stage name')
    home = Path(home).resolve()
    for parent, identity in zip((home / 'profiles', home / '.dsh-pack/imports'), stage['identities'], strict=True):
        path = parent / name
        if parent.resolve() != parent or path.is_symlink() or path.is_junction():
            raise ValueError('redirected stage directory')
        try:
            info = path.stat()
        except FileNotFoundError:
            continue
        if [info.st_dev, info.st_ino] != identity:
            raise ValueError('stage directory no longer belongs to this transaction')
        shutil.rmtree(path)


def execute_incremental(source, home, name, mode, options, token, directory):
    from .snapshot import Snapshot, save_json
    from .importer import import_pack, relocate_pnpm_records
    from dataclasses import replace
    preview, path, stage_name = plan_incremental(source, home, name, mode, options, directory)
    if not token or token != preview['planToken']:
        raise PackImportError('导入计划已变化，请重新预览并确认', stage='planning', code='IMPORT_PLAN_CHANGED')
    target = _target(home, name)
    metadata = Path(home).resolve() / '.dsh-pack' / 'imports' / name
    snapshot = Snapshot(Path(home), target)
    metadata_snapshot = Snapshot(Path(home), metadata)
    journal = snapshot.root / 'transaction.json'
    transaction = {'status': 'active', 'target': name, 'snapshots': [str(snapshot.root), str(metadata_snapshot.root)], 'maintenanceJob': os.environ.get('DSH_PACK_MAINTENANCE_JOB')}
    save_json(journal, transaction)
    try:
        compatibility_report = copy.deepcopy(options.compatibility_report)
        if compatibility_report:
            for row in compatibility_report.get('skippedPlugins', []):
                if row['name'] in preview.get('retainedRejectedPlugins', []):
                    row['retainedExisting'] = True
                    row['configurationPreserved'] = bool(preview.get('configurationPreserved'))
        prepared = import_pack(path, home, options=replace(options, target_profile_name=stage_name,
                              overwrite_existing_profile=False, overwrite_confirmation=None,
                              compatibility_report=compatibility_report,
                              fallback_pack=Path(directory) / 'baseline.dshcrate' if options.allow_partial_plugins else None,
                              fallback_profile=target if options.allow_partial_plugins else None))
        _remember_stage(journal, transaction, prepared, stage_name)
        preserve_local_files(target, prepared.profile_path)
        retained = set(preview.get('retainedPlugins', []))
        retained.update(row['name'] for row in getattr(prepared, 'warnings', ()) if row.get('retainedExisting'))
        retained.difference_update(row['name'] for row in preview.get('hostRuntimeAdaptations', []))
        preserve_kept_plugins(target, prepared.profile_path, retained)
        if options.pnpm_command:
            relocate_pnpm_records(prepared.profile_path, target)
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
        try:
            _cleanup_stage(home, transaction)
        except Exception as failure:
            recovery.append(str(failure))
        transaction['status'] = 'recovery-failed' if recovery else 'restored'
        save_json(journal, transaction)
        raise PackImportError('增量导入失败，已恢复原环境' if not recovery else '增量导入失败，自动恢复未完成',
                              stage='rollback', code='IMPORT_ROLLED_BACK' if not recovery else 'ROLLBACK_FAILED',
                              details={'snapshot': str(snapshot.root), 'originalError': error.as_dict() if isinstance(error, PackImportError) else str(error),
                                       'rollback': 'PASS' if not recovery else 'FAIL', 'recoveryErrors': recovery}) from error


def recover_interrupted(home, name):
    from .snapshot import Snapshot, save_json
    for path in (Path(home) / '.dsh-pack' / 'snapshots').glob('*/transaction.json'):
        transaction = json.loads(path.read_text(encoding='utf-8'))
        if transaction.get('target') != name:
            continue
        if transaction.get('status') in {'complete', 'restored'}:
            _discard_portable_stage(path, transaction)
            continue
        for root in reversed(transaction['snapshots']):
            Snapshot.reopen(home, root).rollback()
        _rollback_portable_files(home, path, transaction)
        _cleanup_stage(home, transaction)
        _discard_portable_stage(path, transaction)
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


def preserve_kept_plugins(target, prepared, names):
    """本机增量保留未更新插件的实际文件，包括 npm files 未收录的本地补丁。"""
    import shutil
    from .snapshot import inventory
    for name in names:
        parts = name.split('/')
        if any(part in {'', '.', '..'} or '\\' in part for part in parts):
            raise PackImportError('插件路径无效', stage='prepare', code='LOCAL_FILE_LINK_UNSUPPORTED')
        source = target / 'node_modules' / name
        destination = prepared / 'node_modules' / name
        # 安装锚点提供的内置插件可能没有本地包目录。
        for root, base in [(source, target), (destination, prepared)]:
            for parent in [root, *root.parents]:
                if parent == base:
                    break
                if parent.is_symlink() or parent.is_junction():
                    raise PackImportError('插件目录含链接，无法安全保留', stage='prepare', code='LOCAL_FILE_LINK_UNSUPPORTED')
        if not source.is_dir():
            continue
        inventory(source)
        if destination.exists():
            inventory(destination)
        shutil.copytree(source, destination, dirs_exist_ok=True)


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


def _portable_paths(home, journal, relative):
    from .portability import _inside, portable_layout
    if portable_layout(relative) is None:
        raise ValueError('unexpected portable data path')
    # 保留已有事务磁盘格式，以便升级后仍能恢复之前的会话导入。
    stage = _inside(journal.parent, 'session-stage/' + relative)
    return stage, _inside(Path(home).resolve(), relative)


def _publish_portable_files(home, journal, transaction):
    from .snapshot import save_json
    for relative, digest in transaction.get('sessionFiles', {}).items():
        stage, target = _portable_paths(home, journal, relative)
        if sha256_bytes(stage.read_bytes()) != digest:
            raise ValueError('staged portable file hash mismatch')
        for parent in reversed(target.parents):
            if not parent.is_relative_to(Path(home).resolve()) or parent.exists():
                continue
            try:
                parent.mkdir()
            except FileExistsError:
                if parent.is_dir() and not parent.is_symlink() and not parent.is_junction():
                    continue
                raise
            info = parent.stat()
            transaction.setdefault('sessionDirs', {})[parent.relative_to(Path(home).resolve()).as_posix()] = [info.st_dev, info.st_ino]
            save_json(journal, transaction)
        # 原子创建；目标已存在即失败。暂存文件也为中断恢复提供文件身份。
        stage, target = _portable_paths(home, journal, relative)
        os.link(stage, target)


def _rollback_portable_files(home, journal, transaction):
    import errno
    from .portability import _inside
    root = Path(home).resolve()
    allowed_dirs = set()
    for relative, digest in transaction.get('sessionFiles', {}).items():
        stage, target = _portable_paths(home, journal, relative)
        allowed_dirs.update(p for p in target.parents if p != root and p.is_relative_to(root))
        if stage.exists() and target.exists() and stage.samefile(target):
            if sha256_bytes(target.read_bytes()) != digest:
                raise ValueError('portable file changed after publication; retained for recovery')
            target.unlink()
    for relative, identity in sorted(transaction.get('sessionDirs', {}).items(), key=lambda row: -row[0].count('/')):
        directory = _inside(root, relative)
        if directory not in allowed_dirs:
            raise ValueError('unexpected portable directory in transaction')
        if directory.exists():
            info = directory.stat()
            if [info.st_dev, info.st_ino] == identity:
                try:
                    directory.rmdir()
                except OSError as error:
                    if error.errno not in {errno.ENOTEMPTY, errno.EEXIST}:
                        raise


def _discard_portable_stage(journal, transaction):
    stage = journal.parent / 'session-stage'
    if transaction.get('sessionFiles') and stage.exists():
        shutil.rmtree(stage)


def _protected_import(source, home, options):
    """新建/覆盖导入也先快照；含 Home 数据的包不能绕过快照覆盖范围。"""
    from .pack import read
    from .importer import create_import_plan, import_pack, relocate_pnpm_records
    from .snapshot import Snapshot, save_json
    from dataclasses import replace
    import uuid
    plan = create_import_plan(source, home, options=options)
    data = read(source)
    if options.overwrite_existing_profile and options.overwrite_confirmation != 'OVERWRITE':
        raise PackImportError('覆盖需要确认', stage='planning', code='OVERWRITE_CONFIRMATION_REQUIRED')
    if os.environ.get('DSH_PACK_ACTIVE_PROFILE') == plan.profile_name:
        raise PackImportError('目标环境正在运行，请先切换', stage='planning', code='TARGET_PROFILE_RUNNING')
    has_storage = any(path.startswith('storages/') for path in data.user_data)
    snapshot = Snapshot(Path(home), plan.profile_path, return_new_to_stage=has_storage)
    metadata_snapshot = Snapshot(Path(home), plan.metadata_path, return_new_to_stage=has_storage)
    journal = snapshot.root / 'transaction.json'
    transaction = {'status': 'active', 'target': plan.profile_name, 'snapshots': [str(snapshot.root), str(metadata_snapshot.root)], 'maintenanceJob': os.environ.get('DSH_PACK_MAINTENANCE_JOB')}
    if data.user_data:
        transaction['sessionFiles'] = {path: sha256_bytes(content) for path, content in data.user_data.items()}
    save_json(journal, transaction)
    try:
        stage_name = 'crate-stage-' + uuid.uuid4().hex
        prepared = import_pack(source, home, _portable_staging=snapshot.root / 'session-stage',
                               options=replace(options, target_profile_name=stage_name,
                                               overwrite_existing_profile=False, overwrite_confirmation=None))
        _remember_stage(journal, transaction, prepared, stage_name)
        if set(prepared.plan.portable_data) != set(data.user_data):
            raise ValueError('portable data selection changed during import')
        if options.pnpm_command:
            relocate_pnpm_records(prepared.profile_path, plan.profile_path)
        finalize_metadata(prepared.metadata_path, plan.profile_path)
        snapshot.commit(prepared.profile_path)
        _publish_portable_files(home, journal, transaction)
        metadata_snapshot.commit(prepared.metadata_path)
        transaction['status'] = 'complete'
        save_json(journal, transaction)
        result = prepared.as_dict()
        result.update(profilePath=str(plan.profile_path), metadataPath=str(plan.metadata_path), plan=plan.as_dict(),
                      snapshot={'profile': str(snapshot.root), 'metadata': str(metadata_snapshot.root), 'status': 'retained'})
    except Exception as error:
        failures = []
        for saved in [metadata_snapshot, snapshot]:
            try:
                saved.rollback()
            except Exception as recovery:
                failures.append(str(recovery))
        try:
            _rollback_portable_files(home, journal, transaction)
            _cleanup_stage(home, transaction)
            if not failures:
                _discard_portable_stage(journal, transaction)
        except Exception as failure:
            failures.append(str(failure))
        transaction['status'] = 'recovery-failed' if failures else 'restored'
        save_json(journal, transaction)
        raise PackImportError('导入失败，已恢复导入前状态' if not failures else '导入失败，恢复未完成', stage='rollback',
                              code='IMPORT_ROLLED_BACK' if not failures else 'ROLLBACK_FAILED',
                              details={'snapshot': str(snapshot.root), 'originalError': error.as_dict() if isinstance(error, PackImportError) else str(error),
                                       'rollback': 'FAIL' if failures else 'PASS', 'recoveryErrors': failures}) from error
    try:
        _discard_portable_stage(journal, transaction)
    except OSError as error:
        # 提交已持久化；下次获取目标锁时继续清理。
        result.setdefault('warnings', []).append({'code': 'PORTABLE_STAGE_CLEANUP_PENDING', 'message': str(error)})
    return result
