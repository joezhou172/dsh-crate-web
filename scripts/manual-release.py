"""手动发布已经验收的制品；不重新构建，不接收任意下载地址。"""
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tarfile
from release_guard import inspect_tarball
from release_policy import validate_metadata

def release_inputs():
    version = os.environ.get('RELEASE_VERSION', '')
    digest = os.environ.get('EXPECTED_SHA256', '')
    if not re.fullmatch(r'\d+\.\d+\.\d+-preview\.\d+', version):
        raise ValueError('只接受明确的 Preview 版本')
    if not re.fullmatch(r'[0-9a-f]{64}', digest):
        raise ValueError('必须提供已验收制品的 SHA-256')
    return version, digest

def audit():
    version, digest = release_inputs()
    path = Path('release') / f'dsh-crate-web-{version}.tgz'
    if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise ValueError('下载制品与本机验收制品不一致')
    report = inspect_tarball(path)
    if report['status'] != 'PASS':
        print(json.dumps(report['findings']))
        raise ValueError('制品安全检查失败')
    with tarfile.open(path, 'r:gz') as archive:
        pkg = json.load(archive.extractfile('package/package.json'))
        if validate_metadata(pkg) != version:
            raise ValueError('制品版本与手动输入不符')
        core = archive.extractfile('package/core/dsh_pack/_version.py').read().decode()
        skill = json.load(archive.extractfile('package/skills/dsh-crate-troubleshooting/compatibility.json'))
        match = re.search(r'__version__\s*=\s*[\'"]([^\'"]+)', core)
        if not match or match[1] != version or skill['skillVersion'] != version:
            raise ValueError('Core、Skill 和 npm 版本不一致')
        if 'package/open-profile-runner.mjs' not in archive.getnames():
            raise ValueError('缺少独立环境启动器')
    report['filename'] = path.name
    Path('release/audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('status', 'version', 'sha256', 'fileCount')}))

if __name__ == '__main__':
    if sys.argv[1:] == ['inputs']:
        release_inputs()
    elif sys.argv[1:] == ['audit']:
        audit()
    else:
        raise SystemExit('需要 inputs 或 audit')
