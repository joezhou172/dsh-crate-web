import assert from 'node:assert/strict'
import http from 'node:http'
import { mkdtemp, mkdir, rename, writeFile } from 'node:fs/promises'
import { join, resolve } from 'node:path'
import { pathToFileURL } from 'node:url'

const root = resolve(process.argv[2])
const entry = resolve(process.argv[3] || join(root, 'lib/index.js'))
const user = await mkdtemp(join(root, 'work/home-resolution-'))
const home = join(user, '.dsh')
process.env.USERPROFILE = user
process.env.HOME = user
const profile = join(home, 'profiles/desktop')
await mkdir(profile, { recursive: true })
await writeFile(join(profile, 'package.json'), JSON.stringify({ name: 'desktop', dsh: { profile: { bundles: [] } } }))
delete process.env.DSH_HOME
const mode = process.argv[4] || 'default'
if (mode === 'blank') process.env.DSH_HOME = '   '
if (mode === 'explicit') process.env.DSH_HOME = home
if (mode === 'tilde') process.env.DSH_HOME = '~/.dsh'
process.chdir(profile)
const handlers = new Map()
const { apply } = await import(pathToFileURL(entry).href)
apply({ effect: fn => fn(), connection: { requestRejection: () => undefined }, webServer: {
  register: route => { handlers.set(route.path, route.handler); return () => {} },
} })
const server = http.createServer((req, res) => handlers.get(req.url)?.(req, res))
await new Promise(done => server.listen(0, '127.0.0.1', done))
try {
  const response = await fetch(`http://127.0.0.1:${server.address().port}/dsh-crate/api`, {
    method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ action: 'profiles' }),
  })
  const result = await response.json()
  assert.equal(result.profiles?.[0]?.name, 'desktop', JSON.stringify(result))
  assert.equal(result.runtime.dshHome, home)
  const catalog = await (await fetch(`http://127.0.0.1:${server.address().port}/dsh-crate/api`, {
    method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ action: 'export-catalog', profileName: 'desktop' }),
  })).json()
  assert.equal(catalog.status, 'ok', JSON.stringify(catalog))
  // A preparation scandir ENOENT is not a missing executable: retain its cause.
  const runtime = join(user, 'runtime')
  await mkdir(join(runtime, 'node_modules/@deepseek-ai/dsh'), { recursive: true })
  await writeFile(join(runtime, 'node_modules/@deepseek-ai/dsh/package.json'), '{"version":"fixture"}')
  process.argv[1] = join(runtime, '@deepseek-ai/dsh-desktop-host/index.js')
  process.argv[2] = runtime
  process.chdir(user)
  await rename(join(home, 'profiles'), join(home, 'profiles-saved'))
  const failure = await (await fetch(`http://127.0.0.1:${server.address().port}/dsh-crate/api`, {
    method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ action: 'export-catalog', profileName: 'desktop' }),
  })).json()
  assert.equal(failure.status, 'failed')
  assert.match(failure.error.message, /ENOENT.*scandir/)
  assert.ok(!failure.error.message.includes('Core is unavailable'), JSON.stringify(failure))
  console.log(`PASS: ${mode} Home, cwd is desktop Profile, profiles and bundled Core catalog`)
} finally {
  server.closeAllConnections()
  await new Promise(done => server.close(done))
}
