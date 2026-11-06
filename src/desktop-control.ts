import { randomUUID } from 'node:crypto'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

export function desktopControlState(home: string) {
  let state: { defaultProfile?: string; lastResult?: unknown } = {}
  try { state = JSON.parse(readFileSync(join(home, '.dsh-pack/desktop-launch/state.json'), 'utf8')) } catch { /* Missing state is the default desktop. */ }
  return { desktopRestartConfigured: process.env.DSH_CRATE_DESKTOP_ADAPTER === '1' && !!process.send,
    defaultProfile: state.defaultProfile || 'desktop', desktopLastResult: state.lastResult ?? null }
}

export async function desktopControl(request: { action: 'switch' | 'default' | 'replace'; target: string; makeDefault?: boolean; confirm: boolean }): Promise<any> {
  if (process.env.DSH_CRATE_DESKTOP_ADAPTER !== '1' || !process.send) throw Error('This Desktop does not have the verified environment launcher adapter. No environment was changed.')
  const id = randomUUID()
  return new Promise((resolve, reject) => {
    const cleanup = () => { clearTimeout(timer); process.off('message', receive) }
    const receive = (message: any) => {
      if (message?.type !== 'crate-desktop-result' || message.id !== id) return
      cleanup()
      if (message.status === 'ok') resolve(message.result)
      else reject(Error(message.error?.message || 'Desktop operation failed'))
    }
    const timer = setTimeout(() => { cleanup(); reject(Error('Desktop did not acknowledge the operation; check environment management before retrying')) }, 15000)
    process.on('message', receive)
    process.send!({ type: 'crate-desktop-request', id, request }, error => { if (error) { cleanup(); reject(error) } })
  })
}
