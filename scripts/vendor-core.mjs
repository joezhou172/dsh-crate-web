import { cp, mkdir, rm } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const script = fileURLToPath(import.meta.url)
const pluginRoot = resolve(dirname(script), '..')
const repositoryRoot = resolve(pluginRoot, '..', '..')
const source = resolve(repositoryRoot, 'src', 'dsh_pack')
const destination = resolve(pluginRoot, 'core', 'dsh_pack')

await mkdir(destination, { recursive: true })
await rm(destination, { recursive: true, force: true })
await cp(source, destination, {
  recursive: true,
  force: true,
  filter: path => !path.includes(`${process.platform === 'win32' ? '\\' : '/'}__pycache__`) && !path.endsWith('.pyc'),
})
