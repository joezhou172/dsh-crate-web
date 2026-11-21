/** Background preparation only. Program files are changed by the separately confirmed worker. */
import { createHash, randomUUID } from 'node:crypto'
import * as nodeFs from 'node:fs'
import { createRequire } from 'node:module'
import { access, cp, mkdir, readFile, rename, writeFile } from 'node:fs/promises'
import { dirname, join, resolve } from 'node:path'
import { spawn } from 'node:child_process'
import { tmpdir } from 'node:os'

// Electron treats .asar as a virtual directory. Checksums and installation probes need physical bytes.
const physicalFs: typeof nodeFs = (() => {
  try { return createRequire(import.meta.url)('original-fs') } catch { return nodeFs }
})()

export const stableVersion = (value: unknown): value is string => typeof value === 'string' && /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/.test(value)
export function newerStable(candidate: string, current: string) {
  const a = candidate.split('.').map(BigInt), base = current.split('-')[0]
  if (!stableVersion(base)) return false
  const b = base.split('.').map(BigInt)
  for (let i = 0; i < 3; i++) if (a[i] !== b[i]) return a[i] > b[i]
  return current.includes('-')
}
export function selectStable(metadata: any, current: string) {
  // Only the maintainer's stable channel can advertise an update. A preview tag is never read.
  const version = metadata?.['dist-tags']?.latest
  const entry = metadata?.versions?.[version]
  return stableVersion(version) && entry?.version === version && !entry.deprecated && newerStable(version, current) ? version : null
}
export async function boundedDownload(url: string, limit: number, fetcher: typeof fetch = fetch): Promise<Buffer> {
  if (new URL(url).protocol !== 'https:') throw Error('Only HTTPS component sources are allowed')
  const response = await fetcher(url, { signal: AbortSignal.timeout(45000), credentials: 'omit' })
  if (!response.ok || !response.body) throw Error(`Download failed: HTTP ${response.status}`)
  if (response.url && new URL(response.url).protocol !== 'https:') throw Error('Insecure redirect rejected')
  const reader = response.body.getReader(), chunks: Uint8Array[] = []; let size = 0
  try {
    while (true) { const { done, value } = await reader.read(); if (done) break; size += value.length; if (size > limit) throw Error('Download exceeds size limit'); chunks.push(value) }
  } finally { await reader.cancel().catch(() => {}); reader.releaseLock() }
  return Buffer.concat(chunks)
}
const sha = (data: Buffer) => createHash('sha256').update(data).digest('hex')
const workerDirectory = (home: string, id: string) => join(tmpdir(), `crate-${sha(Buffer.from(resolve(home))).slice(0, 8)}-${id}`)
async function fileHash(file: string) { const hash = createHash('sha256'); for await (const chunk of physicalFs.createReadStream(file)) hash.update(chunk); return hash.digest('hex') }
async function noLinks(path: string) {
  for (let current = resolve(path);;) {
    const info = await physicalFs.promises.lstat(current).catch((e: any) => { if (e.code !== 'ENOENT') throw e; return null })
    if (info?.isSymbolicLink()) throw Error('Linked component or installation paths are not supported')
    const parent = dirname(current); if (parent === current) break; current = parent
  }
}
type Options = { home: string; packageRoot: string; desktopRoot?: string; resolveDesktop?: () => Promise<string | undefined>; platform?: string; fetcher?: typeof fetch }
export class CrateSetup {
  state: any = { desktop: { status: 'checking' }, update: { status: 'checking' } }
  private preparing?: Promise<void>
  private checking?: Promise<void>
  private scheduling = false
  private manifest: any
  private cache = ''
  private options: Options
  constructor(options: Options) { this.options = options }
  private async config() {
    if (!this.manifest) this.manifest = JSON.parse(await readFile(join(this.options.packageRoot, 'packaging/desktop-bootstrap/manifest.json'), 'utf8'))
    return this.manifest
  }
  async status() {
    const task = join(this.options.home, '.dsh-pack/desktop-setup/task.json')
    let operation: any
    try { await noLinks(task); operation = JSON.parse(await readFile(task, 'utf8')) } catch (e: any) { if (e.code !== 'ENOENT') operation = { status: 'failed', error: String(e) } }
    if (['preparing', 'waiting-exit'].includes(operation?.status) && /^[0-9a-f-]{36}$/.test(operation.id)) {
      const job = workerDirectory(this.options.home, operation.id)
      try {
        await noLinks(job)
        const worker = JSON.parse(await readFile(join(job, 'worker.json'), 'utf8'))
        if (Number.isSafeInteger(worker.pid) && worker.pid > 0) {
          try { process.kill(worker.pid, 0) } catch (error: any) {
            if (error.code === 'ESRCH') operation = { ...operation, status: 'failed', error: 'Desktop setup worker exited before completing. ' + await readFile(join(job, 'worker.log'), 'utf8').catch(() => '') }
          }
        }
      } catch { /* The child may not yet have acknowledged spawn; retain the bounded deadline below. */ }
    }
    if (['preparing', 'waiting-exit'].includes(operation?.status) && Date.now() - operation.startedAt > 180000) operation = { ...operation, status: 'failed', error: 'Setup worker did not finish; no success was confirmed. Retry preparation.' }
    return { ...this.state, operation }
  }
  start() { void this.prepare(); void this.checkUpdates() }
  prepare(): Promise<void> {
    if (this.preparing) return this.preparing
    this.preparing = this.prepareOnce().catch(error => { this.state.desktop = { status: 'failed', error: String(error) } }).finally(() => { this.preparing = undefined })
    return this.preparing
  }
  private async prepareOnce() {
    this.state.desktop = { status: 'checking' }
    const { packageRoot, home } = this.options
    const root = this.options.desktopRoot ?? await this.options.resolveDesktop?.()
    this.options.desktopRoot = root
    if ((this.options.platform ?? process.platform) !== 'win32' || !root) { this.state.desktop = { status: 'not-applicable' }; return }
    const manifest = await this.config()
    await noLinks(root)
    await access(join(root, 'DeepSeek Harness.exe'))
    const archive = join(root, 'resources/app.asar'); await noLinks(archive)
    const current = await fileHash(archive)
    let receipt: any
    try { receipt = JSON.parse(await readFile(join(root, 'resources/crate-profile-patch.json'), 'utf8')) } catch { /* Unpatched installation. */ }
    const builds: Record<string, string> = manifest.supportedBuilds ?? { '0.2.2-rc.1': manifest.originalSha256 }
    const original = receipt?.version ? builds[receipt.version] : manifest.supportedBuilds ? undefined : manifest.originalSha256
    const knownPatch = !!original && receipt?.originalSha256 === original && receipt?.patchedSha256 === current
    if (knownPatch && await fileHash(join(root, 'resources/app.asar.crate-original')) !== original) throw Error('Original Desktop backup is invalid')
    if (!Object.values(builds).includes(current) && !knownPatch) { this.state.desktop = { status: 'unsupported', root }; return }
    if (knownPatch && receipt.componentId === manifest.id) { this.state.desktop = { status: 'installed', root, componentId: manifest.id }; return }
    this.cache = join(home, '.dsh-pack/desktop-setup/cache', manifest.sha256)
    await noLinks(this.cache); await mkdir(this.cache, { recursive: true })
    const payloadPath = join(this.cache, 'component.json'); await noLinks(payloadPath)
    let bytes: Buffer = await readFile(payloadPath).catch(() => Buffer.alloc(0))
    if (sha(bytes) !== manifest.sha256) {
      const bundled = await readFile(join(packageRoot, 'packaging/desktop-bootstrap/component.json')).catch(() => Buffer.alloc(0))
      if (sha(bundled) === manifest.sha256) bytes = bundled
    }
    if (sha(bytes) !== manifest.sha256) {
      this.state.desktop = { status: 'downloading', root }
      bytes = await boundedDownload(manifest.url, manifest.maxBytes, this.options.fetcher)
      if (sha(bytes) !== manifest.sha256) throw Error('Desktop component integrity check failed')
      const temp = join(this.cache, `${randomUUID()}.tmp`); await writeFile(temp, bytes, { flag: 'wx' }); await rename(temp, payloadPath)
    }
    // Preserve the verified bundled payload for the separate restart worker too.
    if (sha(await readFile(payloadPath).catch(() => Buffer.alloc(0))) !== manifest.sha256) {
      const temp = join(this.cache, `${randomUUID()}.tmp`); await writeFile(temp, bytes, { flag: 'wx' }); await rename(temp, payloadPath)
    }
    const payload = JSON.parse(bytes.toString('utf8'))
    if (payload.id !== manifest.id || !payload.files || Object.keys(payload.files).sort().join('\n') !== [...manifest.files].sort().join('\n')) throw Error('Unexpected Desktop component contents')
    for (const name of manifest.files) {
      if (!/^[a-zA-Z0-9_.-]+(?:\/[a-zA-Z0-9_.-]+)*$/.test(name) || name.split('/').some((p: string) => p === '..' || p === '.')) throw Error('Unsafe component path')
      const target = join(this.cache, name); await noLinks(target); await mkdir(dirname(target), { recursive: true })
      await writeFile(target, Buffer.from(payload.files[name], 'base64'))
    }
    await access(join(packageRoot, 'runtime/python/python.exe'))
    this.state.desktop = { status: 'ready', root, componentId: manifest.id, update: !!knownPatch }
  }
  checkUpdates(force = false): Promise<void> {
    if (this.checking) return this.checking
    this.checking = this.checkOnce(force).catch(error => { this.state.update = { ...this.state.update, status: 'failed', error: String(error) } }).finally(() => { this.checking = undefined })
    return this.checking
  }
  private async checkOnce(force: boolean) {
    const current = JSON.parse(await readFile(join(this.options.packageRoot, 'package.json'), 'utf8')).version
    this.state.update = { status: 'checking', current }
    const path = join(this.options.home, '.dsh-pack/desktop-setup/stable-update.json')
    await noLinks(path)
    let cached: any
    try { cached = JSON.parse(await readFile(path, 'utf8')) } catch { /* First check. */ }
    if (!force && cached?.current === current && Date.now() >= cached.checkedAt && Date.now() - cached.checkedAt < 6 * 3600000 && (cached.available === null || stableVersion(cached.available) && newerStable(cached.available, current))) { this.state.update = cached; return }
    const bytes = await boundedDownload('https://registry.npmjs.org/dsh-crate-web', 8 * 1024 * 1024, this.options.fetcher)
    const metadata = JSON.parse(bytes.toString('utf8')), available = selectStable(metadata, current)
    const result = { status: 'checked', current, available, deprecated: metadata.versions?.[current]?.deprecated || null, preview: current.includes('-'), checkedAt: Date.now(), channel: 'stable' }
    await mkdir(dirname(path), { recursive: true }); await writeFile(path, JSON.stringify(result)); this.state.update = result
  }
  async schedule(confirm: boolean) {
    if (confirm !== true) throw Error('Confirm normal exit and restart before applying Desktop support')
    if (this.scheduling) throw Error('Desktop setup is already being prepared')
    this.scheduling = true
    try {
      const previous = (await this.status()).operation
      if (['preparing', 'waiting-exit', 'applying'].includes(previous?.status)) throw Error('Desktop setup is already pending')
      await this.prepare()
      if (this.state.desktop.status !== 'ready') throw Error('Verified Desktop component is not ready')
      const manifest = await this.config(), id = randomUUID()
      const base = join(this.options.home, '.dsh-pack/desktop-setup'), job = workerDirectory(this.options.home, id)
      await noLinks(job); await mkdir(dirname(job), { recursive: true }); await mkdir(job)
      // Reconstruct from the pinned payload, not potentially modified extracted cache files.
      const payloadBytes = await readFile(join(this.cache, 'component.json'))
      if (sha(payloadBytes) !== manifest.sha256) throw Error('Cached component changed')
      const payload = JSON.parse(payloadBytes.toString('utf8'))
      for (const name of manifest.files) { const target = join(job, name); await mkdir(dirname(target), { recursive: true }); await writeFile(target, Buffer.from(payload.files[name], 'base64')) }
      await cp(join(this.options.packageRoot, 'runtime/python'), join(job, 'runtime/python'), { recursive: true, dereference: false })
      const task = { status: 'preparing', id, startedAt: Date.now(), root: this.options.desktopRoot, componentId: manifest.id, report: join(base, 'task.json') }
      await noLinks(task.report)
      await writeFile(join(job, 'job.json'), JSON.stringify(task)); await writeFile(task.report, JSON.stringify(task))
      const log = nodeFs.openSync(join(job, 'worker.log'), 'wx')
      const child = spawn(join(job, 'runtime/python/python.exe'), ['-B', join(job, 'scripts/desktop-setup-worker.py'), join(job, 'job.json')], { cwd: job, detached: true, windowsHide: true, stdio: ['ignore', log, log], env: { ...process.env, PYTHONUTF8: '1', PYTHONDONTWRITEBYTECODE: '1' } })
      nodeFs.closeSync(log)
      try { await new Promise<void>((accept, reject) => { child.once('spawn', accept); child.once('error', reject) }); child.unref(); await writeFile(join(job, 'worker.json'), JSON.stringify({ pid: child.pid })) }
      catch (error) { await writeFile(task.report, JSON.stringify({ ...task, status: 'failed', error: String(error) })); throw error }
      // Do not tell the user to exit before the independent worker has captured the original launch arguments.
      const deadline = Date.now() + 15000
      while (Date.now() < deadline) {
        const operation = (await this.status()).operation
        if (operation?.id === id && operation.status === 'waiting-exit') return operation
        if (operation?.status === 'failed') throw Error(operation.error || 'Desktop setup worker failed')
        await new Promise(resolve => setTimeout(resolve, 200))
      }
      throw Error('Desktop setup worker did not acknowledge preparation; do not exit yet. Check the setup status before retrying.')
    } finally { this.scheduling = false }
  }
}

export async function locateDesktopRoot(runtime: string | undefined): Promise<string | undefined> {
  if (!runtime || process.platform !== 'win32') return
  const failures: string[] = []
  // Electron utilityProcess runs under the Desktop executable; runtime sources may be extracted elsewhere.
  for (const origin of [dirname(process.execPath), runtime]) {
    for (let candidate = resolve(origin), count = 0; count < 6; count++, candidate = dirname(candidate)) {
      try { await physicalFs.promises.access(join(candidate, 'DeepSeek Harness.exe')); await physicalFs.promises.access(join(candidate, 'resources/app.asar')); await noLinks(candidate); return await physicalFs.promises.realpath(candidate) } catch (error: any) { if (error.code !== 'ENOENT' && error.code !== 'ENOTDIR') failures.push(String(error)) }
    }
  }
  throw Error(`Official Desktop detected, but its installation directory could not be verified. Executable: ${process.execPath}; runtime: ${runtime}; checks: ${failures.join('; ')}`)
}
