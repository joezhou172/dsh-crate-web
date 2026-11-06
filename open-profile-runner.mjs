// Uses the installed official runtime; never rewrites the desktop Profile.
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'
const spec = JSON.parse(Buffer.from(process.argv[2], 'base64url').toString('utf8'))
let running
let stopping = false
async function stop() {
  if (stopping) return
  stopping = true
  try { await running?.ctx.dispose() } finally { process.exit(0) }
}
process.on('message', message => { if (message?.type === 'stop') void stop() })
process.on('disconnect', () => void stop())
try {
  const modules = join(spec.runtime, 'node_modules', '@deepseek-ai')
  const { runProfile } = await import(pathToFileURL(join(modules, 'dsh/lib/profile-boot.js')).href)
  const { loadLayeredEnv, loadProfileDirectory } = await import(pathToFileURL(join(modules, 'dsh-app-boot/lib/index.js')).href)
  const installAnchor = join(modules, 'dsh/package.json')
  const profile = loadProfileDirectory('dsh', spec.profilePath, installAnchor)
  running = await runProfile({
    environment: loadLayeredEnv('dsh'), profile: spec.name,
    resolvedProfile: { profile, installAnchor }, patchFiles: [],
    args: ['--no-open', '--host', '127.0.0.1', '--port', '0'],
    ...(spec.pnpm ? { packageManager: { command: process.execPath, args: ['--expose-internals', spec.pnpm], env: { ELECTRON_RUN_AS_NODE: '1' } } } : {}),
  })
  if (stopping) { await running.ctx.dispose(); process.exit(0) }
  const { ctx } = running
  if (!ctx.webServer || !ctx.connection) throw Error('The environment has no Web interface')
  const url = ctx.connection.authenticatedUrl(`${ctx.webServer.protocol}//127.0.0.1:${ctx.webServer.port}`)
  process.send?.({ type: 'ready', profile: spec.name, pid: process.pid, url })
} catch (error) {
  process.send?.({ type: 'failed', message: error instanceof Error ? error.message : String(error) })
  console.error(error)
  await stop()
}
