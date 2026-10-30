import assert from 'node:assert/strict'
import { mkdir, mkdtemp, readFile, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { prepareVerifyArgs } from '../src/verify.ts'

const root = await mkdtemp(join(process.argv[2], 'bridge-'))
const profilePath = join(root, 'profile')
await mkdir(profilePath)
await writeFile(join(profilePath, 'package.json'), '{}')
const defaults = { mode: 'web', profilePath, workDirectory: join(root, 'work'),
  defaultConfig: { kind: 'desktop', mode: 'web', maximumBoots: 1, modelRequests: 0, automaticRetries: 0 } }
const first = await prepareVerifyArgs(['verify'], defaults)
assert.equal(first.source, 'bundled-desktop')
const configPath = first.args[first.args.indexOf('--runner-config') + 1]
assert.deepEqual(JSON.parse(await readFile(configPath, 'utf8')), defaults.defaultConfig)
const hostSource = await readFile(new URL('../src/index.ts', import.meta.url), 'utf8')
assert.match(hostSource, /maximumBoots: 1, modelRequests: 0, automaticRetries: 0/)
const path = join(root, 'host.json')
await writeFile(path, '{"mode":"web","kind":"explicit-host"}')
assert.equal((await prepareVerifyArgs([], { ...defaults, configuredPath: path })).source, 'host-environment')
assert.equal((await prepareVerifyArgs([], { ...defaults, configuredPath: 'invalid', requestConfig: { mode: 'web' } })).source, 'request')
await assert.rejects(prepareVerifyArgs([], { ...defaults, mode: 'headless' }), /mode/)
console.log(JSON.stringify({ status: 'PASS', cases: 5, scope: 'builtin fallback, one-verifier startup cap, explicit priority and mode guard' }))
