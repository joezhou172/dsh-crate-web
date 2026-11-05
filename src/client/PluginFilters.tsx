import type { DshCrateLocaleKey } from './locales.ts'
export interface PluginFilter { search: string; selection: string; source: string }
export const emptyPluginFilter: PluginFilter = { search: '', selection: 'all', source: 'all' }
export function hasPluginFilter(value: PluginFilter) { return Boolean(value.search.trim() || value.selection !== 'all' || value.source !== 'all') }
export function matchesPluginFilter(value: PluginFilter, name: string, official: boolean, included?: boolean) {
  return name.toLowerCase().includes(value.search.trim().toLowerCase())
    && (value.source === 'all' || (value.source === 'official' ? official : !official))
    && (value.selection === 'all' || (value.selection === 'selected' ? included === true : included === false))
}
export function PluginFilters({ value, onChange, count, total, t }: { value: PluginFilter; onChange: (value: PluginFilter) => void; count: number; total: number; t: (key: DshCrateLocaleKey) => string }) {
  return <div className="dsh-crate-filters">
    <input type="search" className="dsh-crate-file" aria-label={t('filterPlugins')} placeholder={t('filterPlugins')} value={value.search} onChange={e => onChange({ ...value, search: e.target.value })} />
    <div className="dsh-crate-filter-options">
      <select className="dsh-crate-select" aria-label={t('filterSelection')} value={value.selection} onChange={e => onChange({ ...value, selection: e.target.value })}>
        <option value="all">{t('filterAllSelections')}</option><option value="selected">{t('filterSelected')}</option><option value="unselected">{t('filterUnselected')}</option>
      </select>
      <select className="dsh-crate-select" aria-label={t('filterSource')} value={value.source} onChange={e => onChange({ ...value, source: e.target.value })}>
        <option value="all">{t('filterAllSources')}</option><option value="official">{t('officialPlugins')}</option><option value="community">{t('userPlugins')}</option>
      </select>
      {hasPluginFilter(value) ? <button className="dsh-crate-secondary dsh-crate-text-button" type="button" onClick={() => onChange({ ...emptyPluginFilter })}>{t('clearFilters')}</button> : null}
    </div>
    <span className="dsh-crate-muted" role="status">{t('filterResults').replace('{count}', String(count)).replace('{total}', String(total))}</span>
    {count === 0 ? <p className="dsh-crate-muted">{t('noMatchingPlugins')}</p> : null}
  </div>
}
