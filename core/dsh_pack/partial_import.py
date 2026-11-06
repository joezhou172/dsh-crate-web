"""兼容导入：原包不可变，插件级降级与整包安全失败分开。"""
from __future__ import annotations
import copy
import io
import json
import os
import subprocess
import tarfile
from contextlib import contextmanager
from pathlib import Path
from .errors import PackImportError

CORE = {'@deepseek-ai/dsh-base', '@deepseek-ai/dsh-web-app'}
RECOVERABLE = {'PLUGIN_INSTALL_FAILED', 'PLUGIN_SOURCE_MISSING', 'PLUGIN_MISSING',
               'NETWORK_INSTALL_FAILED', 'NETWORK_INSTALL_TIMEOUT', 'PLUGIN_VERSION_MISMATCH',
               'PACKAGE_MANIFEST_INVALID', 'BUNDLE_PATCH_MISSING', 'BUNDLE_PATCH_INVALID', 'BUNDLE_PATCH_MISMATCH'}


def required_dependencies(manifest):
    required = set(manifest.get('dependencies', {}))
    required.update(dep for dep in manifest.get('peerDependencies', {})
                    if not manifest.get('peerDependenciesMeta', {}).get(dep, {}).get('optional'))
    return required - set(manifest.get('optionalDependencies', {}))


def dependency_closure(names, manifests):
    result = set(names)
    pending = list(names)
    while pending:
        name = pending.pop()
        for dep in required_dependencies(manifests.get(name, {})) & manifests.keys() - result:
            result.add(dep); pending.append(dep)
    return result


def package_manifest(data, row):
    artifact = row.get('artifact', {})
    if artifact.get('mode') != 'embedded':
        return {}
    content = data.plugin_artifacts.get(artifact.get('path', '').removeprefix('plugins/'))
    if content is None:
        return {}
    try:
        with tarfile.open(fileobj=io.BytesIO(content), mode='r:*') as archive:
            member = archive.getmember('package/package.json')
            if not member.isfile():
                raise ValueError('package manifest is not a regular file')
            manifest = json.loads(archive.extractfile(member).read())
            if not isinstance(manifest, dict):
                raise ValueError('package manifest must be an object')
            return manifest
    except (KeyError, ValueError, tarfile.TarError) as error:
        raise PackImportError('插件制品无法读取，已停止导入', stage='compatibility', code='PACKAGE_MANIFEST_INVALID',
                              details={'plugin': row['name'], 'error': str(error)}) from error


def dependency_exclusions(data, excluded):
    result = set(excluded)
    manifests = {}
    for row in data.plugins_lock['plugins']:
        try:
            manifests[row['name']] = package_manifest(data, row)
        except PackImportError:
            if row['name'] not in result:
                raise
            manifests[row['name']] = {}
    changed = True
    while changed:
        changed = False
        for name, manifest in manifests.items():
            required = required_dependencies(manifest)
            if name not in result and required & result:
                result.add(name)
                changed = True
    if result & CORE:
        raise PackImportError('基础环境依赖不可用，不能提交部分环境', stage='compatibility',
                              code='CORE_PLUGIN_UNAVAILABLE', details={'plugins': sorted(result & CORE)})
    return result


def prune_plugins(data, names, command=None):
    """仅处理明确属于被跳过插件的依赖、Bundle 与 Loader 配置。"""
    names = dependency_exclusions(data, names)
    result = copy.deepcopy(data)
    removed = [row for row in result.plugins_lock['plugins'] if row['name'] in names]
    patches = []
    for row in removed:
        artifact = row.get('artifact', {})
        content = data.plugin_artifacts.get(artifact.get('path', '').removeprefix('plugins/'))
        if content and row.get('bundle', {}).get('enabled'):
            from .validation import bundle_patch_paths
            with tarfile.open(fileobj=io.BytesIO(content), mode='r:*') as archive:
                for patch in bundle_patch_paths(row['bundle'].get('patch')):
                    try:
                        member = archive.getmember('package/' + patch.removeprefix('./'))
                        if member.isfile():
                            patches.append(archive.extractfile(member).read().decode('utf-8'))
                    except (KeyError, UnicodeDecodeError):
                        # 缺失的 patch 不会贡献 Loader rows；移除包名引用即可。
                        continue
    configs = {name: value.decode('utf-8') if isinstance(value, bytes) else value
               for name, value in result.profile_files.items() if name in {'cordis.yml', 'cordis.patch.yml'}}
    if configs and any(value.strip() not in {'', '[]', '---\n[]'} for value in configs.values()):
        if not command:
            raise PackImportError('跳过插件需要配置解析器，当前无法安全移除配置引用', stage='compatibility', code='PARTIAL_CONFIG_ADAPTER_REQUIRED')
        run = subprocess.run(command, input=json.dumps({'operation': 'exclude-plugins', 'names': sorted(names),
                             'files': configs, 'bundlePatches': patches}), text=True, encoding='utf-8', capture_output=True,
                             timeout=30, env={**os.environ, 'ELECTRON_RUN_AS_NODE': '1'})
        if run.returncode:
            raise PackImportError('无法安全处理被跳过插件的配置', stage='compatibility', code='PARTIAL_CONFIG_FAILED', details={'stderr': run.stderr})
        for name, text in json.loads(run.stdout)['files'].items():
            if name not in configs:
                raise ValueError('Unexpected config adapter output')
            result.profile_files[name] = text.encode('utf-8')
    package = json.loads(result.profile_files['package.json'])
    for field in ['dependencies', 'devDependencies', 'optionalDependencies', 'peerDependencies']:
        for name in names:
            package.get(field, {}).pop(name, None)
    bundles = package.get('dsh', {}).get('profile', {}).get('bundles', [])
    bundles[:] = [name for name in bundles if name not in names]
    result.profile_files['package.json'] = json.dumps(package, ensure_ascii=False, indent=2).encode()
    result.plugins_lock['plugins'] = [row for row in result.plugins_lock['plugins'] if row['name'] not in names]
    for row in result.plugins_lock['plugins']:
        if row['bundle'].get('enabled'):
            row['bundle']['order'] = bundles.index(row['name'])
    used = {row.get('artifact', {}).get('path', '').removeprefix('plugins/') for row in result.plugins_lock['plugins']}
    result.plugin_artifacts = {key: value for key, value in result.plugin_artifacts.items() if key in used}
    return result, names


def merge_command():
    value = os.environ.get('DSH_PACK_CONFIG_MERGE_COMMAND')
    return tuple(json.loads(value)) if value else None


def restore_baseline(data, baseline, excluded):
    """失败更新恢复原制品；无法确定配置归属时保留原配置，不猜测键的所有者。"""
    result = copy.deepcopy(data)
    previous = {row['name']: row for row in baseline.plugins_lock['plugins']}
    retained = set(excluded) & previous.keys()
    if not retained:
        return result, retained
    package = json.loads(result.profile_files['package.json'])
    original = json.loads(baseline.profile_files['package.json'])
    for name in sorted(retained):
        row = copy.deepcopy(previous[name])
        result.plugins_lock['plugins'].append(row)
        if row['artifact']['mode'] == 'embedded':
            key = row['artifact']['path'].removeprefix('plugins/')
            result.plugin_artifacts[key] = baseline.plugin_artifacts[key]
        for field in ('dependencies', 'devDependencies', 'optionalDependencies', 'peerDependencies'):
            if name in original.get(field, {}):
                package.setdefault(field, {})[name] = original[field][name]
    bundles = package.setdefault('dsh', {}).setdefault('profile', {}).setdefault('bundles', [])
    old_bundles = original.get('dsh', {}).get('profile', {}).get('bundles', [])
    # 原顺序优先，保留新插件的相对顺序。
    bundles[:] = [name for name in old_bundles if name in bundles or name in retained] + [name for name in bundles if name not in old_bundles]
    for row in result.plugins_lock['plugins']:
        if row['bundle'].get('enabled'):
            row['bundle']['order'] = bundles.index(row['name'])
    for name, content in baseline.profile_files.items():
        if name not in {'package.json', 'pnpm-lock.yaml', 'package-lock.json'} and not name.startswith('.dsh-crate/'):
            result.profile_files[name] = content
    result.profile_files['package.json'] = json.dumps(package, ensure_ascii=False, indent=2).encode()
    return result, retained


@contextmanager
def compatible_pack(source, environment, host_bundles=None, modules=None):
    import tempfile
    from .pack import read, create, sha256_bytes
    from .compatibility import adapt_data
    data = read(source)  # 完整性、schema、路径错误始终是整包失败。
    original_environment = copy.deepcopy(data.manifest.get('environment', {}))
    source_version = original_environment.get('dsh', {}).get('version')
    target_version = environment.get('dsh', {}).get('version')
    adaptation = None
    excluded = {}
    if target_version and source_version != target_version and host_bundles and modules:
        for row in data.plugins_lock['plugins']:
            if row.get('runtime', {}).get('source') == 'installation-anchor' and row['name'] not in host_bundles:
                excluded[row['name']] = {'name': row['name'], 'reason': 'HOST_BUNDLE_UNAVAILABLE'}
        if excluded:
            data, names = prune_plugins(data, excluded, merge_command())
            for name in names:
                excluded.setdefault(name, {'name': name, 'reason': 'PLUGIN_DEPENDENCY_UNAVAILABLE'})
        if any(row.get('runtime', {}).get('source') == 'installation-anchor' for row in data.plugins_lock['plugins']):
            data, adaptation = adapt_data(data, target_version, host_bundles, modules)
    os_name = environment.get('os', {}).get('name', '').lower()
    platform = {'windows': 'win32', 'win32': 'win32', 'darwin': 'darwin', 'macos': 'darwin', 'linux': 'linux'}.get(os_name)
    for row in data.plugins_lock['plugins']:
        if row['name'] not in CORE:
            row['required'] = False
        try:
            manifest = package_manifest(data, row)
        except PackImportError as error:
            excluded[row['name']] = {'name': row['name'], 'reason': error.code, 'diagnostic': error.as_dict()}
            continue
        systems = manifest.get('os')
        if platform and isinstance(systems, list):
            allowed = [value for value in systems if isinstance(value, str) and not value.startswith('!')]
            if '!'+platform in systems or (allowed and platform not in allowed and 'any' not in allowed):
                excluded[row['name']] = {'name': row['name'], 'reason': 'PLUGIN_OS_UNSUPPORTED', 'requiredOS': systems, 'currentOS': platform}
    if excluded:
        data, all_names = prune_plugins(data, excluded, merge_command())
        for name in all_names:
            excluded.setdefault(name, {'name': name, 'reason': 'PLUGIN_DEPENDENCY_UNAVAILABLE'})
    report = {'policy': 'compatible', 'sourceEnvironment': original_environment, 'targetEnvironment': dict(environment),
              'sourceSha256': sha256_bytes(Path(source).read_bytes()),
              'hostAdaptation': adaptation, 'skippedPlugins': list(excluded.values()), 'runtimeVerification': 'UNTESTED'}
    with tempfile.TemporaryDirectory(prefix='crate-compatible-') as directory:
        path = create(data, Path(directory)/'compatible.dshcrate', compression='fast')
        yield path, report


def result_report(value, report):
    result = dict(value)
    skipped = [*report.get('skippedPlugins', []), *result.get('skippedPlugins', [])]
    result['skippedPlugins'] = list({row['name']: row for row in skipped}.values())
    result['compatibilityReport'] = report
    result['completionStatus'] = 'DEGRADED' if skipped else 'PASS'
    result['runtimeVerification'] = 'UNTESTED'
    return result


def manager_exclusions(profile, data, selected, options, failure):
    """依赖解析失败时用独立安装定位；网络、权限、磁盘错误不猜测为插件冲突。"""
    import re
    import tempfile
    from dataclasses import replace
    from .importer import _pnpm_rebuild, _extract_embedded_artifact
    from .pack import sha256_bytes
    def attributable(error):
        if error.code != 'PACKAGE_MANAGER_FAILED':
            return False
        details = error.as_dict().get('details', {})
        return bool(re.search(r'ERR_PNPM_(?:FETCH_404|NO_MATCHING_VERSION|UNSUPPORTED_ENGINE|UNSUPPORTED_PLATFORM|NO_OFFLINE_TARBALL|NO_OFFLINE_META|LINKED_PKG_DIR_NOT_FOUND|TARBALL_ENOENT)\b',
                              str(details.get('stdout', '')) + str(details.get('stderr', ''))))
    if not attributable(failure):
        return {}
    manifest = json.loads((profile/'package.json').read_bytes())
    rows, artifacts = {}, {}
    for original in selected:
        row = copy.deepcopy(original); name = row['name']
        locator = manifest['dependencies'][name]
        path = (profile/locator.removeprefix('file:')).resolve()
        if not path.is_relative_to((profile/'.dsh-crate/artifacts').resolve()):
            raise failure
        content = path.read_bytes(); key = sha256_bytes(content)+'.tgz'
        row['artifact'] = {'mode': 'embedded', 'path': 'plugins/'+key, 'sha256': sha256_bytes(content)}
        rows[name] = row; artifacts[key] = content
    anchors = {name for name, row in rows.items() if name in CORE or row.get('runtime', {}).get('source') == 'installation-anchor'}
    evidence = copy.deepcopy(data); evidence.plugin_artifacts = artifacts
    manifests = {name: package_manifest(evidence, row) for name, row in rows.items()}
    def probe(names):
        names = dependency_closure(names, manifests)
        sample = copy.deepcopy(data)
        sample.plugins_lock['plugins'] = [rows[name] for name in sorted(names)]
        sample.plugin_artifacts = artifacts
        package = {'name': 'crate-compatibility-probe', 'private': True,
                   'dependencies': {name: rows[name]['runtime']['version'] for name in names}}
        sample.profile_files = {'package.json': json.dumps(package).encode()}
        with tempfile.TemporaryDirectory(prefix='.crate-probe-', dir=profile.parent) as directory:
            temporary = Path(directory)
            (temporary/'package.json').write_bytes(sample.profile_files['package.json'])
            for row in sample.plugins_lock['plugins']:
                _extract_embedded_artifact(temporary, row, artifacts[row['artifact']['path'].removeprefix('plugins/')])
            return _pnpm_rebuild(temporary, sample, sample.plugins_lock['plugins'], replace(options, patch_adapter_command=None))
    # 同一基础环境必须先成功，否则不能归罪于第三方插件。
    if anchors:
        probe(anchors)
    rejected = {}
    for name in sorted(rows.keys() - anchors):
        try:
            probe(anchors | {name})
        except PackImportError as error:
            if not attributable(error):
                raise failure from error
            rejected[name] = {'name': name, 'reason': 'PLUGIN_DEPENDENCY_INSTALL_FAILED', 'diagnostic': error.as_dict()}
    return rejected
