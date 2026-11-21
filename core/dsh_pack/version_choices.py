"""用户显式选择的派生导入包；不安装，不修改原件，不宣称运行兼容。"""
import copy
import json
from pathlib import Path
from .errors import PackImportError
from .pack import read, create, sha256_bytes
from .registry import fetch, package_name, exact_version
from .bundle import check_bundle_artifact
from .partial_import import prune_plugins, merge_command, package_manifest, required_dependencies
from .export import _registry_spec_satisfies

AUDIT = '.dsh-crate/version-choices.json'


def fail(message, code='VERSION_CHOICE_BLOCKED'):
    raise PackImportError(message, stage='compatibility', code=code)


def read_audit(data):
    if AUDIT not in data.profile_files:
        return None
    try:
        audit = json.loads(data.profile_files[AUDIT])
        if not isinstance(audit, dict) or not isinstance(audit.get('choices'), list) or len(audit['choices']) > 50000:
            fail('换版记录无效')
        seen = set()
        for choice in audit['choices']:
            if not isinstance(choice, dict) or choice.get('action') not in {'replace', 'skip'}:
                fail('换版记录无效')
            name = package_name(choice.get('name'))
            if name in seen or name.startswith('@deepseek-ai/'):
                fail('换版记录包含重复项或官方组件')
            seen.add(name)
            exact_version(choice.get('from'))
            if choice['action'] == 'replace':
                exact_version(choice.get('to'))
        return audit
    except (ValueError, TypeError) as error:
        fail('换版记录无法读取')


def check_existing(data, home, target, mode):
    audit = read_audit(data)
    if not audit or not target:
        return
    from .importer import _validate_profile_name
    _validate_profile_name(target)
    root = Path(home).resolve() / 'profiles'
    profile = root / target
    if not profile.resolve().is_relative_to(root) or profile.is_symlink():
        fail('目标环境路径无效')
    for choice in audit['choices']:
        if choice['action'] != 'replace':
            continue
        path = profile / 'node_modules' / choice['name'] / 'package.json'
        if not path.is_file():
            continue
        installed = json.loads(path.read_bytes()).get('version')
        if mode == 'add':
            fail('只新增模式不会替换已有插件；请选择增量更新')
        if _registry_spec_satisfies('>=' + str(installed), choice['to']) is not True:
            fail('不能确认已有插件数据支持降级，已停止应用', 'VERSION_DOWNGRADE_UNVERIFIED')


def choice_report(data):
    audit = read_audit(data)
    if not audit:
        return None
    return {'versionChoices': audit, 'runtimeVerification': 'UNTESTED',
            'skippedPlugins': [{'name': c['name'], 'reason': 'USER_SKIPPED'} for c in audit['choices'] if c['action'] == 'skip']}


def prepare(source, output, choices, profile, npm_command=None):
    data = read(source)  # 损坏包、非法路径、哈希错误永远先失败。
    if not isinstance(choices, list) or not 1 <= len(choices) <= 50:
        fail('请选择 1 到 50 个问题插件')
    result = copy.deepcopy(data)
    rows = {row['name']: row for row in result.plugins_lock['plugins']}
    package = json.loads(result.profile_files['package.json'])
    seen, skipped, audit = set(), set(), []
    for choice in choices:
        if not isinstance(choice, dict) or choice.get('action') not in {'replace', 'skip'}:
            fail('无效的插件处理选择')
        name = package_name(choice.get('name'))
        if name in seen or name not in rows:
            fail('选择重复或插件不在原包中')
        seen.add(name); row = rows[name]
        if name.startswith('@deepseek-ai/') or row['runtime']['source'] == 'installation-anchor':
            fail('官方基础组件由宿主适配，不能在此换版或跳过')
        old = row['runtime']['version']
        if choice['action'] == 'skip':
            skipped.add(name); audit.append({'name': name, 'action': 'skip', 'from': old})
            continue
        version = exact_version(choice.get('version'))
        if _registry_spec_satisfies('>=' + old, version) is not True:
            fail('尚无配置和数据降级迁移规则，不能应用更低或无法比较的版本', 'VERSION_DOWNGRADE_UNVERIFIED')
        manifest, content, integrity, url = fetch(profile, name, version, npm_command, reject_deprecated=True)
        if manifest.get('deprecated'):
            fail('不能应用已弃用版本')
        patch = manifest.get('dsh', {}).get('bundle', {}).get('patch')
        if row['bundle']['enabled']:
            if not patch:
                fail('所选版本没有可启用的 Bundle')
            check_bundle_artifact(content, patch)
            row['bundle']['patch'] = patch
        key = 'choice-' + sha256_bytes(content) + '.tgz'
        result.plugin_artifacts[key] = content
        row['artifact'] = {'mode': 'embedded', 'path': 'plugins/' + key, 'sha256': sha256_bytes(content)}
        row['requested'] = {'sourceType': 'registry', 'specifier': version}
        row['resolved'] = {'version': version, 'locator': name + '@' + version}
        row['runtime']['version'] = version
        for field in ('dependencies', 'devDependencies', 'optionalDependencies', 'peerDependencies'):
            if name in package.get(field, {}):
                package[field][name] = version
        audit.append({'name': name, 'action': 'replace', 'from': old, 'to': version,
                      'sha256': sha256_bytes(content), 'integrity': integrity, 'source': url,
                      'runtimeVerification': 'UNTESTED'})
    result.profile_files['package.json'] = json.dumps(package, ensure_ascii=False).encode()
    if skipped:
        result, removed = prune_plugins(result, skipped, merge_command())
        for name in sorted(removed - skipped):
            audit.append({'name': name, 'action': 'skip', 'from': rows[name]['runtime']['version'], 'reason': 'PLUGIN_DEPENDENCY_UNAVAILABLE'})
    manifests = {r['name']: package_manifest(result, r) for r in result.plugins_lock['plugins']}
    versions = {r['name']: r['runtime']['version'] for r in result.plugins_lock['plugins']}
    for name, manifest in manifests.items():
        for dep in required_dependencies(manifest) & versions.keys():
            spec = manifest.get('dependencies', {}).get(dep) or manifest.get('peerDependencies', {}).get(dep)
            if _registry_spec_satisfies(spec, versions[dep]) is False:
                fail(f'{name} 需要 {dep}@{spec}，所选版本不满足依赖')
    # Stale lockfiles must not force the previous resolution after a user choice.
    for name in ('pnpm-lock.yaml', 'package-lock.json', 'yarn.lock'):
        result.profile_files.pop(name, None)
    used = {r['artifact'].get('path', '').removeprefix('plugins/') for r in result.plugins_lock['plugins']}
    result.plugin_artifacts = {k: v for k, v in result.plugin_artifacts.items() if k in used}
    completeness = result.manifest.get('completeness')
    if completeness:
        completeness['embedded'] = [r['name'] for r in result.plugins_lock['plugins'] if r['artifact']['mode'] == 'embedded']
        completeness['referenceOnly'] = [r['name'] for r in result.plugins_lock['plugins'] if r['artifact']['mode'] == 'reference-only']
        completeness['offlineRestorable'] = 'NO' if completeness['referenceOnly'] else 'UNPROVEN'
    if any(isinstance(r['bundle'].get('patch'), list) for r in result.plugins_lock['plugins']):
        result.plugins_lock['schemaVersion'] = 2
        result.manifest['schemaVersion'] = max(3, result.manifest['schemaVersion'])
    record = {'sourceSha256': sha256_bytes(Path(source).read_bytes()), 'choices': audit, 'runtimeVerification': 'UNTESTED'}
    result.profile_files[AUDIT] = json.dumps(record, ensure_ascii=False, sort_keys=True).encode()
    create(result, output, compression='fast')
    return {**record, 'preparedSha256': sha256_bytes(Path(output).read_bytes()), 'status': 'prepared'}
