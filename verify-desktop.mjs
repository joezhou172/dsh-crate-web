/** Owned, zero-model Desktop Verify controller. Only stdio protocol and local CDP. */
import { createRequire } from 'node:module'
import { spawn } from 'node:child_process'
import { createInterface } from 'node:readline'
import { createHash, randomUUID } from 'node:crypto'
import { open, mkdir, readdir, lstat, readFile, writeFile } from 'node:fs/promises'
import { createServer } from 'node:net'
import { dirname, isAbsolute, join, relative, resolve } from 'node:path'
import { pathToFileURL } from 'node:url'
import { inspectorApplicability } from './runtime-inventory.mjs'

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms))
const inside = (root, path) => { const part = relative(resolve(root), resolve(path)); return part === '' || (!part.startsWith('..') && !isAbsolute(part)) }
const send = value => process.stdout.write(JSON.stringify(value) + '\n')

export async function copyRegularTree(source, target, limit = { files: 0, bytes: 0 }) {
  const info = await lstat(source)
  if (info.isSymbolicLink()) throw new Error('Verify refuses reparse links in the source Profile')
  if (info.isDirectory()) {
    await mkdir(target, { recursive: false })
    for (const item of await readdir(source)) await copyRegularTree(join(source, item), join(target, item), limit)
  } else if (info.isFile()) {
    limit.files += 1; limit.bytes += info.size
    if (limit.files > 15000 || limit.bytes > 1024 ** 3) throw new Error('Verify Profile copy exceeds its bounded file/byte limit')
    await writeFile(target, await readFile(source), { flag: 'wx', mode: 0o600 })
  } else throw new Error('Verify Profile contains an unsupported filesystem entry')
  return limit
}

export function isolatedEnvironment(source, job, home) {
  const result = {}
  for (const [name, value] of Object.entries(source)) {
    if (/secret|token|password|credential|authorization|api.?key|cookie|^auth$|private/i.test(name) || /^(DSH_|NODE_|ELECTRON_|CRATE_TEST_|PYTHONPATH$|PYTHONHOME$|PYTHONUSERBASE$)/i.test(name)) continue
    if (typeof value === 'string' && !/:\/\/[^/@\s]+:[^/@\s]+@/.test(value)) result[name] = value
  }
  Object.assign(result, { DSH_HOME: home, HOME: join(job, 'user'), USERPROFILE: join(job, 'user'),
    APPDATA: join(job, 'roaming'), LOCALAPPDATA: join(job, 'local'), TEMP: join(job, 'tmp'), TMP: join(job, 'tmp'),
    XDG_CACHE_HOME: join(job, 'cache'), XDG_CONFIG_HOME: join(job, 'config'), XDG_DATA_HOME: join(job, 'data'),
    NARB_NATIVE_CACHE_DIR: join(job, 'native-cache'), npm_config_cache: join(job, 'npm-cache'),
    npm_config_userconfig: join(job, 'npmrc'), npm_config_fetch_retries: '0', npm_config_registry: 'http://127.0.0.1:9',
    PNPM_CONFIG_STORE_DIR: join(job, 'pnpm-store'), PNPM_CONFIG_CACHE_DIR: join(job, 'pnpm-cache'),
    PNPM_CONFIG_STATE_DIR: join(job, 'pnpm-state'), PNPM_CONFIG_CONFIG_DIR: join(job, 'pnpm-config'),
    PNPM_CONFIG_OFFLINE: 'true', PNPM_CONFIG_FETCH_RETRIES: '0', PYTHONDONTWRITEBYTECODE: '1' })
  return result
}

async function freePort() {
  const server = createServer()
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve) })
  const port = server.address().port
  await new Promise((resolve, reject) => server.close(error => error ? reject(error) : resolve()))
  return port
}

export function validateSurface(value, home, webPort) {
  const officialDesktop = value.protocol === 'dsh-app:' && value.hostname === 'app'
  const localWeb = value.protocol === 'http:' && ['127.0.0.1', 'localhost', '[::1]'].includes(value.hostname)
  if ((!officialDesktop && !localWeb) || !value.accountMenu || value.httpStatus !== 200 || value.backendHttpStatus !== 200 || value.backendStatus !== 'ok') {
    throw new Error('Verification workspace/authenticated Web ready failed; see surface.observation')
  }
  if (typeof value.runtimeHome !== 'string' || resolve(value.runtimeHome).toLowerCase() !== resolve(home).toLowerCase() || value.runtimeProfile !== 'desktop' || !Number.isInteger(value.runtimePid) || value.runtimePid <= 0) {
    throw new Error('Verification backend identity does not match its isolated desktop')
  }
  if (!Number.isInteger(webPort) || webPort < 1 || webPort > 65535) throw new Error('Owned backend Web port missing from startup log')
  const inspector = inspectorApplicability(value.runtimePlugins, value.runtimeInventoryComplete)
  const { runtimePlugins, runtimeInventoryComplete, ...surface } = value
  return { ...surface, inspector, webPort, authenticationContext: 'official owned desktop protocol and authenticated profiles route; credentials not exported' }
}

class Cdp {
  constructor(url) { this.url = url; this.pending = new Map(); this.sequence = 0 }
  async connect() {
    const parsed = new URL(this.url)
    if (parsed.protocol !== 'ws:' || parsed.hostname !== '127.0.0.1') throw new Error('CDP is restricted to the owned local endpoint')
    this.socket = new WebSocket(this.url)
    this.socket.addEventListener('message', event => {
      const data = JSON.parse(event.data)
      if (!this.pending.has(data.id)) return
      const pending = this.pending.get(data.id); this.pending.delete(data.id); clearTimeout(pending.timer)
      data.error ? pending.reject(new Error(data.error.message)) : pending.resolve(data.result)
    })
    this.socket.addEventListener('close', () => {
      for (const item of this.pending.values()) { clearTimeout(item.timer); item.reject(new Error('CDP connection closed')) }
      this.pending.clear()
    })
    await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error('local CDP connection deadline')), 10000)
      this.socket.addEventListener('open', () => { clearTimeout(timer); resolve() }, { once: true })
      this.socket.addEventListener('error', () => { clearTimeout(timer); reject(new Error('local CDP connection failed')) }, { once: true })
    })
  }
  call(method, params = {}, sessionId) {
    const id = ++this.sequence
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => { this.pending.delete(id); reject(new Error('CDP command deadline: ' + method)) }, 10000)
      this.pending.set(id, { resolve, reject, timer })
      this.socket.send(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) }))
    })
  }
  async evaluate(expression) {
    const response = await this.call('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true }, this.pageSession)
    if (response.exceptionDetails) throw new Error('owned page evaluation failed')
    return response.result.value
  }
  disconnect() { if (this.socket && this.socket.readyState < 2) this.socket.close() }
}

export class DesktopController {
  constructor(config) { this.config = config; this.generation = 0; this.child = null; this.originalHashes = {} }
  async event(name, values = {}) {
    await writeFile(join(this.config.job, 'controller-events.jsonl'), JSON.stringify({ atUtc: new Date().toISOString(), event: name, generation: this.generation, ...values }) + '\n', { flag: 'a', mode: 0o600 })
  }
  async prepare() {
    const { job, sourceHome, sourceProfile, runtimeRoot } = this.config
    if (!/^[A-Za-z0-9._-]+$/.test(sourceProfile)) throw new Error('invalid Profile name')
    if (!inside(join(sourceHome, '.dsh-pack', 'verify-jobs'), job)) throw new Error('Verify job escaped its isolated workspace')
    this.home = join(job, 'home'); this.documents = join(job, 'documents')
    for (const name of ['home', 'home/profiles', 'documents', 'electron', 'user', 'roaming', 'local', 'tmp', 'cache', 'config', 'data', 'native-cache', 'npm-cache', 'pnpm-store', 'pnpm-cache', 'pnpm-state', 'pnpm-config']) await mkdir(join(job, name), { recursive: true })
    await writeFile(join(job, 'npmrc'), '', { flag: 'wx' })
    this.profile = join(this.home, 'profiles', 'desktop')
    const source = join(sourceHome, 'profiles', sourceProfile)
    if ((await lstat(source)).isSymbolicLink()) throw new Error('source Profile root is a reparse link')
    await mkdir(this.profile)
    let copied = { files: 0, bytes: 0 }
    for (const name of ['package.json', 'pnpm-lock.yaml', 'node_modules']) {
      let data
      try { data = await lstat(join(source, name)) } catch (error) { if (error.code === 'ENOENT') continue; throw error }
      copied = await copyRegularTree(join(source, name), join(this.profile, name), copied)
      if (data.isFile()) this.originalHashes[name] = createHash('sha256').update(await readFile(join(source, name))).digest('hex')
    }
    const require = createRequire(import.meta.url)
    const yaml = require(join(runtimeRoot, 'node_modules', 'js-yaml'))
    const patchPath = join(this.profile, 'cordis.patch.yml')
    // Parse configuration before writing: credentials in config are never copied verbatim.
    const rows = yaml.load(await readFile(join(source, 'cordis.patch.yml'), 'utf8')) ?? []
    if (!Array.isArray(rows)) throw new Error('Profile patch must be a patch-list array')
    const workspace = rows.find(row => row?.id === 'workspace-controller')
    const oldDocuments = workspace?.config?.documentsDirectory
    const rewrite = value => {
      if (typeof value === 'string') {
        let result = value.split(sourceHome).join(this.home)
        if (typeof oldDocuments === 'string' && oldDocuments) result = result.split(oldDocuments).join(this.documents)
        if (isAbsolute(result) && ![job, dirname(this.config.desktopExecutable), process.env.SystemRoot ?? 'C:\\Windows'].some(root => inside(root, result))) throw new Error('Profile has an absolute path outside Verify isolation')
        return result
      }
      if (Array.isArray(value)) return value.map(rewrite)
      if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([key, item]) => [key,
        /^(api.?key|token|password|secret|authorization|cookie|credential|private.?key)$/i.test(key) ? 'CRATE_VERIFY_REDACTED' : rewrite(item)]))
      return value
    }
    let rewritten = rewrite(rows)
    const put = (id, change) => { let row = rewritten.find(item => item?.id === id); if (!row) { row = { id }; rewritten.push(row) } change(row) }
    put('workspace-controller', row => { row.config = { ...row.config, documentsDirectory: this.documents } })
    for (const id of ['session-title-llm', 'session-telemetry-otel', 'desktop-product-telemetry', 'product-analytics', 'llm-deepseek']) put(id, row => { row.disabled = true })
    const providerRow = rewritten.find(row => row?.id === 'llm-pi-ai')
    if (providerRow) {
      const row = providerRow
      for (const provider of Object.values(row.config?.providers ?? {})) if (provider && typeof provider === 'object') {
        provider.baseURL = 'http://127.0.0.1:9/v1'; provider.apiKey = 'CRATE_VERIFY_NO_MODEL_REQUESTS'
        provider.retryPolicy = { ...provider.retryPolicy, maxRetries: 0 }
      }
    }
    this.inspectorPort = await freePort()
    put('experimental-inspector', row => { row.config = { ...row.config, port: this.inspectorPort } })
    await writeFile(patchPath, yaml.dump(rewritten, { noRefs: true, lineWidth: 4096 }))
    const rootRows = yaml.load(await readFile(join(source, 'cordis.yml'), 'utf8')) ?? []
    if (!Array.isArray(rootRows) || rootRows.length) throw new Error('Nonempty Profile root requires an explicit runner; built-in Verify will not guess its isolation')
    await writeFile(join(this.profile, 'cordis.yml'), '[]\n')
    for (const name of ['cordis.patch.yml', 'cordis.yml']) this.originalHashes[name] = createHash('sha256').update(await readFile(join(source, name))).digest('hex')
    const homePatch = join(sourceHome, 'cordis.patch.yml')
    try {
      if ((await lstat(homePatch)).isSymbolicLink()) throw new Error('Home patch reparse link refused')
      const data = yaml.load(await readFile(homePatch, 'utf8'))
      if (Array.isArray(data) ? data.length : data && Object.keys(data).length) throw new Error('Nonempty Home overlay requires an explicit runner; built-in Verify will not guess its isolation')
    } catch (error) { if (error.code !== 'ENOENT') throw error }
    const preparation = { sourceProfile, runtimeProfile: 'desktop', copied, sourceHashes: this.originalHashes,
      credentialsFilesCopied: false, modelRequests: 0, requiredPluginsRemoved: false, home: this.home, documents: this.documents }
    await writeFile(join(job, 'preparation.json'), JSON.stringify(preparation, null, 2))
    this.prepared = true
    return preparation
  }
  async boot() {
    if (this.generation >= this.config.maximumBoots) throw new Error('Verify desktop boot limit reached')
    if (!this.prepared) await this.prepare()
    this.generation += 1; this.cdpPort = await freePort()
    const env = isolatedEnvironment(process.env, this.config.job, this.home)
    if (this.config.observe) {
      this.trace = join(this.config.job, 'trace-' + this.generation)
      await mkdir(this.trace)
      Object.assign(env, { CRATE_TEST_ROOT: this.config.job, CRATE_TEST_OBSERVATION_DIR: this.trace, CRATE_TEST_RUN_ID: randomUUID() })
    }
    const stdout = await open(join(this.config.job, `desktop-${this.generation}.stdout.log`), 'wx')
    const stderr = await open(join(this.config.job, `desktop-${this.generation}.stderr.log`), 'wx')
    try {
      this.child = spawn(this.config.desktopExecutable, [`--user-data-dir=${join(this.config.job, 'electron')}`,
        '--remote-debugging-address=127.0.0.1', `--remote-debugging-port=${this.cdpPort}`], {
        cwd: this.config.job, env, windowsHide: true, stdio: ['ignore', stdout.fd, stderr.fd] })
    } finally { await stdout.close(); await stderr.close() }
    this.childError = null
    this.child.once('error', error => { this.childError = error })
    const state = { pid: this.child.pid, cdpPort: this.cdpPort, inspectorPort: this.inspectorPort, trace: this.trace,
      home: this.home, job: this.config.job, generation: this.generation }
    await writeFile(join(this.config.job, 'state.json'), JSON.stringify(state, null, 2))
    send({ event: 'desktop.spawned', ...state })
    await this.event('desktop.spawned', state)
    const deadline = Date.now() + 45000
    let version
    while (Date.now() < deadline) {
      if (this.childError) throw new Error('Verification desktop spawn failed: ' + this.childError.code)
      if (this.child.exitCode !== null) throw new Error('Verification desktop exited before ready: ' + this.child.exitCode)
      try {
        const response = await fetch(`http://127.0.0.1:${this.cdpPort}/json/version`, { signal: AbortSignal.timeout(1500) })
        if (response.ok) { version = await response.json(); break }
      } catch { /* Passive startup wait; no launch retry. */ }
      await sleep(200)
    }
    if (!version) throw new Error('Verification desktop CDP ready deadline')
    this.browser = new Cdp(version.webSocketDebuggerUrl); await this.browser.connect()
    let target
    while (!target && Date.now() < deadline) {
      const targets = await this.browser.call('Target.getTargets')
      target = targets.targetInfos.find(item => item.type === 'page' && !item.url.startsWith('devtools:'))
      if (!target) await sleep(150)
    }
    if (!target) throw new Error('Owned desktop page missing')
    this.browser.pageSession = (await this.browser.call('Target.attachToTarget', { targetId: target.targetId, flatten: true })).sessionId
    let openedKey = false
    while (Date.now() < deadline) {
      const ready = await this.browser.evaluate(`(() => {
        const labels = element => (element.getAttribute('aria-label') || element.innerText || '').trim();
        const buttons = [...document.querySelectorAll('button')];
        if (buttons.some(button => /^(Account menu|账户菜单|账号菜单)$/i.test(labels(button)))) return 'ready';
        const skip = document.querySelector('#skip-key'); if (skip) { skip.click(); return 'skip'; }
        ${openedKey ? '' : "const add = buttons.find(button => /^(Add API Key|添加 API Key)$/i.test(labels(button))); if (add) { add.click(); return 'opened-key'; }"}
        return 'waiting';
      })()`)
      if (ready === 'ready') break
      if (ready === 'opened-key') openedKey = true
      await sleep(150)
    }
    const surface = await this.surface()
    await this.event('desktop.ready', { ...state, surface })
    return { ...state, surface }
  }
  async surface() {
    const value = await this.browser.evaluate(`(async () => {
      const accountMenu = [...document.querySelectorAll('button')].some(button => /^(Account menu|账户菜单|账号菜单)$/i.test((button.getAttribute('aria-label') || button.innerText || '').trim()));
      const response = await fetch('/', { credentials: 'same-origin', signal: AbortSignal.timeout(7000) });
      const backend = await fetch('/dsh-crate/api', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action: 'profiles' }), signal: AbortSignal.timeout(7000) });
      let result; try { result = await backend.json() } catch { result = {} }
      return { accountMenu, httpStatus: response.status, origin: location.origin, protocol: location.protocol, hostname: location.hostname,
        backendHttpStatus: backend.status, backendStatus: result.status, runtimePid: result.runtime?.pid,
          runtimeHome: result.runtime?.dshHome, runtimeProfile: result.runtime?.currentProfile,
          runtimePlugins: result.runtimePlugins, runtimeInventoryComplete: result.runtimeInventoryComplete };
    })()`)
    const log = join(this.config.job, `desktop-${this.generation}.stdout.log`)
    if ((await lstat(log)).size > 1024 * 1024) throw new Error('Owned desktop startup log exceeded observation limit')
    const ports = [...(await readFile(log, 'utf8')).matchAll(/dsh web: http:\/\/127\.0\.0\.1:(\d+)\//g)]
    const webPort = ports.length ? Number(ports.at(-1)[1]) : undefined
    await this.event('surface.observation', { ...value, webPort })
    return validateSurface(value, this.home, webPort)
  }
  async newSession() {
    const selected = () => this.browser.evaluate(`([...document.querySelectorAll('[data-row-key^="session:"][aria-selected="true"]')].map(element => element.getAttribute('data-row-key').slice(8)))`)
    const selectedBefore = await selected()
    const clicked = await this.browser.evaluate(`(() => {
      const button = [...document.querySelectorAll('button')].find(element => /^New session$/i.test((element.getAttribute('aria-label') || element.innerText || '').trim()) && !element.disabled && element.getClientRects().length);
      if (!button) return false; button.click(); return true;
    })()`)
    if (!clicked) throw new Error('Official New session button unavailable')
    await this.event('new-session.clicked')
    let selectedAfter = []
    const deadline = Date.now() + 10000
    while (Date.now() < deadline) {
      selectedAfter = await selected()
      if (selectedAfter.length === 1) break
      await sleep(100)
    }
    if (selectedAfter.length !== 1) throw new Error('New session did not select exactly one session')
    return { officialButtonClicks: 1, selectedBefore, selectedAfter }
  }
  async close() {
    if (!this.child) return { requested: false, exitCode: null }
    let requested = false
    if (this.child.exitCode === null && this.browser) {
      requested = true
      try { await this.browser.call('Browser.close') } catch { /* Browser may close its socket before acknowledging. */ }
    }
    const deadline = Date.now() + 20000
    while (this.child.exitCode === null && Date.now() < deadline) await sleep(100)
    this.browser?.disconnect()
    const value = { requested, pid: this.child.pid, exitCode: this.child.exitCode, generation: this.generation }
    await this.event('desktop.closed', value)
    if (value.exitCode === null) throw new Error('Owned desktop did not exit after close request')
    return value
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const config = JSON.parse(await readFile(process.argv[2], 'utf8'))
  if (config.modelRequests !== 0 || config.automaticRetries !== 0) throw new Error('Built-in desktop verifier only accepts zero-model, no-retry scope')
  const controller = new DesktopController(config)
  try {
    for await (const line of createInterface({ input: process.stdin })) {
      let response
      try {
        const request = JSON.parse(line)
        const value = request.operation === 'boot' ? await controller.boot()
          : request.operation === 'surface' ? await controller.surface()
          : request.operation === 'new_session' ? await controller.newSession()
          : request.operation === 'close' ? await controller.close()
          : (() => { throw new Error('Unsupported desktop controller operation') })()
        response = { value }
      } catch (error) { response = { error: { type: error.name, message: error.message } } }
      send(response)
    }
  } finally { await controller.close().catch(() => undefined) }
}
