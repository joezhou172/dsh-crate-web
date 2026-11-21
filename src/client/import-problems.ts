type Row = Record<string, any>
const rows = (v: unknown): Row[] => Array.isArray(v) ? v.filter(x => x && typeof x === 'object') : []
const attributable = new Set(['PLUGIN_OS_UNSUPPORTED', 'PLUGIN_DEPENDENCY_UNAVAILABLE', 'PLUGIN_VERSION_MISMATCH',
  'PACKAGE_MANIFEST_INVALID', 'BUNDLE_PATCH_MISSING', 'BUNDLE_PATCH_INVALID', 'BUNDLE_PATCH_MISMATCH'])
/** 不把网络、权限、空间、哈希或无归属的安装失败解释成插件不兼容。 */
export function importProblems(value?: Row): { name: string; reason: string }[] {
  const result = value?.result ?? value ?? {}, error = result.error ?? value?.error ?? {}
  const candidates = [...rows(result.skippedPlugins), ...rows(result.compatibilityReport?.skippedPlugins),
    ...rows(result.findings), ...rows(error.details?.findings), error]
  const found = new Map<string, { name: string; reason: string }>()
  for (const item of candidates) {
    const reason = item.reason ?? item.code
    const name = item.name ?? item.plugin ?? item.evidence?.plugin ?? item.details?.plugin
    if (attributable.has(reason) && typeof name === 'string' && !name.startsWith('@deepseek-ai/') &&
      /^(?:@[a-z0-9][a-z0-9._-]*\/)?[a-z0-9][a-z0-9._-]*$/.test(name)) found.set(name, { name, reason })
  }
  return [...found.values()]
}
