import { access, cp, mkdir, rm } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const script = fileURLToPath(import.meta.url)
const pluginRoot = resolve(dirname(script), '..')
const repositoryRoot = resolve(pluginRoot, '..', '..')
// The dsh-crate-web workspace tracks core/dsh_pack in-repo and it is the
// authoritative source. The legacy parent-repo path is only a bootstrap
// fallback for fresh clones that do not carry core/dsh_pack yet.
const inRepoSource = resolve(pluginRoot, 'core', 'dsh_pack')
const legacySource = resolve(repositoryRoot, 'src', 'dsh_pack')
let source = inRepoSource
try { await access(inRepoSource) } catch { source = legacySource }
const destination = resolve(pluginRoot, 'core', 'dsh_pack')
if (source === destination) {
  console.log('[vendor-core] in-repo core/dsh_pack is authoritative; nothing to vendor')
} else {
  await mkdir(destination, { recursive: true })
  await rm(destination, { recursive: true, force: true })
  await cp(source, destination, {
    recursive: true,
    force: true,
    filter: path => !path.includes(`${process.platform === 'win32' ? '\\' : '/'}__pycache__`) && !path.endsWith('.pyc'),
  })
}
