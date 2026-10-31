/** Run with exact bundled Electron in Node mode; no desktop or Worker starts. */
import assert from 'node:assert/strict'
import { mkdir, readFile, writeFile, symlink } from 'node:fs/promises'
import { join, resolve } from 'node:path'
import { DesktopController, isolatedEnvironment, copyRegularTree, validateSurface } from '../verify-desktop.mjs'

const root = resolve(process.argv[2])
const runtimeRoot = process.argv[3]
await mkdir(root)
const sourceHome = join(root, 'source')
const profile = join(sourceHome, 'profiles', 'desktop')
await mkdir(profile, { recursive: true })
await writeFile(join(profile, 'package.json'), '{"dependencies":{},"dsh":{"profile":{"bundles":[]}}}')
await writeFile(join(profile, 'cordis.yml'), '[]')
await writeFile(join(profile, 'cordis.patch.yml'), JSON.stringify([
  { id: 'workspace-controller', config: { documentsDirectory: join(root, 'old-documents') } },
  { id: 'dsh-crate-web', config: { windowsTerminalCompatibility: false } },
  { id: 'llm-pi-ai', config: { providers: { test: { apiKey: 'SENSITIVE_FIXTURE_VALUE', baseURL: 'https://example.invalid/v1', retryPolicy: { maxRetries: 7 } } } } },
]))
const job = join(sourceHome, '.dsh-pack', 'verify-jobs', 'static-one')
await mkdir(job, { recursive: true })
const config = { job, sourceHome, sourceProfile: 'desktop', runtimeRoot, desktopExecutable: process.execPath, maximumBoots: 1 }
const exhausted = new DesktopController(config)
exhausted.generation = 1
await assert.rejects(exhausted.boot(), /boot limit reached/)
const controller = new DesktopController(config)
const prepared = await controller.prepare()
assert.equal(prepared.requiredPluginsRemoved, false)
assert.equal(prepared.credentialsFilesCopied, false)
const output = await readFile(join(job, 'home/profiles/desktop/cordis.patch.yml'), 'utf8')
assert.equal(output.includes('SENSITIVE_FIXTURE_VALUE'), false)
assert.match(output, /127\.0\.0\.1:9/)
assert.match(output, /maxRetries: 0/)
assert.equal(/id: dsh-crate-web\s+disabled: true/.test(output), false)
const ready = { protocol: 'dsh-app:', hostname: 'app', origin: 'dsh-app://app', accountMenu: true,
  httpStatus: 200, backendHttpStatus: 200, backendStatus: 'ok', runtimePid: 17,
  runtimeHome: controller.home, runtimeProfile: 'desktop', runtimeInventoryComplete: true,
  runtimePlugins: [{ id: 'workspace-controller', name: '@deepseek-ai/dsh-api-workspace-controller', enabled: true, phase: 'active' }] }
assert.equal(validateSurface(ready, controller.home, 56789).webPort, 56789)
assert.equal(validateSurface({ ...ready, origin: 'null' }, controller.home, 56789).webPort, 56789)
assert.throws(() => validateSurface({ ...ready, hostname: 'shell' }, controller.home, 56789), /ready failed/)
assert.throws(() => validateSurface({ ...ready, backendHttpStatus: 401 }, controller.home, 56789), /ready failed/)
assert.throws(() => validateSurface({ ...ready, runtimeHome: sourceHome }, controller.home, 56789), /identity/)
assert.throws(() => validateSurface(ready, controller.home, 0), /port missing/)
controller.browser = { evaluate: async () => ready }
await writeFile(join(job, 'desktop-0.stdout.log'), 'dsh web: http://127.0.0.1:56789/?token=DO_NOT_EXPORT_FIXTURE_TOKEN\n')
assert.equal((await controller.surface()).runtimePid, 17)
const events = await readFile(join(job, 'controller-events.jsonl'), 'utf8')
assert.match(events, /surface.observation/)
assert.equal(events.includes('DO_NOT_EXPORT_FIXTURE_TOKEN'), false)
const env = isolatedEnvironment({ API_KEY: 'SENSITIVE_FIXTURE_VALUE', ELECTRON_RUN_AS_NODE: '1', DSH_HOME: 'outside', Path: 'ok', AUTH: 'secret', NODE_OPTIONS: '--bad' }, job, join(job, 'home'))
assert.equal(env.API_KEY, undefined)
assert.equal(env.NODE_OPTIONS, undefined)
assert.equal(env.ELECTRON_RUN_AS_NODE, undefined)
assert.equal(env.AUTH, undefined)
assert.equal(env.DSH_HOME, join(job, 'home'))
assert.equal(env.TEMP, join(job, 'tmp'))
const link = join(root, 'linked')
await symlink(profile, link, 'junction')
await assert.rejects(copyRegularTree(link, join(root, 'refused')), /reparse/)
await assert.rejects(copyRegularTree(join(profile, 'package.json'), join(root, 'oversized'), { files: 15000, bytes: 0 }), /bounded/)
await writeFile(join(sourceHome, 'cordis.patch.yml'), '[{"id":"llm-deepseek","disabled":false}]')
const job2 = join(sourceHome, '.dsh-pack', 'verify-jobs', 'static-two')
await mkdir(job2)
await assert.rejects(new DesktopController({ ...config, job: job2 }).prepare(), /Nonempty Home overlay/)
await assert.rejects(new DesktopController({ ...config, job: join(root, 'escaped') }).prepare(), /escaped/)
console.log(JSON.stringify({ status: 'PASS', cases: 25, desktopStarts: 0, workerStarts: 0, modelRequests: 0, scope: 'packaged Node-mode isolation, startup cap, official origin, backend identity and no-token evidence guards' }))
