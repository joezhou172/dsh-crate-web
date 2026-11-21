import assert from 'node:assert/strict'
import { mkdtemp, mkdir, readFile, writeFile, access, symlink } from 'node:fs/promises'
import { join } from 'node:path'
import { createHash } from 'node:crypto'
import { CrateSetup, selectStable, boundedDownload } from '../src/setup.ts'
const root = await mkdtemp(join(import.meta.dirname, '../work/setup-test-'))
const checks = []
const check = async (name, run) => { await run(); checks.push(name) }
const meta = (v, deprecated) => ({ 'dist-tags': { latest: v, preview: '99.0.0-preview.99' }, versions: { [v]: { version: v, deprecated } } })
await check('stable selection ignores previews, deprecated, downgrade; accepts same-base stable', async () => {
  for (const value of ['1.0.0-preview.1', '1.0.0-rc.1', 'garbage', '01.2.3']) assert.equal(selectStable(meta(value), '0.1.2'), null)
  assert.equal(selectStable(meta('0.1.1'), '0.1.2-preview.16'), null)
  assert.equal(selectStable(meta('0.1.2'), '0.1.2-preview.16'), '0.1.2')
  assert.equal(selectStable(meta('0.2.0', 'broken'), '0.1.2'), null)
  assert.equal(selectStable(meta('0.2.0'), '0.1.2'), '0.2.0')
})
await check('bounded HTTPS download guards', async () => {
  await assert.rejects(boundedDownload('http://example.com', 5), /HTTPS/)
  await assert.rejects(boundedDownload('https://example.com', 5, async () => new Response('123456')), /limit/)
  await assert.rejects(boundedDownload('https://example.com', 5, async () => new Response('', { status: 404 })), /404/)
})
const hash = data => createHash('sha256').update(data).digest('hex')
const pkg = join(root, 'package'), target = join(root, 'desktop'), home = join(root, 'home')
await mkdir(join(pkg, 'packaging/desktop-bootstrap'), { recursive: true }); await mkdir(join(pkg, 'runtime/python'), { recursive: true })
await mkdir(join(target, 'resources'), { recursive: true })
await writeFile(join(pkg, 'runtime/python/python.exe'), 'not-executed')
await writeFile(join(pkg, 'package.json'), JSON.stringify({ version: '0.1.2-preview.16' }))
await writeFile(join(target, 'DeepSeek Harness.exe'), 'not-executed'); await writeFile(join(target, 'resources/app.asar'), 'official-fixture')
const payload = Buffer.from(JSON.stringify({ id: 'test', files: { 'script.py': Buffer.from('fixture').toString('base64') } }))
const manifest = { id: 'test', files: ['script.py'], originalSha256: hash('official-fixture'), sha256: hash(payload), url: 'https://example.com/component', maxBytes: 1024 }
await writeFile(join(pkg, 'packaging/desktop-bootstrap/manifest.json'), JSON.stringify(manifest))
let downloads = 0
const fetcher = async url => { downloads++; return new Response(url.includes('registry.npmjs') ? JSON.stringify(meta('0.1.1')) : payload) }
const service = new CrateSetup({ home, packageRoot: pkg, desktopRoot: target, platform: 'win32', fetcher })
await check('auto preparation downloads once; does not change desktop; concurrent requests join', async () => {
  await Promise.all([service.prepare(), service.prepare()]); assert.equal(downloads, 1)
  assert.equal((await service.status()).desktop.status, 'ready')
  assert.equal(await readFile(join(target, 'resources/app.asar'), 'utf8'), 'official-fixture')
  await assert.rejects(access(join(home, '.dsh-pack/desktop-setup/task.json')))
  await assert.rejects(service.schedule(false), /Confirm/)
})
await check('verified cache works offline; changed extracted files rebuilt', async () => {
  const cached = join(home, '.dsh-pack/desktop-setup/cache', manifest.sha256)
  await writeFile(join(cached, 'script.py'), 'changed')
  const offline = new CrateSetup({ home, packageRoot: pkg, desktopRoot: target, platform: 'win32', fetcher: async () => { throw Error('offline') } })
  await offline.prepare(); assert.equal((await offline.status()).desktop.status, 'ready')
  assert.equal(await readFile(join(cached, 'script.py'), 'utf8'), 'fixture')
})
await check('bad download fails without modifying installation', async () => {
  const bad = new CrateSetup({ home: join(root, 'bad'), packageRoot: pkg, desktopRoot: target, platform: 'win32', fetcher: async () => new Response('wrong') })
  await bad.prepare(); assert.equal((await bad.status()).desktop.status, 'failed')
  assert.equal(await readFile(join(target, 'resources/app.asar'), 'utf8'), 'official-fixture')
})
await check('bundled verified component initializes offline and persists worker payload', async () => {
  await writeFile(join(pkg, 'packaging/desktop-bootstrap/component.json'), payload)
  const bundledHome = join(root, 'bundled')
  const bundled = new CrateSetup({ home: bundledHome, packageRoot: pkg, desktopRoot: target, platform: 'win32', fetcher: async () => { throw Error('offline') } })
  await bundled.prepare()
  assert.equal((await bundled.status()).desktop.status, 'ready')
  assert.deepEqual(await readFile(join(bundledHome, '.dsh-pack/desktop-setup/cache', manifest.sha256, 'component.json')), payload)
  assert.equal(await readFile(join(target, 'resources/app.asar'), 'utf8'), 'official-fixture')
})
await check('unknown desktop build rejected before download', async () => {
  await writeFile(join(target, 'resources/app.asar'), 'unknown')
  const unsupported = new CrateSetup({ home, packageRoot: pkg, desktopRoot: target, platform: 'win32', fetcher: async () => { throw Error('must not download') } })
  await unsupported.prepare(); assert.equal((await unsupported.status()).desktop.status, 'unsupported')
})
await check('update cache and manual recheck; preview not recommended as upgrade', async () => {
  const before = downloads; await service.checkUpdates(); assert.equal((await service.status()).update.available, null)
  await service.checkUpdates(); assert.equal(downloads, before + 1)
  await service.checkUpdates(true); assert.equal(downloads, before + 2)
})
await check('Web has no Desktop preparation, stable check remains available', async () => {
  const web = new CrateSetup({ home, packageRoot: pkg, platform: 'linux', fetcher })
  await web.prepare(); assert.equal((await web.status()).desktop.status, 'not-applicable')
})
await check('Desktop detection failure does not block update detection', async () => {
  const broken = new CrateSetup({ home, packageRoot: pkg, platform: 'win32', resolveDesktop: async () => { throw Error('fixture detection failed') }, fetcher })
  await Promise.all([broken.prepare(), broken.checkUpdates()])
  assert.equal((await broken.status()).desktop.status, 'failed')
  assert.equal((await broken.status()).update.status, 'checked')
})
await check('multi-build receipts bind version and original hash; legacy manifest remains supported', async () => {
  const multi = { ...manifest, supportedBuilds: { '0.2.1-rc.5': hash('old-official'), '0.2.2-rc.3': hash('new-official') } }
  delete multi.originalSha256
  await writeFile(join(pkg, 'packaging/desktop-bootstrap/manifest.json'), JSON.stringify(multi))
  const inspect = async () => { const s = new CrateSetup({ home, packageRoot: pkg, desktopRoot: target, platform: 'win32', fetcher }); await s.prepare(); return (await s.status()).desktop.status }
  for (const original of ['old-official', 'new-official']) {
    await writeFile(join(target, 'resources/app.asar'), original)
    assert.equal(await inspect(), 'ready')
  }
  await writeFile(join(target, 'resources/app.asar'), 'patched')
  await writeFile(join(target, 'resources/app.asar.crate-original'), 'old-official')
  const receipt = { version: '0.2.1-rc.5', originalSha256: hash('old-official'), patchedSha256: hash('patched'), componentId: multi.id }
  await writeFile(join(target, 'resources/crate-profile-patch.json'), JSON.stringify(receipt))
  assert.equal(await inspect(), 'installed')
  await writeFile(join(target, 'resources/crate-profile-patch.json'), JSON.stringify({ ...receipt, version: '0.2.2-rc.3' }))
  assert.equal(await inspect(), 'unsupported')
  await writeFile(join(target, 'resources/crate-profile-patch.json'), JSON.stringify(receipt))
  await writeFile(join(target, 'resources/app.asar.crate-original'), 'changed')
  assert.equal(await inspect(), 'failed')
})
await writeFile(join(root, 'report.json'), JSON.stringify({ status: 'PASS', checks, desktopWindowsOpened: 0 }, null, 2))
console.log(JSON.stringify({ status: 'PASS', checks: checks.length, report: join(root, 'report.json') }))
