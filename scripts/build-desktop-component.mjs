/** Fixed public component; contains program sources only, no local data or credentials. */
import { readFile, writeFile, mkdir } from 'node:fs/promises'
import { createHash } from 'node:crypto'
import { join } from 'node:path'
const root = new URL('../', import.meta.url)
const version = JSON.parse(await readFile(new URL('package.json', root), 'utf8')).version
if (!/^\d+\.\d+\.\d+-preview\.\d+$/.test(version)) throw Error('Desktop component requires an explicit Preview release version')
const id = 'desktop-multiversion-bootstrap-3'
const supportedBuilds = JSON.parse(await readFile(new URL('packaging/desktop-bootstrap/builds.json', root), 'utf8'))
const files = ['desktop-profile-adapter.mjs', 'desktop-instances.mjs', 'desktop-maintenance.mjs',
  'scripts/desktop-profile-patch.py', 'scripts/desktop-patch-launcher.py', 'scripts/desktop-setup-worker.py', 'packaging/desktop-bootstrap/builds.json']
const payload = { id, files: {} }
for (const name of files) payload.files[name] = (await readFile(new URL(name, root))).toString('base64')
const bytes = Buffer.from(JSON.stringify(payload))
const sha256 = createHash('sha256').update(bytes).digest('hex')
await mkdir(new URL('packaging/desktop-bootstrap/', root), { recursive: true })
await mkdir(new URL('work/desktop-bootstrap/', root), { recursive: true })
await writeFile(new URL(`work/desktop-bootstrap/${id}.json`, root), bytes)
await writeFile(new URL('packaging/desktop-bootstrap/component.json', root), bytes)
await writeFile(new URL('packaging/desktop-bootstrap/manifest.json', root), JSON.stringify({
  schemaVersion: 1, id, url: `https://github.com/joezhou172/dsh-crate-web/releases/download/v${version}/${id}.json`,
  sha256, maxBytes: 2 * 1024 * 1024, files,
  supportedBuilds,
}, null, 2) + '\n')
console.log(JSON.stringify({ id, sha256, bytes: bytes.length }))
