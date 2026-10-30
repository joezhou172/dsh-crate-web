/** Read-only adapter: use the installed official parser/composer, never activate entries. */
import { createHash } from 'node:crypto'
import { existsSync, readFileSync, realpathSync } from 'node:fs'
import { createRequire } from 'node:module'
import { dirname, join, resolve } from 'node:path'
import { pathToFileURL } from 'node:url'
import { isDeepStrictEqual } from 'node:util'

const hash = value => createHash('sha256').update(value).digest('hex')
const runtime = resolve(process.argv[2])
const profile = resolve(process.argv[3])
const anchor = join(runtime, 'package.json')
const require = createRequire(anchor)
const { parseDocument, isMap, isScalar, isSeq } = require('yaml')
const boot = await import(pathToFileURL(join(runtime, 'node_modules/@deepseek-ai/dsh-app-boot/lib/index.js')).href)

function rowsById(rows, result = new Map(), depth = 0) {
  if (depth > 64) throw new Error('patch nesting exceeds adapter limit')
  for (const row of rows ?? []) {
    if (!row || typeof row !== 'object') continue
    if (typeof row.id === 'string') result.set(row.id, [...(result.get(row.id) ?? []), row])
    if (Array.isArray(row.config)) rowsById(row.config, result, depth + 1)
    if (Array.isArray(row.insert)) rowsById(row.insert, result, depth + 1)
  }
  return result
}

function hasFilesystemInsert(rows, depth = 0) {
  if (depth > 64) throw new Error('patch nesting exceeds adapter limit')
  return (rows ?? []).some(row => row && typeof row === 'object' &&
    (typeof row.name === 'string' && row.name.startsWith('file:') ||
     row.group && Array.isArray(row.config) && hasFilesystemInsert(row.config, depth + 1)))
}

function main() {
  const path = join(profile, 'cordis.patch.yml')
  if (!existsSync(path)) return { changed: false, reason: 'no-profile-patch' }
  const original = readFileSync(path)
  const source = boot.loadOptionalPatches('dsh-crate', path) ?? []
  // A custom root is deliberately left to its owner; this adapter targets the
  // normal empty-root + ordered Bundle + id-targeted override contract only.
  if ((boot.loadOptionalPatches('dsh-crate', join(profile, 'cordis.yml')) ?? []).length) {
    return { changed: false, reason: 'custom-root-entries' }
  }
  const manifest = boot.readProfileManifest('dsh-crate', profile)
  // Retired official Bundles are not in the runtime's current catalog. Avoid
  // loadProfileDirectory here: it can rewrite a manifest to remove them.
  const catalog = new Set([...boot.DEFAULT_PROFILE_BUNDLES, ...boot.OPTIONAL_BUNDLES,
    ...Object.values(boot.PROFILE_TEMPLATES).flatMap(template => template.bundles)])
  const exemptions = boot.readProfileVersionExemptions(profile)
  const layers = []
  for (const name of manifest.dsh?.profile?.bundles ?? []) {
    if (name.startsWith('@deepseek-ai/') && !catalog.has(name)) return { changed: false, reason: 'uncatalogued-official-bundle' }
    const root = boot.resolveBundleDir('dsh-crate', name, anchor, profile)
    const bundleManifest = boot.readProfileManifest('dsh-crate', root)
    const issue = boot.evaluatePluginCompatibility(bundleManifest, exemptions)
    if (issue && !issue.exempted) return { changed: false, reason: 'incompatible-bundle' }
    const bundle = bundleManifest.dsh?.bundle
    if (!bundle) throw new Error('declared Bundle has no patch')
    layers.push(...boot.bundlePatchPaths(root, bundle).map(file => boot.loadOverlayPatches('dsh-crate', file)))
  }
  const baseWarnings = []
  const base = boot.composeEntries(layers, message => baseWarnings.push(message))
  if (baseWarnings.length) return { changed: false, reason: 'ambiguous-bundle-composition' }
  const declarations = new Map()
  for (const patches of layers) {
    for (const patch of patches) {
      for (const [id, rows] of rowsById(patch.insert ?? [])) {
        declarations.set(id, (declarations.get(id) ?? 0) + rows.length)
      }
    }
  }
  const slots = rowsById(base)
  const occurrences = rowsById(source)
  // The official parser anchors filesystem insert names beside the original
  // file. Preserve these profiles unchanged rather than compare two dialects.
  if (source.some(patch => hasFilesystemInsert(patch.insert))) {
    return { changed: false, reason: 'filesystem-insert-requires-official-parser' }
  }
  const homePatch = boot.loadOptionalPatches('dsh-crate', join(dirname(dirname(profile)), 'cordis.patch.yml')) ?? []
  const homeSlots = rowsById(homePatch)
  const document = parseDocument(original.toString('utf8'), {
    customTags: [{ tag: 'tag:yaml.org,2002:js', resolve: value => value }],
    uniqueKeys: true,
  })
  if (document.errors.length || !isSeq(document.contents)) throw new Error('profile patch cannot be safely represented')
  const changes = []
  for (const item of document.contents.items) {
    if (!isMap(item)) continue
    const idNode = item.get('id', true), nameNode = item.get('name', true)
    if (!isScalar(idNode) || !isScalar(nameNode)) continue
    const id = idNode.value, name = nameNode.value
    if (typeof id !== 'string' || typeof name !== 'string' || !/^@deepseek-ai\/[A-Za-z0-9._-]+$/.test(name)) continue
    const slot = slots.get(id)
    if (slot?.length !== 1 || slot[0].name !== name || declarations.get(id) !== 1 || occurrences.get(id)?.length !== 1 || homeSlots.has(id)) continue
    // Preserve explicit package overrides and any hoisted dependency that can
    // select a different implementation than the installation anchor.
    if (name in (manifest.dependencies ?? {}) || name in (manifest.optionalDependencies ?? {})) continue
    if (existsSync(join(profile, 'node_modules', name, 'package.json')) ||
        existsSync(join(dirname(profile), 'node_modules', name, 'package.json'))) continue
    let official
    try { official = require.resolve(name + '/package.json') } catch { continue }
    if (!realpathSync(official).replaceAll('\\', '/').startsWith(realpathSync(join(runtime, 'node_modules')).replaceAll('\\', '/') + '/')) continue
    try {
      const local = createRequire(join(profile, 'package.json')).resolve(name + '/package.json')
      if (realpathSync(local) !== realpathSync(official)) continue
    } catch (error) { if (error?.code !== 'MODULE_NOT_FOUND') continue }
    item.delete('name')
    changes.push({ id, name })
  }
  if (!changes.length) return { changed: false, reason: 'no-equivalent-official-overrides' }
  const content = document.toString()
  // Official loadOptionalPatches treats !!js as inert expression nodes. It
  // does not evaluate them, and this helper never calls Loader/boot/apply.
  const yaml = require('js-yaml')
  const expression = new yaml.Type('tag:yaml.org,2002:js', {
    kind: 'scalar', resolve: value => typeof value === 'string',
    construct: value => ({ __jsExpr: value }),
  })
  const next = yaml.load(content, { schema: yaml.JSON_SCHEMA.extend(expression) })
  const beforeWarnings = [], afterWarnings = []
  const before = boot.composeEntries([...layers, source, homePatch], message => beforeWarnings.push(message))
  const after = boot.composeEntries([...layers, next, homePatch], message => afterWarnings.push(message))
  if (!isDeepStrictEqual(before, after) || !isDeepStrictEqual(beforeWarnings, afterWarnings)) {
    throw new Error('the official Loader composition changed; refusing adaptation')
  }
  return { changed: true, originalSha256: hash(original), runtimeSha256: hash(content),
    loaderTreeSha256: hash(JSON.stringify(before)), removedNames: changes,
    contentBase64: Buffer.from(content).toString('base64') }
}

try { process.stdout.write(JSON.stringify(main()) + '\n') }
catch (error) {
  // Core redacts the full process diagnostic before exposing it. Do not echo
  // parser snippets, which may contain values from the configuration file.
  const detail = error instanceof Error ? { name: error.name,
    message: error.message.split(/\n|\r/)[0], code: error.code ?? null } : { name: 'Error', message: String(error).split(/\n|\r/)[0] }
  process.stdout.write(JSON.stringify({ error: 'official patch equivalence could not be verified', detail }) + '\n')
  process.exitCode = 1
}
