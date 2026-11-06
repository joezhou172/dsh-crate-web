import { PluginFilters, emptyPluginFilter, hasPluginFilter, matchesPluginFilter } from './PluginFilters.tsx'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import type { DshCrateLocaleKey } from './locales.ts'
type T = (key: DshCrateLocaleKey) => string
export interface ExportChoice {
  name: string; included: boolean; selection: { kind: 'installed' } | { kind: 'registry'; version: string }
  artifactMode: string; activateOnImport: boolean
}
export interface CatalogPlugin { name: string; version: string; active: boolean; official: boolean }
type Json = Record<string, unknown>

export function ExportSelection({ rows, catalog, onChange, query, onError, disabled, t }: {
  rows: ExportChoice[]; catalog: CatalogPlugin[]; onChange: (rows: ExportChoice[]) => void
  query: (name: string) => Promise<Json>; onError: (value: unknown) => void; disabled: boolean; t: T
}) {
  const [name, setName] = useState('')
  const [target, setTarget] = useState<string>()
  const [versions, setVersions] = useState<string[]>([])
  const [filter, setFilter] = useState('')
  const [version, setVersion] = useState('')
  const [loading, setLoading] = useState(false)
  const [filters, setFilters] = useState({ ...emptyPluginFilter })
  const generation = useRef(0)
  useEffect(() => () => { generation.current += 1 }, [])
  const edit = (item: ExportChoice, patch: Partial<ExportChoice>) => onChange(rows.map(row => row.name === item.name ? { ...row, ...patch } : row))
  const load = async (packageName: string) => {
    if (!packageName.trim() || loading) return
    const id = ++generation.current
    setLoading(true)
    try {
      const value = await query(packageName.trim())
      if (id !== generation.current) return
      if (value.status === 'failed') { onError(value); return }
      const result = value.result as Json
      if (!result || !Array.isArray(result.versions)) throw new Error(t('catalogUnavailable'))
      setVersions(result.versions.filter((v): v is string => typeof v === 'string').reverse())
      setTarget(packageName.trim()); setVersion(''); setFilter('')
    } catch (error) { if (id === generation.current) onError({ status: 'failed', message: String(error) }) }
    finally { if (id === generation.current) setLoading(false) }
  }
  const addVersion = () => {
    if (!target || !version) return
    const existing = rows.find(row => row.name === target)
    if (existing) edit(existing, { included: true, selection: { kind: 'registry', version } })
    else onChange([...rows, { name: target, included: true, selection: { kind: 'registry', version }, artifactMode: 'embedded', activateOnImport: false }])
    setTarget(undefined); setName('')
  }
  const rowView = (item: ExportChoice) => {
    const installed = catalog.find(p => p.name === item.name)
    const host = installed?.official === true
    return <div className="dsh-crate-choice" key={item.name}>
      <label className="dsh-crate-choice-name"><input type="checkbox" aria-label={item.name} checked={item.included} disabled={disabled || host} onChange={e => edit(item, { included: e.target.checked })} /> <span className="dsh-crate-plugin-copy"><strong>{item.name}</strong><span className="dsh-crate-muted">{item.selection.kind === 'installed' ? t('installedContent') + ' · ' + installed?.version : item.selection.version + ' · ' + t('statusUntested')}</span></span></label>
      <div className="dsh-crate-choice-controls">
        {!host ? <button className="dsh-crate-secondary dsh-crate-text-button" disabled={disabled || loading} type="button" onClick={() => void load(item.name)}>{t('chooseVersion')}</button> : null}

        <select className="dsh-crate-select" aria-label={item.name + ' ' + t('artifactMode')} disabled={disabled || !item.included} value={item.artifactMode} onChange={e => edit(item, { artifactMode: e.target.value })}>
          <option value="embedded">{t('embedded')}</option><option value="reference-only">{t('referenceOnly')}</option>
        </select>
        {!installed ? <label><input type="checkbox" disabled={disabled || !item.included} checked={item.activateOnImport} onChange={e => edit(item, { activateOnImport: e.target.checked })} /> {t('activateOnImport')}</label> : null}
      </div>
    </div>
  }
  const visible = rows.filter(r => matchesPluginFilter(filters, r.name, catalog.some(p => p.name === r.name && p.official), r.included))
  return <section className="dsh-crate-inventory dsh-crate-selection" aria-label={t('exportSelection')}>
    <strong>{rows.filter(r => r.included).length}/{rows.length} · {t('selectedForExport')}</strong>
    <p className="dsh-crate-muted">{t('exportOnlyHint')}</p>
    <PluginFilters value={filters} onChange={setFilters} count={visible.length} total={rows.length} t={t} />
    <div className="dsh-crate-choice-controls"><input className="dsh-crate-file" aria-label={t('packageName')} placeholder={t('packageName')} value={name} disabled={disabled || loading} onChange={e => setName(e.target.value)} />
      <button className="dsh-crate-secondary" type="button" disabled={disabled || loading || !name.trim()} onClick={() => void load(name)}>{loading ? t('working') : t('addToExport')}</button></div>
    {visible.filter(r => !catalog.find(p => p.name === r.name)?.official).map(rowView)}
    {visible.some(r => catalog.find(p => p.name === r.name)?.official) ? <details key={JSON.stringify(filters)} open={hasPluginFilter(filters) || undefined}><summary>{t('officialPlugins')} · {visible.filter(r => catalog.find(p => p.name === r.name)?.official).length}</summary>
      {visible.filter(r => catalog.find(p => p.name === r.name)?.official).map(rowView)}
    </details> : null}
    {target ? <VersionDialog title={t('chooseVersion')} onClose={() => setTarget(undefined)}>
      {catalog.some(item => item.name === target) ? <button className="dsh-crate-secondary" type="button" disabled={disabled} onClick={() => { const item = rows.find(row => row.name === target); if (item) edit(item, { selection: { kind: 'installed' } }); setTarget(undefined) }}>{t('installedContent')}</button> : null}
      <strong>{target}</strong><span className="dsh-crate-muted">{t('versionUntested')}</span>
      <input className="dsh-crate-file" aria-label={t('filterVersions')} placeholder={t('filterVersions')} value={filter} onChange={e => setFilter(e.target.value)} />
      <select className="dsh-crate-select" aria-label={t('publishedVersion')} value={version} onChange={e => setVersion(e.target.value)}>
        <option value="">{t('chooseVersion')}</option>{versions.filter(v => v.includes(filter)).map(v => <option key={v} value={v}>{v}{v.includes('-') ? ' · ' + t('prerelease') : ''}</option>)}
      </select>
      <div className="dsh-crate-choice-controls"><button className="dsh-crate-secondary" type="button" onClick={() => setTarget(undefined)}>{t('cancel')}</button>
      <button className="dsh-crate-button" type="button" disabled={!version || disabled} onClick={addVersion}>{t('addToExport')}</button></div>
    </VersionDialog> : null}
  </section>
}

export function ReferenceConfirmation({ rows, evidence, t, onCancel, onConfirm }: { rows: ExportChoice[]; evidence: Json[]; t: T; onCancel: () => void; onConfirm: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const previous = document.activeElement
    dialog.current?.showModal()
    const escape = (event: KeyboardEvent) => { if (event.key === 'Escape') { event.preventDefault(); event.stopImmediatePropagation(); onCancel() } }
    document.addEventListener('keydown', escape, true)
    return () => { document.removeEventListener('keydown', escape, true); if (previous instanceof HTMLElement) previous.focus() }
  }, [])
  return <dialog ref={dialog} className="dsh-crate-report-dialog" aria-labelledby="crate-reference-title" onCancel={e => { e.preventDefault(); onCancel() }}>
    <h3 id="crate-reference-title">{t('referenceConfirmTitle')}</h3><p>{t('referenceConfirmBody').replace('{count}', String(rows.length))}</p>
    <details><summary>{t('referenceList')}</summary>{rows.map(row => { const item = evidence.find(item => item.name === row.name); return <p key={row.name}>{row.name} · {String(item?.version ?? (row.selection.kind === 'registry' ? row.selection.version : t('installedContent')))} · {String(item?.sourceType ?? t('recordedSource'))}</p> })}</details>
    <div className="dsh-crate-dialog-actions"><button autoFocus className="dsh-crate-secondary" onClick={onCancel}>{t('backToEdit')}</button><button className="dsh-crate-button" onClick={onConfirm}>{t('confirmExport')}</button></div>
  </dialog>
}

function VersionDialog({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  const dialog = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const previous = document.activeElement
    dialog.current?.showModal()
    const escape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { event.preventDefault(); event.stopImmediatePropagation(); onClose() }
    }
    document.addEventListener('keydown', escape, true)
    return () => { document.removeEventListener('keydown', escape, true); if (previous instanceof HTMLElement) previous.focus({ preventScroll: true }) }
  }, [])
  return <dialog ref={dialog} className="dsh-crate-report-dialog" aria-label={title} onCancel={e => { e.preventDefault(); onClose() }}><h3>{title}</h3>{children}</dialog>
}
