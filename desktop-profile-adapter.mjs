// Installed only into an explicitly approved, hash-checked Desktop copy.
import { existsSync, lstatSync, realpathSync, mkdirSync, readFileSync, writeFileSync, renameSync, cpSync, readdirSync } from 'node:fs'
import { join, resolve, relative, isAbsolute } from 'node:path'
import { randomUUID } from 'node:crypto'

export function safeName(name) {
  return typeof name === 'string' && name.length > 0 && name === name.trim() && !/[<>:"/\\|?*\x00-\x1f\x7f]/.test(name) && !/[. ]$/.test(name) && !['.', '..', 'node_modules'].includes(name.toLowerCase()) && !/^(con|prn|aux|nul|com[1-9¹²³]|lpt[1-9¹²³])(?:\.|$)/i.test(name)
}
const inside = (root, path) => { const rel = relative(root, path); return rel === '' || (!rel.startsWith('..') && !isAbsolute(rel)) }
export class DesktopProfiles {
  constructor(home) {
    this.home = resolve(home)
    this.root = join(this.home, '.dsh-pack', 'desktop-launch')
    this.file = join(this.root, 'state.json')
    this.selected = undefined
  }
  read() {
    if (!existsSync(this.file)) return { schemaVersion: 1, defaultProfile: 'desktop' }
    const state = JSON.parse(readFileSync(this.file, 'utf8'))
    if (state.schemaVersion !== 1 || !safeName(state.defaultProfile)) throw Error('Invalid desktop launch settings')
    return state
  }
  write(state) {
    for (const path of [this.home, join(this.home, '.dsh-pack'), this.root]) {
      if (existsSync(path) && lstatSync(path).isSymbolicLink()) throw Error('Linked desktop settings directories are not supported')
    }
    mkdirSync(this.root, { recursive: true })
    const temp = join(this.root, `${randomUUID()}.tmp`)
    writeFileSync(temp, JSON.stringify(state, null, 2), { flag: 'wx', mode: 0o600 })
    renameSync(temp, this.file)
  }
  profile(name) {
    if (!safeName(name)) throw Error('Invalid environment name')
    const root = join(this.home, 'profiles'), path = join(root, name)
    if (lstatSync(root).isSymbolicLink() || lstatSync(path).isSymbolicLink() || !inside(realpathSync(root), realpathSync(path))) throw Error('Linked environment directories are not supported')
    const pkg = JSON.parse(readFileSync(join(path, 'package.json'), 'utf8'))
    return { path, pkg }
  }
  request({ action, target, makeDefault = false, confirm = false }, current) {
    if (!confirm) throw Error('Explicit confirmation is required')
    const { path, pkg } = this.profile(target)
    if (!pkg.dsh?.profile?.bundles?.includes('dsh-crate-web') || !existsSync(join(path, 'node_modules/dsh-crate-web/package.json'))) throw Error('Install DSH Crate in the target environment before restarting, so environment management remains available')
    const state = this.read()
    if (state.pending) throw Error('A desktop operation is already pending')
    if (action === 'default') {
      state.defaultProfile = target
      this.write(state)
      return { status: 'configured', defaultProfile: target }
    }
    if (!['switch', 'replace'].includes(action)) throw Error('Unsupported desktop operation')
    if (action === 'replace' && target === 'desktop') throw Error('Cannot replace desktop with itself')
    this.profile(current)
    const pending = { id: randomUUID(), action, target, previous: current, makeDefault: makeDefault === true, phase: 'scheduled' }
    state.pending = pending
    this.write(state)
    return { status: 'scheduled', operationId: pending.id, profileName: action === 'replace' ? 'desktop' : target }
  }
  treeWithoutLinks(path) {
    const stat = lstatSync(path)
    if (stat.isSymbolicLink()) throw Error('Replacement refuses linked files; export and import this environment first')
    if (stat.isDirectory()) for (const entry of readdirSync(path)) this.treeWithoutLinks(join(path, entry))
    else if (!stat.isFile()) throw Error('Unsupported environment file')
  }
  transactionPaths(pending) {
    if (!/^[0-9a-f-]{36}$/.test(pending.id)) throw Error('Invalid operation identity')
    const dir = join(this.root, pending.id)
    for (const path of [this.root, dir]) if (existsSync(path) && lstatSync(path).isSymbolicLink()) throw Error('Linked snapshot directories are not supported')
    return { dir, stage: join(dir, 'prepared'), backup: join(dir, 'desktop-snapshot'), failed: join(dir, 'failed-desktop'), desktop: join(this.home, 'profiles', 'desktop') }
  }
  restore(state, message) {
    const op = state.pending
    let restored = false
    if (op?.action === 'replace') {
      const paths = this.transactionPaths(op)
      if (existsSync(paths.backup)) {
        if (existsSync(paths.desktop)) renameSync(paths.desktop, paths.failed)
        renameSync(paths.backup, paths.desktop)
        restored = true
      }
    }
    state.lastResult = { status: 'failed', operationId: op?.id, message, restored, target: op?.target }
    if (op?.defaultProbe) state.defaultProfile = 'desktop'
    delete state.pending
    this.write(state)
  }
  select() {
    if (this.selected) return this.selected
    let state
    try { state = this.read() }
    catch (error) {
      // Preserve malformed settings for diagnosis instead of silently overwriting.
      if (existsSync(this.file)) renameSync(this.file, `${this.file}.invalid-${randomUUID()}`)
      state = { schemaVersion: 1, defaultProfile: 'desktop', lastResult: { status: 'failed', message: String(error), restored: false } }
      this.write(state)
    }
    let target = state.recoveryProfile || state.defaultProfile
    if (state.recoveryProfile) { delete state.recoveryProfile; this.write(state) }
    const op = state.pending
    if (op) {
      if (op.phase !== 'scheduled') {
        this.restore(state, 'Previous startup did not finish; restored the previous environment')
        target = op.previous
      } else {
        try {
          this.profile(op.target)
          if (op.action === 'replace') {
            const paths = this.transactionPaths(op)
            this.profile('desktop')
            if (existsSync(join(paths.desktop, 'lock'))) throw Error('Desktop is locked; replacement was not started')
            if (existsSync(join(this.profile(op.target).path, 'lock'))) throw Error('Source environment is locked; replacement was not started')
            this.treeWithoutLinks(this.profile(op.target).path)
            mkdirSync(paths.dir, { recursive: true })
            cpSync(this.profile(op.target).path, paths.stage, { recursive: true, errorOnExist: true, force: false })
            op.phase = 'prepared'; this.write(state)
            renameSync(paths.desktop, paths.backup)
            op.phase = 'snapshot'; this.write(state)
            renameSync(paths.stage, paths.desktop)
          }
          target = op.action === 'replace' ? 'desktop' : op.target
          op.phase = 'booting'; this.write(state)
        } catch (error) {
          this.restore(state, String(error))
          target = op.previous
        }
      }
    }
    if (target === 'desktop' && !existsSync(join(this.home, 'profiles/desktop'))) {
      this.selected = target // The official first-run initializer creates desktop.
      return target
    }
    try { this.profile(target) }
    catch (error) {
      target = 'desktop'; this.profile(target)
      state.defaultProfile = target
      state.lastResult = { status: 'failed', message: String(error), restored: false }
      this.write(state)
    }
    if (!state.pending && target !== 'desktop') {
      state.pending = { id: randomUUID(), action: 'switch', target, previous: 'desktop', defaultProbe: true, phase: 'booting' }
      this.write(state)
    }
    this.selected = target
    return target
  }
  ready() {
    const state = this.read(), op = state.pending
    if (!op || op.phase !== 'booting') return
    if (op.makeDefault) state.defaultProfile = this.selected
    state.lastResult = { status: 'ready', operationId: op.id, profileName: this.selected, snapshot: op.action === 'replace' ? this.transactionPaths(op).backup : undefined }
    delete state.pending
    this.write(state)
  }
}

let manager, lifecycle, busy = false, watchdog
export function desktopSelection(home) {
  manager ??= new DesktopProfiles(home)
  return manager.select()
}
export function registerDesktopLifecycle(value) {
  lifecycle = value
  if (manager?.read().pending?.phase === 'booting') watchdog = setTimeout(() => void failedStartup('Desktop environment startup timed out'), 90000)
}
export function handleDesktopFailure(error) {
  if (!manager || !lifecycle || !manager.read().pending) return false
  void failedStartup(String(error))
  return true
}
async function failedStartup(message) {
  if (busy || !lifecycle || !manager?.read().pending) return
  busy = true; clearTimeout(watchdog)
  try {
    await lifecycle.stop()
    const state = manager.read(), previous = state.pending?.previous || 'desktop'
    manager.restore(state, message)
    // Recover this launch without changing the user's saved default.
    const recovered = manager.read()
    recovered.recoveryProfile = previous
    manager.write(recovered)
    lifecycle.restart()
  } catch (error) { console.error('Crate desktop recovery failed:', error); busy = false }
}
export function handleDesktopHostMessage(message, child) {
  if (message?.type === 'ready') { clearTimeout(watchdog); manager?.ready(); return false }
  if (message?.type === 'fatal' && manager?.read().pending) void failedStartup(String(message.message || 'Environment startup failed'))
  if (message?.type !== 'crate-desktop-request') return false
  const reply = value => { if (child.connected) child.send({ type: 'crate-desktop-result', id: message.id, ...value }) }
  try {
    if (!lifecycle || busy) throw Error('Desktop is busy')
    const result = manager.request(message.request, manager.selected)
    reply({ status: 'ok', result })
    if (result.status === 'scheduled') {
      busy = true
      setTimeout(async () => {
        try { await lifecycle.stop(); lifecycle.restart() }
        catch (error) {
          manager.restore(manager.read(), `Desktop did not stop cleanly: ${String(error)}`)
          busy = false
        }
      }, 1500)
    }
  } catch (error) { reply({ status: 'failed', error: { message: String(error) } }) }
  return true
}
