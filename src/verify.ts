/** Default Web Verify arguments; execution and status decisions remain in Core. */
import { randomUUID } from 'node:crypto'
import { lstat, mkdir, readFile, writeFile } from 'node:fs/promises'
import { isAbsolute, join } from 'node:path'

type JsonObject = Record<string, unknown>

const KNOWN_SMOKES: Record<string, readonly string[]> = {
  '@deepseek-ai/dsh-base': ['newSessionPersistsAcrossRestart'],
  '@deepseek-ai/dsh-web-app': ['workspaceRendered'],
  '@deepseek-ai/dsh-experimental-terminal-bundle': ['coreCapability'],
  '@deepseek-ai/dsh-experimental-session-search': ['coreCapability'],
  '@deepseek-ai/dsh-experimental-inspector-profile': ['cordisDomQuery'],
  'dsh-crate-web': ['preflightDownloadedPack'],
}

function object(value: unknown): value is JsonObject {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

export interface VerifyArgumentOptions {
  mode: 'web' | 'headless'
  profilePath: string
  workDirectory: string
  requestConfig?: unknown
  configuredPath?: string
  defaultConfig?: JsonObject
}

async function configuredRunner(path: string): Promise<JsonObject> {
  if (!isAbsolute(path)) throw new Error('DSH_PACK_VERIFY_RUNNER_CONFIG must be an absolute JSON file path')
  const info = await lstat(path)
  if (!info.isFile() || info.isSymbolicLink()) throw new Error('Verify runner config must be a regular JSON file')
  if (info.size > 1024 * 1024) throw new Error('Verify runner config exceeds the 1 MiB size limit')
  let value: unknown
  try { value = JSON.parse(await readFile(path, 'utf8')) }
  catch { throw new Error('Verify runner config must contain valid JSON') }
  if (!object(value)) throw new Error('Verify runner config must be a JSON object')
  return value
}

async function installedNames(profilePath: string): Promise<Set<string>> {
  // A malformed/missing Profile must still reach Core's full composition diagnosis.
  let manifest: unknown
  try { manifest = JSON.parse(await readFile(join(profilePath, 'package.json'), 'utf8')) }
  catch { return new Set() }
  if (!object(manifest)) return new Set()
  const names = new Set(object(manifest.dependencies) ? Object.keys(manifest.dependencies) : [])
  const dsh = object(manifest.dsh) ? manifest.dsh : {}
  const profile = object(dsh.profile) ? dsh.profile : {}
  if (Array.isArray(profile.bundles)) {
    for (const name of profile.bundles) if (typeof name === 'string') names.add(name)
  }
  return names
}

export async function prepareVerifyArgs(base: readonly string[], options: VerifyArgumentOptions): Promise<{
  args: string[]
  source: 'request' | 'host-environment' | 'bundled-desktop' | 'unconfigured'
}> {
  let runner: JsonObject | undefined
  let source: 'request' | 'host-environment' | 'bundled-desktop' | 'unconfigured' = 'unconfigured'
  if (options.requestConfig !== undefined) {
    if (!object(options.requestConfig)) throw new Error('runnerConfig must be a JSON object')
    runner = options.requestConfig
    source = 'request'
  } else if (options.configuredPath) {
    runner = await configuredRunner(options.configuredPath)
    source = 'host-environment'
  } else if (options.defaultConfig) {
    runner = options.defaultConfig
    source = 'bundled-desktop'
  }
  if (runner?.mode !== undefined && runner.mode !== options.mode) {
    throw new Error('Verify runner mode must match the requested Verify mode')
  }
  const names = await installedNames(options.profilePath)
  const configured = object(runner?.pluginTests) ? runner.pluginTests : {}
  const contracts: { plugin: string; required: false; tests: string[] }[] = []
  for (const plugin of names) {
    const probes = object(configured[plugin]) ? Object.keys(configured[plugin]).filter(name => name.trim()) : []
    const tests = probes.length ? probes : KNOWN_SMOKES[plugin]
    if (tests?.length) contracts.push({ plugin, required: false, tests: [...tests] })
    // Core's imported lock raises required=true; optional plugins stay optional.
    // Core also accounts for imported plugins without a known contract.
  }
  const args = [...base]
  if (runner || contracts.length) await mkdir(options.workDirectory, { recursive: true })
  const operation = randomUUID()
  if (runner) {
    const path = join(options.workDirectory, `verify-${operation}.json`)
    await writeFile(path, JSON.stringify(runner, null, 2) + '\n', { encoding: 'utf8', flag: 'wx', mode: 0o600 })
    args.push('--runner-config', path)
  }
  if (contracts.length) {
    const path = join(options.workDirectory, `verify-${operation}-contracts.json`)
    await writeFile(path, JSON.stringify(contracts, null, 2) + '\n', { encoding: 'utf8', flag: 'wx', mode: 0o600 })
    args.push('--plugin-contract', path)
  }
  return { args, source }
}
