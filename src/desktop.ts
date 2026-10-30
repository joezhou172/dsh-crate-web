/** Read the official Desktop's bundled sources without changing its installation. */
import { createHash, randomUUID } from 'node:crypto'
import { readFileSync } from 'node:fs'
import { mkdir, readFile, readdir, rename, rm, writeFile } from 'node:fs/promises'
import { dirname, join, resolve } from 'node:path'

export function desktopRuntimeRoot(argv = process.argv): string | undefined {
  const entry = (argv[1] ?? '').replaceAll('\\', '/')
  return entry.includes('/@deepseek-ai/dsh-desktop-host/') && argv[2]
    ? resolve(argv[2]) : undefined
}

export function desktopRuntimeVersion(): string | undefined {
  const root = desktopRuntimeRoot()
  if (!root) return undefined
  try {
    const pkg = JSON.parse(readFileSync(join(root, 'node_modules', '@deepseek-ai', 'dsh', 'package.json'), 'utf8'))
    return typeof pkg.version === 'string' ? pkg.version : undefined
  } catch { return undefined }
}

export function rejectRequest(connection: { requestRejection(request: unknown): number | undefined } | undefined,
  req: unknown, res: { writeHead(status: number): unknown; end(): unknown }): boolean {
  const status = connection?.requestRejection(req) ?? (connection ? undefined : 503)
  if (status === undefined) return false
  res.writeHead(status)
  res.end()
  return true
}

export async function copyPackage(source: string, target: string): Promise<void> {
  await mkdir(target, { recursive: true })
  for (const entry of await readdir(source, { withFileTypes: true })) {
    if (['node_modules', '.git', 'cache', 'logs'].includes(entry.name)) continue
    const input = join(source, entry.name)
    const output = join(target, entry.name)
    if (entry.isDirectory()) await copyPackage(input, output)
    else if (entry.isFile()) await writeFile(output, await readFile(input))
    else throw new Error(`Unsupported link in Desktop package: ${entry.name}`)
  }
}

/** Public evidence for dependencies already supplied by this exact host. */
export async function writeDesktopHostBundles(home: string, runtime = desktopRuntimeRoot()): Promise<string | undefined> {
  if (!runtime) return undefined
  const modules = join(runtime, 'node_modules')
  const bundles: Record<string, unknown> = {}
  const hashFiles = async (root: string, prefix = ''): Promise<Record<string, string>> => {
    const result: Record<string, string> = {}
    for (const entry of await readdir(join(root, prefix), { withFileTypes: true })) {
      if (['node_modules', '.git', 'cache', 'logs'].includes(entry.name)) continue
      const relative = prefix ? `${prefix}/${entry.name}` : entry.name
      if (entry.isDirectory()) Object.assign(result, await hashFiles(root, relative))
      else if (entry.isFile()) result[relative] = createHash('sha256').update(await readFile(join(root, relative))).digest('hex')
      else throw new Error('Unsupported link in official host Bundle evidence')
    }
    return result
  }
  for (const entry of await readdir(join(modules, '@deepseek-ai'), { withFileTypes: true })) {
    if (!entry.isDirectory()) continue
    const root = join(modules, '@deepseek-ai', entry.name)
    let manifest: Record<string, any>
    try { manifest = JSON.parse(await readFile(join(root, 'package.json'), 'utf8')) }
    catch { continue }
    if (!manifest.dsh?.bundle?.patch) continue
    const dependencies: Record<string, string> = {}
    for (const name of Object.keys({ ...manifest.dependencies, ...manifest.optionalDependencies })) {
      try {
        const dependency = JSON.parse(await readFile(join(modules, ...name.split('/'), 'package.json'), 'utf8'))
        if (typeof dependency.version === 'string') dependencies[name] = dependency.version
      } catch { /* Core blocks missing required host dependencies explicitly. */ }
    }
    bundles[`@deepseek-ai/${entry.name}`] = { manifest, dependencies, files: await hashFiles(root) }
  }
  const content = JSON.stringify({ schemaVersion: 1, runtime, bundles })
  const digest = createHash('sha256').update(content).digest('hex')
  const destination = join(home, '.dsh-pack', 'runtime-sources', `${digest}-host-bundles.json`)
  await mkdir(dirname(destination), { recursive: true })
  // Contents are public package metadata and hashes, never credentials.
  try { if (await readFile(destination, 'utf8') === content) return destination } catch { /* First snapshot. */ }
  const staging = `${destination}.${randomUUID()}.tmp`
  await writeFile(staging, content, { flag: 'wx' })
  try { await rename(staging, destination) }
  catch (error) { if (await readFile(destination, 'utf8').catch(() => '') !== content) throw error }
  finally { await rm(staging, { force: true }) }
  return destination
}

/** Electron can read ASAR; Python/npm cannot. Materialize only public package files. */
let materializing: Promise<unknown> = Promise.resolve()

export async function materializeDesktopModules(home: string, selectedNames: string[] = []): Promise<string | undefined> {
  const pending = materializing.then(() => materializeDesktopModulesOnce(home, selectedNames))
  materializing = pending.catch(() => undefined)
  return pending
}

async function materializeDesktopModulesOnce(home: string, selectedNames: string[]): Promise<string | undefined> {
  const runtime = desktopRuntimeRoot()
  if (!runtime) return undefined
  const modules = join(runtime, 'node_modules')
  const version = await readFile(join(modules, '@deepseek-ai', 'dsh', 'package.json'), 'utf8')
  const identity = createHash('sha256').update(runtime).update(version).digest('hex').slice(0, 20)
  const destination = join(home, '.dsh-pack', 'runtime-sources', identity, 'node_modules')
  const names = new Set(selectedNames.filter(name => /^@deepseek-ai\/[A-Za-z0-9._-]+$/.test(name)))
  const profiles = join(home, 'profiles')
  for (const entry of await readdir(profiles, { withFileTypes: true })) {
    if (!entry.isDirectory() || entry.name === 'node_modules' || entry.name.startsWith('.')) continue
    try {
      const pkg = JSON.parse(await readFile(join(profiles, entry.name, 'package.json'), 'utf8'))
      for (const name of [...Object.keys(pkg.dependencies ?? {}), ...(pkg.dsh?.profile?.bundles ?? [])]) {
        if (typeof name === 'string' && /^@deepseek-ai\/[A-Za-z0-9._-]+$/.test(name)) names.add(name)
      }
    } catch {
      // Another Profile must not block this operation. Core validates the
      // explicitly requested Profile and reports its own malformed manifest.
      continue
    }
  }
  for (const name of names) {
    const source = join(modules, ...name.split('/'))
    let manifest: string
    try { manifest = await readFile(join(source, 'package.json'), 'utf8') }
    catch (error) {
      if ((error as NodeJS.ErrnoException).code === 'ENOENT') continue
      throw error
    }
    const target = join(destination, ...name.split('/'))
    try {
      if (await readFile(join(target, 'package.json'), 'utf8') === manifest) continue
    } catch { /* First use in this isolated Home. */ }
    const staging = `${target}.staging-${process.pid}`
    await rm(staging, { recursive: true, force: true })
    try {
      await copyPackage(source, staging)
      await mkdir(dirname(target), { recursive: true })
      await rm(target, { recursive: true, force: true })
      // Windows scanners can briefly hold a freshly copied package open.
      // Retry only sharing/permission errors, then surface the actual failure.
      for (let attempt = 0; ; attempt += 1) {
        try { await rename(staging, target); break }
        catch (error) {
          if (attempt >= 4 || !['EPERM', 'EACCES', 'EBUSY'].includes((error as NodeJS.ErrnoException).code ?? '')) throw error
          await new Promise(done => setTimeout(done, 100 * (attempt + 1)))
        }
      }
    } finally { await rm(staging, { recursive: true, force: true }) }
  }
  return destination
}
