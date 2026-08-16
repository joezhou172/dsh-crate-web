/** Host half: a small local HTTP bridge to the installed dsh-crate Core CLI. */

import { randomUUID } from 'node:crypto'
import { createReadStream } from 'node:fs'
import { access, cp, mkdir, readFile, readdir, stat, writeFile } from 'node:fs/promises'
import { platform as osPlatform } from 'node:os'
import { dirname, join, relative, resolve } from 'node:path'
import { spawn } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import type { IncomingMessage, ServerResponse } from 'node:http'
import type { Context } from '@deepseek-ai/cordis'
import type {} from '@deepseek-ai/dsh-host-webserver'
import { readHistory, record } from './history.ts'

const API_PATH = '/dsh-crate/api'
const DOWNLOAD_PATH = '/dsh-crate/download'
const MAX_BODY_BYTES = 64 * 1024 * 1024
const SAFE_NAME = /^[A-Za-z0-9._-]+$/
const SAFE_PLUGIN_NAME = /^@?[A-Za-z0-9._-]+(?:\/[A-Za-z0-9._-]+)?$/
const SAFE_OPERATION_ID = /^[0-9a-f-]{36}$/i
const CRATE_PACKAGE_NAME = 'dsh-crate-web'

type JsonObject = Record<string, unknown>
type Action = 'profiles' | 'history' | 'inspect' | 'export' | 'import' | 'delete-profile' | 'create-profile' | 'switch-profile' | 'switch-status' | 'verify'

interface CoreRun {
  code: number
  stdout: string
  stderr: string
}

interface CoreCommand {
  command: string
  prefix: string[]
  env?: NodeJS.ProcessEnv
}

/** Minimal structural projection of the Cordis Loader entry tree used by DSH. */
interface LoaderEntryOptions {
  id: string
  name: string
  group?: boolean | null
  disabled?: boolean | null
}

interface LoaderEntry {
  id: string
  options: LoaderEntryOptions
  readonly disabled: boolean
  fiber?: { state: number } | undefined
}

interface RuntimeLoader {
  entries(): Iterable<LoaderEntry>
}

declare module '@deepseek-ai/cordis' {
  interface Context {
    loader?: RuntimeLoader
  }
}

/** Cordis FiberState enum values; mirrors dsh-host-plugin-inventory phases. */
const RUNTIME_FIBER_PHASE: Record<number, string | null> = {
  0: 'pending', 1: 'loading', 2: 'active', 3: 'failed', 4: null, 5: 'unloading',
}

/** Read-only projection of the currently running Loader's non-group entries. */
function listRuntimePlugins(ctx: Context): JsonObject[] {
  const loader = ctx.loader
  if (!loader || typeof loader.entries !== 'function') return []
  const rows: JsonObject[] = []
  try {
    for (const entry of loader.entries()) {
      if (entry.options.group) continue
      if (entry.options.name.startsWith('cordis:')) continue
      rows.push({
        id: entry.id,
        name: entry.options.name,
        enabled: entry.disabled !== true,
        phase: entry.fiber ? (RUNTIME_FIBER_PHASE[entry.fiber.state] ?? null) : null,
      })
    }
  } catch {
    // The Loader tree may be mid-teardown during a restart; the next poll re-reads it.
  }
  return rows
}

function json(res: ServerResponse, status: number, body: JsonObject): void {
  const payload = JSON.stringify(body)
  res.writeHead(status, {
    'content-type': 'application/json; charset=utf-8',
    'cache-control': 'no-store',
  })
  res.end(payload)
}

function failMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

function safeName(value: unknown, label: string): string {
  if (typeof value !== 'string' || !SAFE_NAME.test(value)) {
    throw new Error(`${label} must be a simple file or Profile name`)
  }
  return value
}

function safePluginName(value: unknown, label: string): string {
  if (typeof value !== 'string' || !SAFE_PLUGIN_NAME.test(value)) {
    throw new Error(`${label} must be a valid package name`)
  }
  return value
}

async function readRequest(req: IncomingMessage): Promise<JsonObject> {
  const chunks: Buffer[] = []
  let length = 0
  for await (const chunk of req) {
    const bytes = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk)
    length += bytes.length
    if (length > MAX_BODY_BYTES) throw new Error('request body is too large')
    chunks.push(bytes)
  }
  if (length === 0) return {}
  const value: unknown = JSON.parse(Buffer.concat(chunks).toString('utf8'))
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('request body must be a JSON object')
  }
  return value as JsonObject
}

function decodePack(value: unknown): Buffer {
  if (typeof value !== 'string' || value.length === 0) throw new Error('packBase64 is required')
  const pack = Buffer.from(value, 'base64')
  if (pack.length === 0) throw new Error('packBase64 is empty')
  return pack
}

async function ensureWorkspace(home: string): Promise<{ root: string; exports: string; work: string; history: string }> {
  const root = join(home, '.dsh-pack')
  const exports = join(root, 'exports')
  const work = join(root, 'ui-work')
  const history = join(root, 'ui-history.json')
  await mkdir(exports, { recursive: true })
  await mkdir(work, { recursive: true })
  return { root, exports, work, history }
}

async function bundledCorePath(): Promise<string | undefined> {
  const packageRoot = dirname(dirname(fileURLToPath(import.meta.url)))
  const core = join(packageRoot, 'core')
  try {
    await access(join(core, 'dsh_pack', '__main__.py'))
    return core
  } catch {
    return undefined
  }
}

async function bundledRuntimeCommand(): Promise<CoreCommand | undefined> {
  const packageRoot = dirname(dirname(fileURLToPath(import.meta.url)))
  const command = join(packageRoot, 'runtime', 'python', 'python.exe')
  try {
    await access(command)
    return { command, prefix: ['-B', '-m', 'dsh_pack'] }
  } catch {
    return undefined
  }
}

function configuredCoreCommand(): CoreCommand | undefined {
  if (!process.env.DSH_PACK_CLI) return undefined
  let prefix: string[] = []
  if (process.env.DSH_PACK_CLI_PREFIX) {
    const parsed: unknown = JSON.parse(process.env.DSH_PACK_CLI_PREFIX)
    if (!Array.isArray(parsed) || parsed.some(item => typeof item !== 'string')) throw new Error('DSH_PACK_CLI_PREFIX must be a JSON string array')
    prefix = parsed
  }
  return { command: process.env.DSH_PACK_CLI, prefix }
}

function isCommandNotFound(error: unknown): boolean {
  return isObject(error) && error.code === 'ENOENT'
}

async function spawnCore(home: string, command: CoreCommand, args: string[]): Promise<CoreRun> {
  return await new Promise((resolveRun, reject) => {
    const child = spawn(command.command, [...command.prefix, ...args], {
      cwd: home,
      env: {
        ...process.env,
        ...command.env,
        DSH_HOME: home,
        DSH_PACK_CORE_MODE: '1',
        PYTHONDONTWRITEBYTECODE: '1',
      },
      shell: false,
      windowsHide: true,
    })
    const stdout: Buffer[] = []
    const stderr: Buffer[] = []
    child.stdout.on('data', chunk => stdout.push(Buffer.from(chunk)))
    child.stderr.on('data', chunk => stderr.push(Buffer.from(chunk)))
    child.once('error', reject)
    child.once('close', code => resolveRun({
      code: code ?? 1,
      stdout: Buffer.concat(stdout).toString('utf8'),
      stderr: Buffer.concat(stderr).toString('utf8'),
    }))
  })
}

async function runCore(home: string, args: string[]): Promise<CoreRun> {
  const configured = configuredCoreCommand()
  if (configured) return spawnCore(home, configured, args)

  const candidates: CoreCommand[] = []
  const bundledRuntime = await bundledRuntimeCommand()
  if (bundledRuntime) candidates.push(bundledRuntime)
  candidates.push({ command: 'dsh-crate', prefix: [] })
  const bundled = await bundledCorePath()
  if (bundled) {
    const pythonPath = [bundled, process.env.PYTHONPATH].filter(Boolean).join(process.platform === 'win32' ? ';' : ':')
    candidates.push(
      { command: 'python', prefix: ['-B', '-m', 'dsh_pack'], env: { PYTHONPATH: pythonPath } },
      { command: 'python3', prefix: ['-B', '-m', 'dsh_pack'], env: { PYTHONPATH: pythonPath } },
      { command: 'py', prefix: ['-3', '-B', '-m', 'dsh_pack'], env: { PYTHONPATH: pythonPath } },
    )
  }

  let lastError: unknown
  for (const candidate of candidates) {
    try {
      return await spawnCore(home, candidate, args)
    } catch (error) {
      lastError = error
      if (!isCommandNotFound(error)) throw error
    }
  }
  throw new Error(`DSH Crate Core is unavailable: ${failMessage(lastError)}. Install dsh-crate or keep the bundled Core runner in the plugin package.`)
}

function parseCore(stdout: string): unknown {
  const value: unknown = JSON.parse(stdout)
  return value
}

function isObject(value: unknown): value is JsonObject {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

function coreDiagnostic(result: unknown, fallback: string): JsonObject {
  if (isObject(result) && isObject(result.error)) return result.error
  return { message: fallback }
}

function runtimeCoreArgs(): string[] {
  const args = [
    '--node-version', process.version.replace(/^v/, ''),
    '--os-name', osPlatform() === 'win32' ? 'windows' : osPlatform(),
  ]
  // The host cannot safely infer the DSH launcher version from Node. A DSH
  // deployment may provide it explicitly; otherwise Core leaves that check
  // unknown instead of manufacturing a mismatch.
  if (process.env.DSH_VERSION) args.push('--dsh-version', process.env.DSH_VERSION)
  return args
}

function argumentValue(args: string[], flag: string): string | undefined {
  const index = args.indexOf(flag)
  return index >= 0 && typeof args[index + 1] === 'string' ? args[index + 1] : undefined
}

function replaceArgument(args: string[], flag: string, value: string): string[] {
  const next = [...args]
  const index = next.indexOf(flag)
  if (index >= 0 && index + 1 < next.length) next[index + 1] = value
  else next.push(flag, value)
  return next
}

function currentRuntime(home: string): JsonObject {
  const args = process.argv.slice(2)
  const portValue = argumentValue(args, '--port') ?? process.env.DSH_PACK_PORT
  const port = portValue !== undefined && /^\d+$/.test(portValue) ? Number(portValue) : undefined
  return {
    currentProfile: argumentValue(args, '--profile') ?? process.env.DSH_PACK_ACTIVE_PROFILE ?? null,
    pid: process.pid,
    dshHome: home,
    port: port ?? null,
    restartConfigured: typeof process.argv[1] === 'string' && port !== undefined,
  }
}

function operationDiagnostic(code: string, stage: string, item: string, message: string, impact: string, suggestedNextStep: string): JsonObject {
  return {
    code,
    stage,
    severity: 'BLOCKER',
    item,
    expected: 'the requested Profile operation completes safely',
    observed: message,
    evidence: { code, stage, item },
    impact,
    canContinue: false,
    suggestedNextStep,
    suggestedChecks: [
      'confirm the exact Profile name and operation evidence above',
      'verify the target DSH_HOME and Profile path are correct',
      'retry after correcting the reported item',
    ],
    message,
  }
}

async function savePack(work: string, action: string, value: unknown): Promise<string> {
  const path = join(work, `${action}-${randomUUID()}.dshcrate`)
  await writeFile(path, decodePack(value), { flag: 'wx' })
  return path
}

async function readInstalledBundle(packagePath: string, location: string): Promise<JsonObject | undefined> {
  try {
    const packageJson: unknown = JSON.parse(await readFile(join(packagePath, 'package.json'), 'utf8'))
    if (!isObject(packageJson)) return undefined
    const dsh = packageJson.dsh
    const bundle = dsh !== null && typeof dsh === 'object' && !Array.isArray(dsh)
      ? (dsh as JsonObject).bundle
      : undefined
    if (bundle === null || typeof bundle !== 'object' || Array.isArray(bundle)) return undefined
    const patch = (bundle as JsonObject).patch
    if (typeof packageJson.name !== 'string' || typeof packageJson.version !== 'string' || typeof patch !== 'string' || patch.trim() === '') return undefined
    return { name: packageJson.name, version: packageJson.version, patch, location }
  } catch {
    return undefined
  }
}

let profileInvariantPromise: Promise<void> | undefined

async function ensureCrateBundleInAllProfilesOnce(home: string): Promise<void> {
  const profilesRoot = join(home, 'profiles')
  let entries
  try {
    entries = await readdir(profilesRoot, { withFileTypes: true })
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === 'ENOENT') return
    throw error
  }

  const packageRoot = dirname(dirname(fileURLToPath(import.meta.url)))
  const sourceManifest = JSON.parse(await readFile(join(packageRoot, 'package.json'), 'utf8')) as JsonObject
  const sourceVersion = typeof sourceManifest.version === 'string' ? sourceManifest.version : undefined
  if (sourceVersion === undefined) throw new Error('DSH Crate package version is missing')

  const anchorPackage = join(profilesRoot, 'node_modules', ...CRATE_PACKAGE_NAME.split('/'))
  let anchorManifest: JsonObject | undefined
  try {
    const value: unknown = JSON.parse(await readFile(join(anchorPackage, 'package.json'), 'utf8'))
    if (isObject(value)) anchorManifest = value
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error
  }
  if (anchorManifest === undefined && resolve(packageRoot) !== resolve(anchorPackage)) {
    try {
      await stat(anchorPackage)
      throw new Error(`DSH Crate installation anchor exists but has no valid package.json: ${anchorPackage}`)
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error
    }
    await mkdir(dirname(anchorPackage), { recursive: true })
    await cp(packageRoot, anchorPackage, { recursive: true })
    const value: unknown = JSON.parse(await readFile(join(anchorPackage, 'package.json'), 'utf8'))
    if (isObject(value)) anchorManifest = value
  }
  const crateVersion = typeof anchorManifest?.version === 'string' ? anchorManifest.version : sourceVersion

  for (const entry of entries) {
    if (!entry.isDirectory() || !SAFE_NAME.test(entry.name)) continue
    const manifestPath = join(profilesRoot, entry.name, 'package.json')
    let manifest: JsonObject
    try {
      const value: unknown = JSON.parse(await readFile(manifestPath, 'utf8'))
      if (!isObject(value)) continue
      manifest = value
    } catch {
      continue
    }

    const dependenciesValue = manifest.dependencies
    if (dependenciesValue !== undefined && !isObject(dependenciesValue)) continue
    const dependencies = isObject(dependenciesValue) ? dependenciesValue : {}
    const dshValue = manifest.dsh
    if (dshValue !== undefined && !isObject(dshValue)) continue
    const dsh = isObject(dshValue) ? dshValue : {}
    const profileValue = dsh.profile
    if (profileValue !== undefined && !isObject(profileValue)) continue
    const profile = isObject(profileValue) ? profileValue : {}
    const bundlesValue = profile.bundles
    if (bundlesValue !== undefined && (!Array.isArray(bundlesValue) || bundlesValue.some(item => typeof item !== 'string'))) continue
    const bundles = Array.isArray(bundlesValue) ? [...bundlesValue] : []

    let changed = false
    if (typeof dependencies[CRATE_PACKAGE_NAME] !== 'string') {
      dependencies[CRATE_PACKAGE_NAME] = crateVersion
      changed = true
    }
    if (!bundles.includes(CRATE_PACKAGE_NAME)) {
      bundles.push(CRATE_PACKAGE_NAME)
      changed = true
    }
    if (!changed) continue

    manifest.dependencies = dependencies
    manifest.dsh = { ...dsh, profile: { ...profile, bundles } }
    await writeFile(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`, 'utf8')
  }
}

async function ensureCrateBundleInAllProfiles(home: string): Promise<void> {
  if (profileInvariantPromise !== undefined) return profileInvariantPromise
  profileInvariantPromise = ensureCrateBundleInAllProfilesOnce(home)
  try {
    await profileInvariantPromise
  } finally {
    profileInvariantPromise = undefined
  }
}

async function listInstalledBundles(profileModules: string, anchorModules: string): Promise<JsonObject[]> {
  const bundles = new Map<string, JsonObject>()
  const addBundle = (bundle: JsonObject | undefined) => {
    if (bundle === undefined || typeof bundle.name !== 'string' || bundles.has(bundle.name)) return
    bundles.set(bundle.name, bundle)
  }
  const scanRoot = async (root: string, location: string): Promise<void> => {
    let entries
    try {
      entries = await readdir(root, { withFileTypes: true })
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === 'ENOENT') return
      throw error
    }
    for (const entry of entries) {
      if (entry.name.startsWith('.')) continue
      const candidate = join(root, entry.name)
      const direct = await readInstalledBundle(candidate, location)
      if (direct !== undefined) {
        addBundle(direct)
        continue
      }
      if (!entry.name.startsWith('@')) continue
      let scopedEntries
      try {
        scopedEntries = await readdir(candidate, { withFileTypes: true })
      } catch (error) {
        if ((error as NodeJS.ErrnoException).code === 'ENOENT') continue
        throw error
      }
      for (const scopedEntry of scopedEntries) {
        if (scopedEntry.name.startsWith('.')) continue
        addBundle(await readInstalledBundle(join(candidate, scopedEntry.name), location))
      }
    }
  }
  await scanRoot(profileModules, 'profile')
  await scanRoot(anchorModules, 'installation-anchor')
  return [...bundles.values()].sort((left, right) => String(left.name).localeCompare(String(right.name)))
}

/**
 * Packages published by the DSH project are treated as official built-ins.
 * This is the single source of truth for the official/user split used by the
 * plugin inventory UI: a runtime loader row is official only when the package
 * itself is an official bundle. Loader row ids are deliberately NOT used,
 * because a user plugin may register a row id that collides with an official
 * built-in (for example a custom sidebar) and must stay in the user group.
 */
function isOfficialPackage(name: string): boolean {
  return name.startsWith('@deepseek-ai/')
}

/** Collect loader row ids registered via top-level ``insert`` blocks. */
function insertedLoaderIds(patchText: string): string[] {
  const ids: string[] = []
  let inInsert = false
  let insertIndent: number | undefined
  for (const raw of patchText.split(/\r?\n/)) {
    const line = raw.replace(/\s+$/, '')
    const stripped = line.trim()
    if (!stripped || stripped.startsWith('#')) continue
    const indent = line.length - line.trimStart().length
    if (indent === 0 && stripped.startsWith('- ')) {
      const key = stripped.slice(2).trim()
      inInsert = key === 'insert:'
      insertIndent = undefined
      continue
    }
    if (!inInsert) continue
    if (!stripped.startsWith('- ')) continue
    if (insertIndent === undefined) insertIndent = indent
    if (indent !== insertIndent) continue
    const row = stripped.slice(2).trim()
    if (row.startsWith('id:')) {
      const value = row.slice(3).trim().replace(/^["']|["']$/g, '')
      if (value) ids.push(value)
    }
  }
  return ids
}

/** Loader row ids registered by one installed Bundle patch. */
async function installedBundlePatchIds(home: string, profileName: string, bundleName: string, patch: string): Promise<Set<string>> {
  const ids = new Set<string>()
  const segments = bundleName.split('/')
  const candidates = [
    join(home, 'profiles', profileName, 'node_modules', ...segments),
    join(home, 'profiles', 'node_modules', ...segments),
  ]
  for (const candidate of candidates) {
    try {
      const patchText = await readFile(join(candidate, patch), 'utf8')
      for (const id of insertedLoaderIds(patchText)) ids.add(id)
      break
    } catch {
      // Try the next resolution root; a missing patch leaves an empty set.
    }
  }
  return ids
}


async function listProfiles(home: string): Promise<JsonObject[]> {
  const root = join(home, 'profiles')
  try {
    const entries = await readdir(root, { withFileTypes: true })
    const profiles: JsonObject[] = []
    for (const entry of entries) {
      if (!entry.isDirectory() || !SAFE_NAME.test(entry.name)) continue
      try {
        const packageJson: unknown = JSON.parse(await readFile(join(root, entry.name, 'package.json'), 'utf8'))
        if (packageJson === null || typeof packageJson !== 'object' || Array.isArray(packageJson)) continue
        const manifest = packageJson as JsonObject
        const dsh = manifest.dsh
        const profile = dsh !== null && typeof dsh === 'object' && !Array.isArray(dsh)
          ? (dsh as JsonObject).profile
          : undefined
        const bundles = profile !== null && typeof profile === 'object' && !Array.isArray(profile)
          ? (profile as JsonObject).bundles
          : []
        const dependencies = manifest.dependencies
        const dependencyNames = dependencies !== null && typeof dependencies === 'object' && !Array.isArray(dependencies)
          ? Object.keys(dependencies as JsonObject)
          : []
        // Only Bundles declared in dsh.profile.bundles are composed at boot. A
        // plain dependency is installed but not mounted: it may even insert a
        // loader row that duplicates an official built-in and must not be
        // exported as an active Bundle.
        const composedBundles = Array.isArray(bundles) ? bundles.filter((name): name is string => typeof name === 'string') : []
        const activePlugins = new Set(composedBundles)
        const installedBundles = (await listInstalledBundles(
          join(root, entry.name, 'node_modules'),
          join(root, 'node_modules'),
        ))
          .map(bundle => ({
            ...bundle,
            active: activePlugins.has(String(bundle.name)),
            official: isOfficialPackage(String(bundle.name)),
          }))
          // A Profile's plugin list is its declared Bundles plus any
          // dependency that is itself an installed Bundle package. Packages
          // hoisted into the shared installation anchor by the DSH runtime
          // (for example official DSH UI modules and their transitive
          // bundles) are not Profile plugins and must not be listed.
          .filter(bundle => bundle.active === true || dependencyNames.includes(String(bundle.name)))
        const activeRowIds = new Set<string>()
        const installedRowIds = new Map<string, Set<string>>()
        for (const bundle of installedBundles) {
          if (typeof bundle.patch !== 'string') continue
          const rowIds = await installedBundlePatchIds(home, entry.name, String(bundle.name), bundle.patch)
          installedRowIds.set(String(bundle.name), rowIds)
          if (bundle.active === true) for (const id of rowIds) activeRowIds.add(id)
        }
        const conflicts = new Map<string, boolean>()
        for (const bundle of installedBundles) {
          if (bundle.active === true) continue
          const rowIds = installedRowIds.get(String(bundle.name)) ?? new Set<string>()
          for (const id of rowIds) {
            if (activeRowIds.has(id)) {
              conflicts.set(String(bundle.name), true)
              break
            }
          }
        }
        const composedInstalledBundles = installedBundles.map(bundle => ({
          ...bundle,
          conflict: conflicts.get(String(bundle.name)) === true,
        }))
        profiles.push({ name: entry.name, plugins: [...activePlugins], installedBundles: composedInstalledBundles })
      } catch {
        // A half-created/non-Profile directory is not a selectable Profile.
      }
    }
    return profiles.sort((a, b) => String(a.name).localeCompare(String(b.name)))
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === 'ENOENT') return []
    throw error
  }
}

const PROFILE_PATCH_TEMPLATE = `# Your patch layer for this dsh profile, applied after every bundle layer:
# a top-level YAML array of loader patch entries (id-targeted config
# overrides, disables, and insert lists; \`!!js\` expressions allowed).
[]
`

const PROFILE_PNPM_WORKSPACE = `packages:
  - .

nodeLinker: hoisted
autoInstallPeers: false
`

/** Official bundles every newly created Profile composes by default. */
const DEFAULT_CREATE_BUNDLES = ['@deepseek-ai/dsh-base', '@deepseek-ai/dsh-web-app', CRATE_PACKAGE_NAME]

async function readInstalledVersion(packageRoot: string): Promise<string | undefined> {
  try {
    const value: unknown = JSON.parse(await readFile(join(packageRoot, 'package.json'), 'utf8'))
    if (isObject(value) && typeof value.version === 'string' && value.version !== '') return value.version
    return undefined
  } catch {
    return undefined
  }
}

async function createProfile(home: string, body: JsonObject, workspace: { root: string; exports: string; work: string; history: string }): Promise<JsonObject> {
  const profileName = safeName(body.profileName, 'profileName')
  if (profileName === '.' || profileName === '..' || profileName === 'node_modules') {
    const error = operationDiagnostic('PROFILE_NAME_RESERVED', 'planning', profileName, `Profile name is reserved: ${profileName}`, 'The requested Profile was not created.', 'Choose another Profile name and retry.')
    return { status: 'failed', command: 'create-profile', exitCode: 2, error }
  }
  const profilesRoot = join(home, 'profiles')
  const profileDir = join(profilesRoot, profileName)
  const profileRelative = relative(profilesRoot, resolve(profileDir))
  if (!profileRelative || profileRelative.startsWith('..') || profileRelative.includes('\\')) throw new Error('profileName escaped DSH_HOME')
  try {
    await access(join(profileDir, 'package.json'))
    const error = operationDiagnostic('PROFILE_EXISTS', 'planning', profileName, `Profile already exists: ${profileName}`, 'No Profile was created or modified.', 'Choose a different Profile name, or delete the existing Profile first.')
    return { status: 'failed', command: 'create-profile', exitCode: 2, error }
  } catch {
    // Expected: the Profile does not exist yet.
  }

  const officialBase = await readInstalledVersion(join(profilesRoot, 'node_modules', '@deepseek-ai', 'dsh-base'))
  const officialWeb = await readInstalledVersion(join(profilesRoot, 'node_modules', '@deepseek-ai', 'dsh-web-app'))
  if (officialBase === undefined || officialWeb === undefined) {
    const missing = officialBase === undefined ? '@deepseek-ai/dsh-base' : '@deepseek-ai/dsh-web-app'
    const error = operationDiagnostic('OFFICIAL_BUNDLE_MISSING', 'planning', profileName, `cannot resolve official bundle version: ${missing}`, 'The requested Profile was not created.', `Install the official DSH bundles into this DSH_HOME first (${profilesRoot}/node_modules), then retry.`)
    return { status: 'failed', command: 'create-profile', exitCode: 2, error }
  }
  const packageRoot = dirname(dirname(fileURLToPath(import.meta.url)))
  const sourceManifest = JSON.parse(await readFile(join(packageRoot, 'package.json'), 'utf8')) as JsonObject
  const crateVersion = typeof sourceManifest.version === 'string' ? sourceManifest.version : undefined
  if (crateVersion === undefined) {
    const error = operationDiagnostic('CRATE_VERSION_MISSING', 'planning', profileName, 'DSH Crate package version is missing', 'The requested Profile was not created.', 'Repair the DSH Crate installation and retry.')
    return { status: 'failed', command: 'create-profile', exitCode: 2, error }
  }

  await mkdir(profileDir, { recursive: true })
  const manifest = {
    name: `dsh-profile-${profileName}`,
    private: true,
    dependencies: {
      '@deepseek-ai/dsh-base': officialBase,
      '@deepseek-ai/dsh-web-app': officialWeb,
      [CRATE_PACKAGE_NAME]: crateVersion,
    },
    dsh: { profile: { bundles: [...DEFAULT_CREATE_BUNDLES] } },
  }
  await writeFile(join(profileDir, 'package.json'), `${JSON.stringify(manifest, null, 2)}\n`, 'utf8')
  await writeFile(join(profileDir, 'cordis.patch.yml'), PROFILE_PATCH_TEMPLATE, 'utf8')
  await writeFile(join(profileDir, 'pnpm-workspace.yaml'), PROFILE_PNPM_WORKSPACE, 'utf8')
  await ensureCrateBundleInAllProfiles(home)
  const item = await record(workspace.history, { time: new Date().toISOString(), action: 'create-profile', status: 'PASS', profile: profileName })
  const row = (await listProfiles(home)).find(candidate => candidate.name === profileName)
  return { status: 'ok', command: 'create-profile', exitCode: 0, profile: row ?? { name: profileName, plugins: DEFAULT_CREATE_BUNDLES, installedBundles: [] }, history: item }
}

async function handleApi(home: string, body: JsonObject, runtimePlugins: JsonObject[] = []): Promise<JsonObject> {
  const action = body.action as Action
  const workspace = await ensureWorkspace(home)
  await ensureCrateBundleInAllProfiles(home)
  if (action === 'profiles') {
    const runtime = currentRuntime(home)
    const isOfficialRow = (row: JsonObject): boolean =>
      typeof row.name === 'string' && isOfficialPackage(row.name)
    const classifiedPlugins = runtimePlugins.map(row => ({ ...row, official: isOfficialRow(row) }))
    return { status: 'ok', profiles: await listProfiles(home), runtimePlugins: classifiedPlugins, runtime }
  }
  if (action === 'create-profile') return createProfile(home, body, workspace)
  if (action === 'history') return { status: 'ok', history: await readHistory(workspace.history) }

  if (action === 'inspect') {
    const pack = await savePack(workspace.work, 'inspect', body.packBase64)
    const run = await runCore(home, ['inspect', pack, '--json', '--allow-network-reference-install', ...runtimeCoreArgs()])
    try {
      const result = parseCore(run.stdout)
      let targetProfile: string | undefined
      let requestedProfileName: string | undefined
      try {
        const planArgs = ['import', pack, '--dsh-home', home, '--plan-only', '--json', ...runtimeCoreArgs()]
        if (typeof body.targetProfile === 'string') planArgs.push('--target-profile', safeName(body.targetProfile, 'targetProfile'))
        if (body.overwrite === true) planArgs.push('--overwrite')
        const planRun = await runCore(home, planArgs)
        if (planRun.code === 0) {
          const planned = parseCore(planRun.stdout)
          if (isObject(planned) && isObject(planned.plan)) {
            if (typeof planned.plan.profileName === 'string') targetProfile = planned.plan.profileName
            if (typeof planned.plan.requestedProfileName === 'string') requestedProfileName = planned.plan.requestedProfileName
          }
        }
      } catch {
        // Preflight remains useful even when an optional target plan cannot be built.
      }
      const enriched = isObject(result)
        ? { ...result, ...(targetProfile ? { targetProfile } : {}), ...(requestedProfileName ? { requestedProfileName } : {}) }
        : result
      return { status: 'ok', command: action, exitCode: run.code, result: enriched }
    } catch {
      return { status: 'failed', command: action, exitCode: run.code, error: coreDiagnostic(undefined, run.stderr || run.stdout || 'dsh-crate inspect failed') }
    }
  }

  if (action === 'export') {
    const profileName = safeName(body.profileName, 'profileName')
    const profile = join(home, 'profiles', profileName)
    const profileRelative = relative(join(home, 'profiles'), resolve(profile))
    if (!profileRelative || profileRelative.startsWith('..') || profileRelative.includes('\\')) throw new Error('profileName escaped DSH_HOME')
    const outputName = `${profileName}-${new Date().toISOString().replace(/[:.]/g, '-')}-${randomUUID()}.dshcrate`
    const output = join(workspace.exports, outputName)
    const args = ['verify', '--dsh-home', home, '--profile', profileName, '--mode', mode, '--json', ...runtimeCoreArgs()]
    let runnerConfigPath: string | undefined
    if (body.runnerConfig !== undefined) {
      if (!isObject(body.runnerConfig)) throw new Error('runnerConfig must be a JSON object')
      const verifyDir = join(workspace.work, 'verify')
      await mkdir(verifyDir, { recursive: true })
      runnerConfigPath = join(verifyDir, 'verify-' + randomUUID() + '.json')
      await writeFile(runnerConfigPath, JSON.stringify(body.runnerConfig, null, 2) + '\n', { encoding: 'utf8', flag: 'wx' })
      args.push('--runner-config', runnerConfigPath)
    }
    const run = await runCore(home, args)
    let result: unknown
    try { result = parseCore(run.stdout) } catch { result = undefined }
    if (run.code !== 0 || result === undefined) {
      const failure = { status: 'failed', action, exitCode: run.code, error: coreDiagnostic(result, run.stderr || run.stdout || 'dsh-crate export failed'), result }
      await record(workspace.history, { time: new Date().toISOString(), action, status: 'FAIL', profile: profileName, message: String(failure.error.message ?? 'dsh-crate export failed'), code: failure.error.code, stage: failure.error.stage })
      return failure
    }
    const item = await record(workspace.history, { time: new Date().toISOString(), action, status: 'PASS', profile: profileName, pack: outputName })
    return { status: 'ok', command: action, exitCode: run.code, result, downloadName: outputName, history: item }
  }

  if (action === 'import') {
    const pack = await savePack(workspace.work, 'import', body.packBase64)
    const args = ['import', pack, '--dsh-home', home, '--json', ...runtimeCoreArgs()]
    if (typeof body.targetProfile === 'string') args.push('--target-profile', safeName(body.targetProfile, 'targetProfile'))
    if (body.overwrite === true) args.push('--overwrite')
    if (body.confirmOverwrite === true) args.push('--confirm-overwrite')
    const run = await runCore(home, args)
    let result: unknown
    try { result = parseCore(run.stdout) } catch { result = undefined }
    if (run.code !== 0 || result === undefined) {
      const message = run.stderr || run.stdout || 'dsh-crate import failed'
      const failure = { status: 'failed', action, exitCode: run.code, error: coreDiagnostic(result, message), result }
      await record(workspace.history, { time: new Date().toISOString(), action, status: 'FAIL', message: String(failure.error.message ?? message), code: failure.error.code, stage: failure.error.stage })
      return failure
    }
    await ensureCrateBundleInAllProfiles(home)
    const prepared = result as JsonObject
    const plan = prepared.plan
    const profileName = plan !== null && typeof plan === 'object' && !Array.isArray(plan) && typeof (plan as JsonObject).profileName === 'string'
      ? (plan as JsonObject).profileName as string
      : undefined
    const item = await record(workspace.history, { time: new Date().toISOString(), action, status: 'PASS', ...(profileName ? { profile: profileName } : {}) })
    let profileRow: JsonObject | undefined
    if (profileName !== undefined) {
      try {
        profileRow = (await listProfiles(home)).find(candidate => candidate.name === profileName)
      } catch {
        // The import already succeeded; the client retries Profile freshness.
      }
    }
    return {
      status: 'ok',
      command: action,
      exitCode: run.code,
      result,
      ...(profileRow !== undefined ? { profile: profileRow } : {}),
      history: item,
    }
  }

  if (action === 'delete-profile') {
    const profileName = safeName(body.profileName, 'profileName')
    const running = currentRuntime(home)
    if (running.currentProfile === profileName) {
      const error = operationDiagnostic('ACTIVE_PROFILE', 'planning', profileName, `cannot delete the active Profile: ${profileName}`, 'The running DSH process would lose its Profile files.', 'Switch to another Profile first, then delete this Profile.')
      return { status: 'failed', command: action, exitCode: 2, error }
    }
    const args = ['delete-profile', '--dsh-home', home, '--profile', profileName, '--json']
    if (body.confirmDelete === true) args.push('--confirm-delete')
    const run = await runCore(home, args)
    let result: unknown
    try { result = parseCore(run.stdout) } catch { result = undefined }
    if (run.code !== 0 || result === undefined) {
      const message = run.stderr || run.stdout || 'dsh-crate Profile deletion failed'
      const failure = { status: 'failed', action, exitCode: run.code, error: coreDiagnostic(result, message), result }
      await record(workspace.history, { time: new Date().toISOString(), action, status: 'FAIL', profile: profileName, message: String(failure.error.message ?? message), code: failure.error.code, stage: failure.error.stage })
      return failure
    }
    const item = await record(workspace.history, { time: new Date().toISOString(), action, status: 'PASS', profile: profileName })
    return { status: 'ok', command: action, exitCode: run.code, result, history: item }
  }

  if (action === 'switch-status') {
    const operationId = typeof body.operationId === 'string' && SAFE_OPERATION_ID.test(body.operationId)
      ? body.operationId
      : (() => { throw new Error('operationId is invalid') })()
    const reportPath = join(workspace.work, `switch-${operationId}.json`)
    try {
      const value: unknown = JSON.parse(await readFile(reportPath, 'utf8'))
      return { status: 'ok', command: action, operationId, result: isObject(value) ? value : { status: 'failed', message: 'switch report is malformed' } }
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === 'ENOENT') return { status: 'ok', command: action, operationId, result: { status: 'pending', operationId, message: 'Switch operation has not produced a report yet.' } }
      throw error
    }
  }

  if (action === 'switch-profile') {
    const profileName = safeName(body.profileName, 'profileName')
    if (body.confirmSwitch !== true) {
      return { status: 'failed', command: action, exitCode: 2, error: operationDiagnostic('SWITCH_CONFIRMATION_REQUIRED', 'planning', profileName, 'switching Profile requires explicit confirmation', 'The current DSH process was not changed.', 'Confirm the switch and retry.') }
    }
    const available = await listProfiles(home)
    if (!available.some(profile => profile.name === profileName)) {
      return { status: 'failed', command: action, exitCode: 2, error: operationDiagnostic('PROFILE_MISSING', 'planning', profileName, `Profile does not exist: ${profileName}`, 'The current DSH process was not changed.', 'Choose an existing Profile and retry.') }
    }
    const runtime = currentRuntime(home)
    const oldProfile = typeof runtime.currentProfile === 'string' ? runtime.currentProfile : undefined
    if (oldProfile === profileName) {
      // Switching to the Profile that is already running is a no-op, not an
      // error: the requested end state already holds, so no restart is needed.
      const item = await record(workspace.history, { time: new Date().toISOString(), action, status: 'PASS', profile: profileName, message: 'Profile is already active; no restart was needed' })
      return {
        status: 'ok',
        command: action,
        exitCode: 0,
        result: { status: 'already-active', profileName, message: `Profile is already active: ${profileName}`, impact: 'The current DSH process was not changed; the requested Profile is already running.', canContinue: true },
        history: item,
      }
    }
    if (runtime.restartConfigured !== true || typeof process.argv[1] !== 'string' || typeof runtime.port !== 'number') {
      return { status: 'failed', command: action, exitCode: 2, error: operationDiagnostic('RESTART_NOT_CONFIGURED', 'planning', profileName, 'the current DSH launch command cannot be safely reconstructed', 'The current DSH process was not changed.', 'Start DSH with an explicit --profile and --port, or configure the DSH Crate restart launcher.') }
    }
    const operationId = randomUUID()
    const reportPath = join(workspace.work, `switch-${operationId}.json`)
    const args = replaceArgument(replaceArgument(process.argv.slice(2), '--profile', profileName), '--port', String(runtime.port))
    const helperPath = join(dirname(fileURLToPath(import.meta.url)), 'restart-helper.mjs')
    try { await access(helperPath) } catch { throw new Error(`restart helper is missing: ${helperPath}`) }
    const spec = {
      operationId, reportPath, oldPid: process.pid, oldProfile, targetProfile: profileName,
      nodePath: process.execPath, scriptPath: resolve(process.argv[1]), args, cwd: process.cwd(),
      env: { ...process.env, DSH_HOME: home, DSH_PACK_ACTIVE_PROFILE: profileName, DSH_PACK_PORT: String(runtime.port) },
      url: `http://127.0.0.1:${runtime.port}/`,
    }
    await writeFile(reportPath, `${JSON.stringify({ status: 'pending', operationId, stage: 'scheduled', oldProfile, targetProfile: profileName, message: 'Switch scheduled.' }, null, 2)}\n`, { encoding: 'utf8', flag: 'wx' })
    const encoded = Buffer.from(JSON.stringify(spec), 'utf8').toString('base64url')
    const helper = spawn(process.execPath, [helperPath, encoded], { detached: true, windowsHide: true, stdio: 'ignore' })
    helper.unref()
    const item = await record(workspace.history, { time: new Date().toISOString(), action, status: 'PASS', profile: profileName, oldProfile, operationId, message: 'Switch scheduled; waiting for the target Profile to become ready.' })
    setTimeout(() => process.exit(0), 650)
    return { status: 'ok', command: action, operationId, history: item, result: { status: 'pending', operationId, oldProfile, targetProfile: profileName, message: 'Switch scheduled; waiting for the target Profile to become ready.' } }
  }

  if (action === 'verify') {
    const profileName = safeName(body.profileName, 'profileName')
    const mode = body.mode === undefined ? 'web' : body.mode
    if (mode !== 'web' && mode !== 'headless') throw new Error('mode must be web or headless')
    const args = ['verify', '--dsh-home', home, '--profile', profileName, '--mode', mode, '--json', ...runtimeCoreArgs()]
    let runnerConfigPath: string | undefined
    if (body.runnerConfig !== undefined) {
      if (!isObject(body.runnerConfig)) throw new Error('runnerConfig must be a JSON object')
      const verifyDir = join(workspace.work, 'verify')
      await mkdir(verifyDir, { recursive: true })
      runnerConfigPath = join(verifyDir, 'verify-' + randomUUID() + '.json')
      await writeFile(runnerConfigPath, JSON.stringify(body.runnerConfig, null, 2) + '\n', { encoding: 'utf8', flag: 'wx' })
      args.push('--runner-config', runnerConfigPath)
    }
    const run = await runCore(home, args)
    let result: unknown
    try { result = parseCore(run.stdout) } catch { result = undefined }
    if (result === undefined) {
      return { status: 'failed', action, exitCode: run.code, error: coreDiagnostic(undefined, run.stderr || run.stdout || 'dsh-crate verify failed') }
    }
    const resultObject = isObject(result) ? result : {}
    const status = typeof resultObject.status === 'string' ? resultObject.status : 'FAIL'
    const success = status === 'PASS'
    const item = await record(workspace.history, { time: new Date().toISOString(), action, status, profile: profileName })
    return { status: 'ok', command: action, exitCode: run.code, result, history: item, success }
  }

  throw new Error(`unsupported DSH Crate action: ${String(action)}`)
}

async function handleDownload(home: string, req: IncomingMessage, res: ServerResponse): Promise<void> {
  if (req.method !== 'GET' && req.method !== 'HEAD') {
    res.writeHead(405)
    res.end()
    return
  }
  const name = new URL(req.url ?? DOWNLOAD_PATH, 'http://dsh.local').searchParams.get('name')
  const safe = safeName(name, 'download name')
  const root = resolve(join(home, '.dsh-pack', 'exports'))
  const path = resolve(join(root, safe))
  if (dirname(path) !== root) throw new Error('download path escaped export directory')
  const info = await stat(path)
  res.writeHead(200, {
    'content-type': 'application/octet-stream',
    'content-length': info.size,
    'content-disposition': `attachment; filename="${safe}"`,
  })
  if (req.method === 'HEAD') { res.end(); return }
  createReadStream(path).pipe(res)
}

/** Register the host bridge. The Core executable is intentionally external. */
export const inject = ['webServer']

export function apply(ctx: Context): void {
  const home = resolve(process.env.DSH_HOME || process.cwd())
  void ensureCrateBundleInAllProfiles(home).catch(error => console.error(`dsh-crate-web: failed to ensure Profile invariant: ${failMessage(error)}`))
  ctx.effect(() => {
    const disposeApi = ctx.webServer.register({
      kind: 'exact',
      path: API_PATH,
      handler: async (req, res) => {
        if (req.method !== 'POST') { res.writeHead(405); res.end(); return }
        try {
          const result = await handleApi(home, await readRequest(req), listRuntimePlugins(ctx))
          json(res, 200, result)
        } catch (error) {
          json(res, 400, { status: 'failed', error: { message: failMessage(error) } })
        }
      },
    })
    const disposeDownload = ctx.webServer.register({
      kind: 'exact',
      path: DOWNLOAD_PATH,
      handler: (req, res) => { void handleDownload(home, req, res).catch(error => json(res, 404, { status: 'failed', error: { message: failMessage(error) } })) },
    })
    return () => { disposeApi(); disposeDownload() }
  }, 'dsh-crate-web: local Core bridge')
}
