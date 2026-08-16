import { access, readdir, readFile, writeFile } from 'node:fs/promises'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const script = fileURLToPath(import.meta.url)
const pluginRoot = resolve(dirname(script), '..')
const runtimeRoot = resolve(pluginRoot, 'runtime', 'python')
const coreEntry = resolve(pluginRoot, 'core', 'dsh_pack', '__main__.py')

await access(resolve(runtimeRoot, 'python.exe'))
await access(coreEntry)
const pthFiles = (await readdir(runtimeRoot)).filter(name => name.endsWith('._pth'))
if (pthFiles.length !== 1) throw new Error(`expected one Python ._pth file, found ${pthFiles.length}`)

const pthPath = join(runtimeRoot, pthFiles[0])
const corePath = '..\\..\\core'
const current = await readFile(pthPath, 'utf8')
const lines = current.split(/\r?\n/)
if (!lines.includes(corePath)) {
  const insertAt = lines.findIndex(line => line.startsWith('#'))
  lines.splice(insertAt < 0 ? lines.length : insertAt, 0, corePath)
  await writeFile(pthPath, `${lines.join('\r\n').replace(/\r\n+$/u, '\r\n')}`, 'utf8')
}
