"""Explicit, static environment resources; no software installation or execution.

Resources travel within the new Profile, not in arbitrary destination paths.
External binaries must be bound on the receiving machine. Source paths are
only present in the local catalog; the archive uses opaque IDs and tokens.
"""
from __future__ import annotations
import hashlib
import json
import ntpath
import os
import re
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlsplit
from .errors import ExportError, SchemaValidationError
from .portability import assert_private_values_absent, safe_relative

ROOT = 'crate-environment'
MAX_FILES = 1500
MAX_BYTES = 64 * 1024 * 1024
TEXT = {'.md', '.txt', '.json', '.yml', '.yaml', '.py', '.js', '.mjs', '.cjs', '.ts', '.ps1', '.sh', '.toml', '.ini', '.css', '.html', '.svg'}
FORBIDDEN = {'node_modules', '.git', '.env', '.venv', 'venv', '__pycache__', 'cache', 'logs', 'credentials.json', 'credentials.yml', 'credentials.yaml'}
TOKEN = re.compile(r'__CRATE_(PATH|URI)_([a-f0-9]{20})__')
URI = re.compile(r'file:///(?:[^\s\"\'`<>])+')

def _digest(content):
    return hashlib.sha256(content).hexdigest()

def _source(value):
    if not isinstance(value, str) or '\n' in value or '\r' in value:
        return None
    if value.startswith('file:///'):
        parsed = urlsplit(value)
        if parsed.query or parsed.fragment:
            raise ExportError('Resource file URI query/fragment requires an adapter')
        value = unquote(parsed.path)
        if os.name == 'nt' and re.match(r'^/[A-Za-z]:/', value):
            value = value[1:]
    if Path(value).is_absolute() or ntpath.isabs(value):
        return Path(value)
    return None

def _regular(path):
    for item in [path, *path.parents]:
        if item.is_symlink() or getattr(item, 'is_junction', lambda: False)():
            raise ExportError('Linked environment resource requires an explicit adapter: ' + path.name)

def _load(path):
    _regular(path)
    if path.stat().st_size > 4 * 1024 * 1024:
        raise ExportError('Configuration exceeds 4 MiB: ' + path.name)
    content = path.read_bytes()
    assert_private_values_absent(content, path.name)
    try:
        return json.loads(content)
    except (ValueError, UnicodeDecodeError):
        prefix = os.environ.get('DSH_PACK_CONFIG_READER')
        if not prefix:
            raise ExportError('Static YAML requires the desktop configuration reader; executable YAML is unsupported')
        command = json.loads(prefix)
        if not isinstance(command, list) or not command or not all(isinstance(v, str) and v for v in command):
            raise ExportError('Invalid configuration reader')
        result = subprocess.run([*command, str(path)], capture_output=True, timeout=20,
                                env=dict(os.environ, ELECTRON_RUN_AS_NODE='1'))
        if result.returncode:
            raise ExportError('Cannot parse static configuration: ' + path.name)
        return json.loads(result.stdout)

def _json(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()

class Inventory:
    def __init__(self, profile):
        self.profile = Path(profile).absolute()
        self.items = {}
        self.documents = {}
        self.errors = []

    def add(self, value, context):
        path = _source(value)
        if path is None:
            return
        # PATH lists are independent bindings, never a fictitious single file.
        if ';' in value and not value.startswith('file:'):
            for part in value.split(';'):
                self.add(part, context)
            return
        absolute = str(path.absolute())
        key = _digest(os.path.normcase(absolute).encode())[:20]
        if key in self.items:
            if value not in self.items[key]['references']:
                self.items[key]['references'].append(value)
            return
        kind = 'skill' if 'skill' in context.lower() else 'compatibility' if value.startswith('file:') else 'mcp' if path.suffix.lower() in TEXT else 'tool'
        mode = 'bind'
        reason = 'target-binding-required'
        try:
            _regular(path)
            if path.is_file() and path.suffix.lower() in TEXT:
                mode, reason = 'embedded', 'static-text-resource'
            elif path.is_dir() and kind == 'skill':
                mode, reason = 'embedded', 'text-skill-directory'
            if not path.exists():
                reason = 'source-missing'
        except ExportError:
            reason = 'linked-source'
        self.items[key] = {'id': key, 'label': path.name or absolute, 'kind': kind,
                           'source': absolute, 'references': [value], 'mode': mode,
                           'reason': reason, 'pathType': 'directory' if path.is_dir() else 'file'}
        if len(self.items) > 300:
            raise ExportError('Environment inventory exceeds 300 resources')
        # Close over nested static patch references and file-URI JS imports.
        if mode == 'embedded' and path.is_file():
            try:
                if path.suffix.lower() in {'.yml', '.yaml', '.json'}:
                    self.walk(_load(path), str(path))
                else:
                    text = path.read_text(encoding='utf-8')
                    for ref in URI.findall(text):
                        self.add(ref, str(path))
            except (OSError, ValueError, ExportError) as error:
                self.items[key].update(mode='bind', reason='static-adapter-required')

    def walk(self, value, context=''):
        if isinstance(value, str):
            self.add(value, context)
        elif isinstance(value, list):
            for item in value:
                self.walk(item, context)
        elif isinstance(value, dict):
            for name, item in value.items():
                self.walk(item, context + '/' + name)

    def scan(self):
        for name in ('cordis.yml', 'cordis.patch.yml'):
            path = self.profile / name
            value = _load(path) if path.exists() else []
            if not isinstance(value, list):
                raise ExportError('Environment configuration must be a static Loader array')
            self.documents[name] = value
            self.walk(value, name)
        return self

def catalog(profile):
    inventory = Inventory(profile).scan()
    return {'schemaVersion': 1, 'resources': list(inventory.items.values()),
            'limitations': ['external-software-not-installed', 'dynamic-configuration-not-supported', 'runtime-functionality-requires-verification']}

def _replace(value, replacements):
    if isinstance(value, str):
        for source, target in replacements:
            value = value.replace(source, target)
        return value
    if isinstance(value, list):
        return [_replace(item, replacements) for item in value]
    if isinstance(value, dict):
        return {key: _replace(item, replacements) for key, item in value.items()}
    return value

def collect(profile, selection):
    inv = Inventory(profile).scan()
    if not isinstance(selection, (tuple, list)):
        raise ExportError('Environment selection must be an array')
    selected = {}
    for choice in selection:
        if not isinstance(choice, dict) or set(choice) != {'id', 'mode'} or choice.get('mode') not in {'embedded', 'bind'}:
            raise ExportError('Invalid environment selection')
        if choice['id'] in selected or choice['id'] not in inv.items:
            raise ExportError('Environment inventory changed; refresh selection')
        selected[choice['id']] = choice['mode']
    if set(selected) != set(inv.items):
        raise ExportError('Every referenced resource needs an explicit migration choice')
    replacements = []
    rows = []
    files = {}
    total = 0
    for key, item in inv.items.items():
        mode = selected[key]
        if mode == 'embedded' and item['mode'] != 'embedded':
            raise ExportError('Resource needs target binding: ' + item['label'])
        for ref in item['references']:
            replacements.append((ref, f'__CRATE_{"URI" if ref.startswith("file:") else "PATH"}_{key}__'))
        row = {k: item[k] for k in ('id', 'label', 'kind', 'pathType')}
        row.update(mode=mode, files={})
        source = Path(item['source'])
        if mode == 'embedded':
            candidates = [source] if source.is_file() else sorted(source.rglob('*'))
            for path in candidates:
                _regular(path)
                rel = path.relative_to(source).as_posix() if source.is_dir() else source.name
                if any(part.casefold() in FORBIDDEN or '.bak' in part.casefold() for part in Path(rel).parts):
                    raise ExportError('Resource directory includes private or runtime files: ' + item['label'])
                if path.is_dir():
                    continue
                if not path.is_file() or path.suffix.lower() not in TEXT:
                    raise ExportError('Resource needs a format-specific adapter: ' + path.name)
                if path.stat().st_size > 4 * 1024 * 1024:
                    raise ExportError('Resource file exceeds 4 MiB: ' + path.name)
                relative = f'{ROOT}/{key}/' + safe_relative(rel)
                content = path.read_bytes()
                assert_private_values_absent(content, path.name)
                total += len(content)
                if len(files) >= MAX_FILES or total > MAX_BYTES:
                    raise ExportError('Environment resources exceed file or size limit')
                files[relative] = content
                row['files'][relative] = ''
            if not row['files']:
                raise ExportError('Empty resource directory: ' + item['label'])
            row['entry'] = f'{ROOT}/{key}' + ('' if source.is_dir() else '/' + source.name)
        rows.append(row)
    replacements.sort(key=lambda pair: len(pair[0]), reverse=True)
    for name, value in inv.documents.items():
        files[name] = _json(_replace(value, replacements))
    for row in rows:
        source = Path(inv.items[row['id']]['source'])
        for name in row['files']:
            suffix = Path(name).suffix.lower()
            if suffix in {'.json', '.yml', '.yaml'}:
                original = source if source.is_file() else source / Path(name).relative_to(f'{ROOT}/{row["id"]}')
                files[name] = _json(_replace(_load(original), replacements))
            else:
                # Only file-URI references are rewritten inside executable text.
                # Arbitrary shell/code path rewriting would change semantics.
                text = files[name].decode('utf-8')
                files[name] = _replace(text, [(a, b) for a, b in replacements if a.startswith('file:')]).encode()
            row['files'][name] = _digest(files[name])
    metadata = {'schemaVersion': 1, 'resources': rows,
                'configuration': ['cordis.yml', 'cordis.patch.yml']}
    validate(metadata, files)
    return files, metadata

def validate(metadata, files=None):
    def fail():
        raise SchemaValidationError('Invalid environment resource manifest or payload')
    if not isinstance(metadata, dict) or set(metadata) != {'schemaVersion', 'resources', 'configuration'} or metadata['schemaVersion'] != 1:
        fail()
    if metadata['configuration'] != ['cordis.yml', 'cordis.patch.yml'] or not isinstance(metadata['resources'], list) or len(metadata['resources']) > 300:
        fail()
    seen, owned = set(), set()
    for row in metadata['resources']:
        if not isinstance(row, dict) or not {'id', 'label', 'kind', 'mode', 'pathType', 'files'} <= set(row) or set(row) - {'id', 'label', 'kind', 'mode', 'pathType', 'files', 'entry'}:
            fail()
        key = row['id']
        if not isinstance(key, str) or not re.fullmatch('[a-f0-9]{20}', key) or key in seen:
            fail()
        seen.add(key)
        if row['kind'] not in {'tool', 'skill', 'mcp', 'compatibility'} or row['mode'] not in {'embedded', 'bind'} or row['pathType'] not in {'file', 'directory'} or not isinstance(row['label'], str) or len(row['label']) > 255 or not isinstance(row['files'], dict):
            fail()
        if row['mode'] == 'bind':
            if row['files'] or 'entry' in row:
                fail()
        else:
            if not row['files'] or not isinstance(row.get('entry'), str):
                fail()
            entry = row['entry']
            if entry != f'{ROOT}/{key}' and not entry.startswith(f'{ROOT}/{key}/'):
                fail()
            safe_relative(entry)
            if row['pathType'] == 'file' and entry not in row['files']:
                fail()
        for name, digest in row['files'].items():
            safe_relative(name)
            if not name.startswith(f'{ROOT}/{key}/') or name in owned or not isinstance(digest, str) or not re.fullmatch('[a-f0-9]{64}', digest):
                fail()
            owned.add(name)
            if files is not None and (name not in files or _digest(files[name]) != digest):
                fail()
    if files is not None:
        if {name for name in files if name.startswith(ROOT + '/')} != owned:
            fail()
        for name in metadata['configuration']:
            if name not in files:
                fail()
        for name in [*owned, *metadata['configuration']]:
            for match in TOKEN.finditer(files[name].decode('utf-8')):
                if match[2] not in seen:
                    fail()

def binding_findings(metadata, bindings):
    if not isinstance(bindings, dict):
        return [{'code': 'ENVIRONMENT_BINDINGS_INVALID', 'message': 'Environment bindings must be an object'}]
    required = {r['id']: r for r in metadata['resources'] if r['mode'] == 'bind'}
    findings = []
    for key in set(bindings) - set(required):
        findings.append({'code': 'ENVIRONMENT_BINDING_UNKNOWN', 'message': 'Unknown resource binding', 'resourceId': key})
    for key, row in required.items():
        value = bindings.get(key)
        path = _source(value)
        valid = path is not None and isinstance(value, str) and not any(c in value for c in '\"\'\n\r;')
        if valid:
            valid = path.is_file() if row['pathType'] == 'file' else path.is_dir()
        if not valid:
            findings.append({'code': 'ENVIRONMENT_BINDING_REQUIRED', 'message': 'Bind target ' + row['pathType'] + ': ' + row['label'], 'resourceId': key})
    return findings

def relocate(metadata, files, target_profile, bindings):
    validate(metadata, files)
    if binding_findings(metadata, bindings):
        raise ExportError('Environment resources require valid target bindings')
    paths = {r['id']: Path(bindings[r['id']]) if r['mode'] == 'bind' else Path(target_profile) / r['entry'] for r in metadata['resources']}
    def substitute(text):
        return TOKEN.sub(lambda m: paths[m[2]].absolute().as_uri() if m[1] == 'URI' else paths[m[2]].absolute().as_posix(), text)
    rewritten = dict(files)
    for name in [*metadata['configuration'], *(n for r in metadata['resources'] for n in r['files'])]:
        text = files[name].decode('utf-8')
        if Path(name).suffix.lower() in {'.json', '.yaml', '.yml'}:
            # Values only; JSON encoding protects destination quotes/backslashes.
            value = json.loads(text)
            pairs = [(m[0], substitute(m[0])) for m in TOKEN.finditer(text)]
            rewritten[name] = _json(_replace(value, pairs))
        else:
            rewritten[name] = substitute(text).encode()
    return rewritten
