/** Read Loader metadata only; a partial enumeration never proves absence. */
const phases = { 0: 'pending', 1: 'loading', 2: 'active', 3: 'failed', 4: null, 5: 'unloading' }
export function readRuntimeInventory(ctx) {
  const rows = []
  const loader = ctx?.loader
  if (!loader || typeof loader.entries !== 'function') return { rows, complete: false }
  try {
    for (const entry of loader.entries()) {
      if (entry.options.group) continue
      if (typeof entry.options.name !== 'string' || typeof entry.id !== 'string') throw new Error('invalid Loader row')
      if (entry.options.name.startsWith('cordis:')) continue
      rows.push({ id: entry.id, name: entry.options.name, enabled: entry.disabled !== true,
        phase: entry.fiber ? (phases[entry.fiber.state] ?? null) : null })
    }
    return { rows, complete: true }
  } catch {
    return { rows, complete: false }
  }
}

export function inspectorApplicability(rows, complete) {
  if (complete !== true || !Array.isArray(rows) || !rows.length || rows.some(row => !row ||
      typeof row.id !== 'string' || typeof row.name !== 'string' || typeof row.enabled !== 'boolean')) {
    throw new Error('Inspector applicability not confirmed: runtime inventory missing or incomplete')
  }
  const matches = rows.filter(row => row.name === '@deepseek-ai/dsh-experimental-inspector')
  const applicable = matches.some(row => row.enabled)
  return { inventoryComplete: true, inventoryCount: rows.length, applicable,
    reason: applicable ? 'enabled' : matches.length ? 'disabled' : 'not-declared',
    plugins: matches.map(({ id, name, enabled, phase }) => ({ id, name, enabled, phase })) }
}
