import { spawn, type ChildProcess } from 'node:child_process'
import { open, readFile, lstat } from 'node:fs/promises'
import { join } from 'node:path'
import { randomUUID } from 'node:crypto'

type Opened = { child: ChildProcess; ready: Promise<{ status: string; profileName: string; url: string; pid: number }>; closing?: Promise<void> }
const opened = new Map<string, Opened>()
const launching = new Map<string, Promise<{ status: string; profileName: string; url: string; pid: number }>>()
const key = (home: string, name: string) => JSON.stringify([home, name])
export function openedProfiles(home: string): string[] {
  return [...new Set([...opened.keys(), ...launching.keys()])].map(value => JSON.parse(value) as string[]).filter(value => value[0] === home).map(value => value[1]!)
}
export async function closeOpenedProfile(home: string, name: string): Promise<void> {
  const id = key(home, name)
  if (launching.has(id)) { try { await launching.get(id) } catch { /* already failed */ } }
  const entry = opened.get(id)
  if (!entry) return
  if (entry.closing) return entry.closing
  entry.closing = new Promise<void>(resolve => {
    const timer = setTimeout(() => entry.child.kill(), 10000)
    entry.child.once('exit', () => { clearTimeout(timer); if (opened.get(id) === entry) opened.delete(id); resolve() })
    if (entry.child.connected) entry.child.send({ type: 'stop' })
    else entry.child.kill()
  })
  return entry.closing
}
export function closeOpenedProfiles(home: string): void {
  for (const name of openedProfiles(home)) void closeOpenedProfile(home, name)
}
async function openProfileOnce(home: string, name: string, runtime: string, runner: string, work: string) {
  const id = key(home, name), previous = opened.get(id)
  if (previous) { if (previous.closing) throw Error('Environment is stopping; try again shortly'); return previous.ready }
  const profilePath = join(home, 'profiles', name)
  if ((await lstat(profilePath)).isSymbolicLink()) throw Error('Cannot open a linked environment directory')
  const log = join(work, `open-${randomUUID()}.log`)
  const output = await open(log, 'wx')
  const spec = { runtime, profilePath, name, pnpm: process.env.DSH_CRATE_DESKTOP_PNPM ?? process.argv[5] }
  const child = spawn(process.execPath, [runner, Buffer.from(JSON.stringify(spec)).toString('base64url')], {
    cwd: profilePath, windowsHide: true,
    env: { ...process.env, DSH_CRATE_DESKTOP_ADAPTER: '0', DSH_HOME: home, DSH_PROFILE: name, DSH_PACK_ACTIVE_PROFILE: name, DSH_CRATE_DESKTOP_RUNTIME: runtime, ...(spec.pnpm ? { DSH_CRATE_DESKTOP_PNPM: spec.pnpm } : {}) },
    stdio: ['ignore', output.fd, output.fd, 'ipc'],
  })
  const ready = new Promise<{ status: string; profileName: string; url: string; pid: number }>((resolve, reject) => {
    const timer = setTimeout(() => { child.kill(); reject(Error('Environment startup timed out. The original desktop remains running.')) }, 60000)
    child.once('error', error => { clearTimeout(timer); reject(error); opened.delete(id) })
    child.once('exit', () => { clearTimeout(timer); opened.delete(id); void readFile(log, 'utf8').then(text => reject(Error(`Environment exited before becoming ready. ${text.slice(-8000).replace(/([?&]token=)[^\s&]+/g, '$1[REDACTED]')}`)), () => reject(Error('Environment exited before becoming ready'))) })
    child.on('message', value => {
      const message = value as { type?: string; profile?: string; pid?: number; url?: string; message?: string }
      if (message.type === 'failed') { clearTimeout(timer); child.kill(); reject(Error(message.message || 'Environment startup failed')) }
      if (message.type !== 'ready') return
      try {
        const url = new URL(message.url ?? '')
        if (message.profile !== name || message.pid !== child.pid || url.hostname !== '127.0.0.1' || !['http:', 'https:'].includes(url.protocol)) throw Error('Environment startup identity mismatch')
        clearTimeout(timer)
        resolve({ status: 'opened', profileName: name, pid: child.pid!, url: url.href })
      } catch (error) { clearTimeout(timer); child.kill(); reject(error) }
    })
  })
  opened.set(id, { child, ready })
  void output.close()
  return ready
}

export function openProfile(home: string, name: string, runtime: string, runner: string, work: string) {
  const id = key(home, name), pending = launching.get(id)
  if (pending) return pending
  const result = openProfileOnce(home, name, runtime, runner, work).finally(() => launching.delete(id))
  launching.set(id, result)
  return result
}
