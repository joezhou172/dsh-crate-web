import { useEffect, useMemo, useRef, useState } from 'react'
import { Toast } from '@deepseek-ai/dsh-client-ui-primitives'
import type { PropsLocale, PropsRuntime } from '@deepseek-ai/dsh-client-ui-slots'
import type { DshCrateLocaleKey } from './locales.ts'
import type { ReactNode } from 'react'

export const css = {
  section: 'dsh-crate-section', heading: 'dsh-crate-heading', intro: 'dsh-crate-intro', muted: 'dsh-crate-muted',
  tabs: 'dsh-crate-tabs', tab: 'dsh-crate-tab', form: 'dsh-crate-form', label: 'dsh-crate-label',
  select: 'dsh-crate-select', file: 'dsh-crate-file', plugin: 'dsh-crate-plugin', button: 'dsh-crate-button',
  report: 'dsh-crate-report', finding: 'dsh-crate-finding', history: 'dsh-crate-history', historyItem: 'dsh-crate-history-item',
  error: 'dsh-crate-error', preview: 'dsh-crate-preview', previewRow: 'dsh-crate-preview-row', diagnostic: 'dsh-crate-diagnostic',
  diagnosticGrid: 'dsh-crate-diagnostic-grid', step: 'dsh-crate-step', stepStatus: 'dsh-crate-step-status',
  inventory: 'dsh-crate-inventory', inventoryItem: 'dsh-crate-inventory-item', success: 'dsh-crate-success',
  modalBackdrop: 'dsh-crate-modal-backdrop', modal: 'dsh-crate-modal', modalActions: 'dsh-crate-modal-actions',
  group: 'dsh-crate-group', groupHead: 'dsh-crate-group-head', groupToggle: 'dsh-crate-group-toggle', groupBody: 'dsh-crate-group-body',
  badge: 'dsh-crate-badge', conflict: 'dsh-crate-conflict', toneOk: 'dsh-crate-tone-ok', toneBad: 'dsh-crate-tone-bad', toneNeutral: 'dsh-crate-tone-neutral',
}

export const STYLE = `
.dsh-crate-section{display:flex;flex-direction:column;gap:12px;max-width:760px;color:var(--dsw-alias-label-primary)}
.dsh-crate-heading{margin:0;font-size:18px;font-weight:600}.dsh-crate-intro,.dsh-crate-muted{margin:0;font-size:13px;color:var(--dsw-alias-label-tertiary)}
.dsh-crate-tabs{display:flex;gap:20px;border-bottom:1px solid var(--dsw-alias-border-l2);overflow:auto}.dsh-crate-tab{border:0;padding:7px 1px 9px;background:transparent;color:var(--dsw-alias-label-tertiary);font:inherit;cursor:pointer;white-space:nowrap}
.dsh-crate-tab[data-active=true]{color:var(--dsw-alias-label-primary);border-bottom:2px solid var(--dsw-alias-label-primary)}.dsh-crate-form{display:flex;flex-direction:column;gap:10px}
.dsh-crate-label{display:flex;flex-direction:column;gap:5px;font-size:13px}.dsh-crate-select,.dsh-crate-file{max-width:100%;padding:7px 8px;border:1px solid var(--dsw-alias-border-l2,#3a3a40);border-radius:6px;background-color:var(--dsw-alias-fill-secondary,rgba(255,255,255,.08));color:var(--dsw-alias-label-primary,#f9fafb);color-scheme:dark}.dsh-crate-select option{background-color:#242428;color:#f9fafb}@media (prefers-color-scheme:light){.dsh-crate-select,.dsh-crate-file{background-color:var(--dsw-alias-fill-secondary,#fff);color:var(--dsw-alias-label-primary,#111827);color-scheme:light}.dsh-crate-select option{background-color:#fff;color:#111827}}
.dsh-crate-plugin{display:grid;grid-template-columns:minmax(0,1fr) 150px;gap:8px;align-items:center}.dsh-crate-button{align-self:flex-start;border:0;border-radius:6px;padding:8px 13px;background:var(--dsw-alias-state-business-primary);color:white;cursor:pointer}.dsh-crate-button:disabled{cursor:default;opacity:.5}
.dsh-crate-report,.dsh-crate-preview,.dsh-crate-diagnostic{display:flex;flex-direction:column;gap:8px;padding:10px;border:1px solid var(--dsw-alias-border-l2);border-radius:8px;overflow-wrap:anywhere;font-size:12px}.dsh-crate-finding,.dsh-crate-step{padding:7px;border-radius:5px;background:var(--dsw-alias-fill-tertiary)}
.dsh-crate-preview-row{display:grid;grid-template-columns:170px minmax(0,1fr);gap:8px}.dsh-crate-preview-row pre{margin:0;white-space:pre-wrap}.dsh-crate-diagnostic-grid{display:grid;grid-template-columns:150px minmax(0,1fr);gap:6px}.dsh-crate-diagnostic-grid dt{font-weight:600}.dsh-crate-diagnostic-grid dd{margin:0;white-space:pre-wrap}.dsh-crate-step{display:flex;gap:8px;align-items:flex-start}.dsh-crate-step-status{min-width:80px;font-weight:600}
.dsh-crate-history{list-style:none;display:flex;flex-direction:column;gap:8px;padding:0;margin:0}.dsh-crate-history-item{display:flex;justify-content:space-between;gap:10px;padding:8px;border-bottom:1px solid var(--dsw-alias-border-l2);font-size:12px}.dsh-crate-error{color:var(--dsw-alias-label-negative)}
.dsh-crate-inventory{display:flex;flex-direction:column;gap:6px;padding:8px;border:1px solid var(--dsw-alias-border-l2);border-radius:8px;font-size:12px}.dsh-crate-inventory-item{display:flex;justify-content:space-between;gap:8px;padding:4px 0;border-bottom:1px solid var(--dsw-alias-border-l2)}.dsh-crate-inventory-item:last-child{border-bottom:0}
.dsh-crate-success{display:flex;flex-direction:column;gap:8px;padding:10px;border:1px solid var(--dsw-alias-label-positive);border-radius:8px;background:var(--dsw-alias-fill-positive);font-size:12px}
.dsh-crate-group{display:flex;flex-direction:column;gap:6px}.dsh-crate-group-head{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:2px 0}.dsh-crate-group-toggle{border:0;background:transparent;color:var(--dsw-alias-state-business-primary,#4f8cff);font:inherit;font-size:12px;cursor:pointer;padding:2px 4px}.dsh-crate-group-body{display:flex;flex-direction:column;gap:6px}
.dsh-crate-badge{margin-left:6px;padding:1px 5px;border-radius:4px;background:var(--dsw-alias-fill-tertiary);color:var(--dsw-alias-label-tertiary);font-size:11px;border:1px solid var(--dsw-alias-border-l2)}.dsh-crate-conflict{color:var(--dsw-alias-label-negative)}
.dsh-crate-modal-backdrop{position:fixed;inset:0;z-index:1000;display:flex;align-items:center;justify-content:center;padding:24px;background:rgba(0,0,0,.58)}.dsh-crate-modal{display:flex;flex-direction:column;gap:12px;width:min(420px,calc(100vw - 48px));padding:18px;border:1px solid var(--dsw-alias-border-l2,#3a3a40);border-radius:10px;background:var(--dsw-alias-fill-primary,#1d1d20);color:var(--dsw-alias-label-primary,#f9fafb);box-shadow:0 18px 50px rgba(0,0,0,.45)}.dsh-crate-modal h3{margin:0;font-size:16px}.dsh-crate-modal p{margin:0;font-size:13px;color:var(--dsw-alias-label-tertiary,#b6b6bd)}.dsh-crate-modal-actions{display:flex;justify-content:flex-end;gap:8px}.dsh-crate-modal-actions button:last-child{background:var(--dsw-alias-state-business-primary,#4b7bec);color:#fff}
.dsh-crate-tone-ok{color:var(--dsw-alias-label-positive)}.dsh-crate-tone-bad{color:var(--dsw-alias-label-negative)}.dsh-crate-tone-neutral{color:var(--dsw-alias-label-tertiary)}
`

type Tab = 'export' | 'import' | 'inspect' | 'verify' | 'history'
type ImportMode = 'new' | 'overwrite'
type Json = Record<string, unknown>
interface Profile { name: string; installedBundles: Json[] }
interface HistoryItem { time?: string; action?: string; status?: string; profile?: string; pack?: string; message?: string }
type PageProps = PropsRuntime<'settings.section'> & PropsLocale<'dsh.crate'>

export function isObject(value: unknown): value is Json { return value !== null && typeof value === 'object' && !Array.isArray(value) }

function formatTime(value: unknown): string {
  if (typeof value !== 'string' || !value) return ''
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}

function toneOf(status: unknown): string {
  const text = String(status ?? '').toUpperCase()
  if (text.includes('FAIL') || text.includes('ERROR') || text === 'BLOCKER' || text === 'UNKNOWN') return css.toneBad
  if (text.includes('PASS') || text === 'READY' || text === 'PREPARED' || text === 'OK') return css.toneOk
  return css.toneNeutral
}

const FIELD_LABELS: Record<string, DshCrateLocaleKey> = {
  code: 'diagCode', stage: 'diagStage', item: 'diagItem', expected: 'diagExpected',
  observed: 'diagObserved', evidence: 'diagEvidence', impact: 'diagImpact',
  originalProfileStatus: 'diagOriginalProfile', failedProfileStatus: 'diagFailedProfile',
  temporaryProfileStatus: 'diagTemporaryProfile', canContinue: 'diagCanContinue',
  suggestedNextStep: 'diagSuggestedNext',
}

function resultOf(value: Json): Json {
  return isObject(value.result) ? value.result : value
}

export function objects(value: unknown): Json[] {
  return Array.isArray(value) ? value.filter(isObject) : []
}

function failMessage(value: Json): string {
  const error = diagnosticOf(value)
  if (error !== undefined && typeof error.message === 'string' && error.message) return error.message
  const result = resultOf(value)
  if (typeof result.message === 'string' && result.message) return result.message
  return ''
}

function display(value: unknown): string {
  if (typeof value === 'string') return value
  const encoded = JSON.stringify(value, null, 2)
  return encoded === undefined ? String(value) : encoded
}

function pluginLabel(plugin: Json): string {
  const resolved = isObject(plugin.resolved) ? plugin.resolved : {}
  return `${String(plugin.name ?? 'unknown')}@${String(resolved.version ?? 'unknown')}`
}

function upsertProfileRow(list: Profile[], row: Json): Profile[] {
  const name = typeof row.name === 'string' ? row.name : ''
  if (!name) return list
  const entry: Profile = { name, installedBundles: objects(row.installedBundles) }
  return [...list.filter(item => item.name !== name), entry].sort((a, b) => a.name.localeCompare(b.name))
}

function installedBundleLabel(bundle: Json, t: (key: DshCrateLocaleKey) => string): string {
  const name = String(bundle.name ?? 'unknown')
  const version = String(bundle.version ?? 'unknown')
  const location = bundle.active === true ? t('active') : t('installationAnchor')
  const official = bundle.official === true ? ` · ${t('officialBadge')}` : ''
  return `${name}@${version} · ${location}${official}`
}

export function splitOfficial(items: Json[]): { official: Json[]; user: Json[] } {
  const official: Json[] = []
  const user: Json[] = []
  for (const item of items) (item.official === true ? official : user).push(item)
  return { official, user }
}

export function PluginName({ name, official, t }: { name: string; official: boolean; t: (key: DshCrateLocaleKey) => string }) {
  return <span>{name}{official ? <span className={css.badge} data-kind="official">{t('officialBadge')}</span> : null}</span>
}

export function PluginGroup({ label, count, defaultOpen = true, t, children }: { label: string; count: number; defaultOpen?: boolean; t: (key: DshCrateLocaleKey) => string; children: ReactNode }) {
  const [open, setOpen] = useState(defaultOpen)
  if (count === 0) return null
  return <div className={css.group} data-open={open}>
    <div className={css.groupHead}>
      <strong>{label} · {count}</strong>
      <button className={css.groupToggle} type="button" aria-expanded={open} onClick={() => setOpen(value => !value)}>{open ? t('collapse') : t('expand')}</button>
    </div>
    {open ? <div className={css.groupBody}>{children}</div> : null}
  </div>
}

function ExportPlugins({ value, t }: { value: Json | undefined; t: (key: DshCrateLocaleKey) => string }) {
  if (value === undefined) return null
  const result = resultOf(value)
  const plugins = objects(result.plugins)
  if (plugins.length === 0) return null
  return <div className={css.inventory} data-field="exportPlugins">
    <strong>{t('exportPlugins')}</strong>
    {plugins.map((plugin, index) => {
      const bundle = isObject(plugin.bundle) ? plugin.bundle : {}
      const artifact = isObject(plugin.artifact) ? plugin.artifact : {}
      const runtime = isObject(plugin.runtime) ? plugin.runtime : {}
      const bundleLabel = bundle.enabled === true
        ? `${t('bundle')} #${String(bundle.order ?? '?')}`
        : t('notBundle')
      return <div className={css.inventoryItem} data-field="exportPlugin" key={`${String(plugin.name)}-${index}`}>
        <span>{pluginLabel(plugin)}</span>
        <span>{bundleLabel} · {String(artifact.mode ?? 'unknown')} · {String(runtime.source ?? 'unknown')}</span>
      </div>
    })}
  </div>
}

export async function request(action: string, body: Json = {}): Promise<Json> {
  const response = await fetch('/dsh-crate/api', {
    method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ action, ...body }),
  })
  const value: unknown = await response.json()
  if (!isObject(value)) throw new Error('DSH Crate returned a malformed response')
  // A Core operation failure is still a report. Keep it in the UI so its
  // structured code/stage/evidence are not reduced to Error.message.
  return value
}

async function toBase64(file: File): Promise<string> {
  const bytes = new Uint8Array(await file.arrayBuffer())
  let binary = ''
  const chunk = 0x8000
  for (let index = 0; index < bytes.length; index += chunk) binary += String.fromCharCode(...bytes.subarray(index, index + chunk))
  return btoa(binary)
}

function diagnosticOf(value: Json): Json | undefined {
  if (isObject(value.error)) return value.error
  const result = resultOf(value)
  return isObject(result.error) ? result.error : undefined
}

function Diagnostic({ value, t }: { value: Json; t: (key: DshCrateLocaleKey) => string }) {
  const [copied, setCopied] = useState(false)
  const diagnostic = diagnosticOf(value)
  if (diagnostic === undefined) return null
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(JSON.stringify(diagnostic, null, 2))
      setCopied(true)
    } catch {
      setCopied(false)
    }
  }
  const fields = ['code', 'stage', 'item', 'expected', 'observed', 'evidence', 'impact', 'originalProfileStatus', 'failedProfileStatus', 'temporaryProfileStatus', 'canContinue', 'suggestedNextStep']
  return <div className={css.diagnostic} role="alert">
    <strong>{t('diagnostic')}</strong>
    <dl className={css.diagnosticGrid}>
      {fields.filter(field => diagnostic[field] !== undefined).map(field => <div key={field}>
        <dt>{t(FIELD_LABELS[field] ?? (field as DshCrateLocaleKey))}</dt><dd>{display(diagnostic[field])}</dd>
      </div>)}
    </dl>
    <div><button className={css.button} type="button" onClick={() => void copy()}>{copied ? t('diagnosticCopied') : t('copyDiagnostic')}</button></div>
    <details><summary>{t('fullDiagnostic')}</summary><pre>{JSON.stringify(diagnostic, null, 2)}</pre></details>
  </div>
}

function Report({ value, t }: { value: Json | undefined; t: (key: DshCrateLocaleKey) => string }) {
  if (value === undefined) return <p className={css.muted}>{t('noReport')}</p>
  const result = resultOf(value)
  const findings = objects(result.findings)
  return <div className={css.report} data-status={String(result.status ?? 'UNKNOWN')}>
    <div><strong>{t('coreStatus')}</strong> · <span className={toneOf(result.status)}>{String(result.status ?? 'UNKNOWN')}</span></div>
    {findings.length > 0 ? <>
      <strong>{t('findings')}</strong>
      {findings.map((finding, index) => <div className={css.finding} key={`${String(finding.code)}-${index}`}>
        {String(finding.severity ?? '')} / {String(finding.code ?? '')}: {String(finding.message ?? '')}
      </div>)}
    </> : null}
    <Diagnostic value={value} t={t} />
    <details><summary>{t('rawJson')}</summary><pre>{JSON.stringify(result, null, 2)}</pre></details>
  </div>
}

function ImportPreview({ value, t, targetProfile, overwrite }: { value: Json; t: (key: DshCrateLocaleKey) => string; targetProfile?: string; overwrite: boolean }) {
  const result = resultOf(value)
  const pack = isObject(result.pack) ? result.pack : {}
  const profile = isObject(pack.profile) ? pack.profile : {}
  const requiredPlugins = objects(result.requiredPlugins)
  const optionalPlugins = objects(result.optionalPlugins)
  const warningCount = typeof result.warningCount === 'number' ? result.warningCount : 0
  const environment = isObject(result.environment) ? result.environment : {}
  const target = targetProfile?.trim() || String(result.targetProfile ?? profile.name ?? 'UNKNOWN')
  const safety = overwrite ? t('overwritePreview') : t('willNotOverwrite')
  return <div className={css.preview}>
    <strong>{t('importPreview')}</strong>
    <div className={css.previewRow} data-field="targetProfile"><strong>{t('targetProfile')}</strong><span>{target}</span></div>
    <div className={css.previewRow} data-field="warningCount"><strong>{t('warningCount')}</strong><span>{warningCount}</span></div>
    <div className={css.previewRow} data-field="requiredPlugins"><strong>{t('requiredPlugins')}</strong><span>{requiredPlugins.map(pluginLabel).join(', ') || t('none')}</span></div>
    <div className={css.previewRow} data-field="optionalPlugins"><strong>{t('optionalPlugins')}</strong><span>{optionalPlugins.map(pluginLabel).join(', ') || t('none')}</span></div>
    <div className={css.previewRow} data-field="environment"><strong>{t('environment')}</strong><pre>{display(environment)}</pre></div>
    <div className={css.previewRow} data-field="coreDecision"><strong>{t('coreDecision')}</strong><span>{display(result.canContinue)}</span></div>
    <div className={css.previewRow} data-field="safety"><strong>{t('safety')}</strong><span>{safety}</span></div>
  </div>
}

function ImportSuccess({ value, t }: { value: Json | undefined; t: (key: DshCrateLocaleKey) => string }) {
  if (value === undefined) return null
  const result = resultOf(value)
  if (result.status !== 'prepared') return null
  const plan = isObject(result.plan) ? result.plan : {}
  const installed = objects(result.installedPlugins)
  const profileName = String(plan.profileName ?? 'UNKNOWN')
  const overwritten = plan.overwrite === true
  return <div className={css.success} data-field="importSuccess" role="status">
    <strong>{t('importSuccess')}</strong>
    <div data-field="preparedProfile"><strong>{t('preparedProfile')}</strong> · {profileName}</div>
    {overwritten ? <div data-field="overwriteConfirmed">{t('overwritePreview')}</div> : null}
    <div data-field="installedPlugins"><strong>{t('installedPlugins')}</strong> · {installed.map(plugin => `${String(plugin.name ?? 'unknown')}@${String(plugin.version ?? 'unknown')}`).join(', ') || t('none')}</div>
  </div>
}

function VerifyReport({ value, t }: { value: Json | undefined; t: (key: DshCrateLocaleKey) => string }) {
  if (value === undefined) return <p className={css.muted}>{t('noReport')}</p>
  const result = resultOf(value)
  const steps = objects(result.steps)
  return <div className={css.report} data-status={String(result.status ?? 'UNKNOWN')}>
    <div><strong>{t('coreStatus')}</strong> · {String(result.status ?? 'UNKNOWN')}</div>
    {String(result.status ?? '') === 'UNTESTED' ? <p className={css.muted}>{t('verifyUntestedNote')}</p> : null}
    {steps.map((step, index) => <div className={css.step} key={`${String(step.name)}-${index}`}>
      <span className={`${css.stepStatus} ${toneOf(step.status)}`}>{String(step.status ?? 'UNKNOWN')}</span>
      <span><strong>{String(step.name ?? 'unknown')}</strong> — {String(step.message ?? '')}<br /><small>{display(step.evidence ?? {})}</small></span>
    </div>)}
    <Diagnostic value={value} t={t} />
    <details><summary>{t('rawJson')}</summary><pre>{JSON.stringify(result, null, 2)}</pre></details>
  </div>
}

export function DshCratePage({ t }: PageProps) {
  const [tab, setTab] = useState<Tab>('export')
  const [profiles, setProfiles] = useState<Profile[]>([])
  const [profile, setProfile] = useState('')
  const [modes, setModes] = useState<Record<string, string>>({})
  const [file, setFile] = useState<File>()
  const [report, setReport] = useState<Json>()
  const [history, setHistory] = useState<HistoryItem[]>([])
  const [busy, setBusy] = useState(false)
  const busyRef = useRef(false)
  const [error, setError] = useState('')
  const [importMode, setImportMode] = useState<ImportMode>('new')
  const [importTarget, setImportTarget] = useState('')
  const [deleteTarget, setDeleteTarget] = useState('')
  const [deleteReport, setDeleteReport] = useState<Json>()
  const [switchTarget, setSwitchTarget] = useState('')
  const [switchReport, setSwitchReport] = useState<Json>()
  const [runtime, setRuntime] = useState<Json>()
  const [runtimePlugins, setRuntimePlugins] = useState<Json[]>([])
  const [updatedAt, setUpdatedAt] = useState('')
  const [toast, setToast] = useState<{ key: number; text: string }>()
  const toastSeq = useRef(0)
  const showToast = (text: string) => { toastSeq.current += 1; setToast({ key: toastSeq.current, text }) }
  const [createTarget, setCreateTarget] = useState('')
  const [newProfileDialogOpen, setNewProfileDialogOpen] = useState(false)
  const [newProfileDraft, setNewProfileDraft] = useState('')
  const [newProfileDialogError, setNewProfileDialogError] = useState('')

  const selectedProfile = useMemo(() => profiles.find(item => item.name === profile), [profiles, profile])
  const installedBundles = selectedProfile?.installedBundles ?? []
  const exportBundles = installedBundles.filter(bundle => bundle.active === true)
  const conflictBundles = installedBundles.filter(bundle => bundle.conflict === true)
  const exportNames = exportBundles.map(bundle => String(bundle.name ?? '')).filter(Boolean)
  const canImport = isObject(report?.result) && report.result.canContinue === true
  const currentRuntimeProfile = typeof runtime?.currentProfile === 'string' ? runtime.currentProfile : ''

  const loadProfiles = async () => {
    const value = await request('profiles')
    const rows = objects(value.profiles).map(item => ({
      name: String(item.name ?? ''),
      installedBundles: objects(item.installedBundles),
    }))
    const runtimeValue = isObject(value.runtime) ? value.runtime : undefined
    const activeName = typeof runtimeValue?.currentProfile === 'string' ? runtimeValue.currentProfile : ''
    const switchable = rows.filter(item => item.name !== activeName)
    setProfiles(rows)
    setProfile(current => (rows.some(item => item.name === current) ? current : rows[0]?.name || ''))
    setDeleteTarget(current => rows.some(item => item.name === current) ? current : rows[0]?.name || '')
    setSwitchTarget(current => switchable.some(item => item.name === current) ? current : switchable[0]?.name || '')
    if (runtimeValue) setRuntime(runtimeValue)
    setRuntimePlugins(objects(value.runtimePlugins))
    setUpdatedAt(new Date().toLocaleTimeString())
  }
  useEffect(() => {
    void loadProfiles().catch(caught => setError(caught instanceof Error ? caught.message : String(caught)))
  }, [])
  useEffect(() => {
    busyRef.current = busy
  }, [busy])
  const loadProfilesRef = useRef<() => Promise<void>>(() => Promise.resolve())
  useEffect(() => {
    loadProfilesRef.current = loadProfiles
  })
  // Keep the Profile/bundle list fresh without a manual reload: poll while
  // the section is mounted and refresh when the tab regains focus. Operations
  // that are in flight are left alone so polling cannot interrupt them.
  useEffect(() => {
    let disposed = false
    const refresh = () => {
      if (disposed || busyRef.current) return
      void loadProfilesRef.current().catch(caught => setError(caught instanceof Error ? caught.message : String(caught)))
    }
    const onVisibility = () => { if (document.visibilityState === 'visible') refresh() }
    const timer = window.setInterval(refresh, 10000)
    window.addEventListener('focus', refresh)
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      disposed = true
      window.clearInterval(timer)
      window.removeEventListener('focus', refresh)
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [])
  useEffect(() => {
    if (tab !== 'history') return
    void request('history').then(value => {
      setHistory(objects(value.history) as HistoryItem[])
    }).catch(caught => setError(caught instanceof Error ? caught.message : String(caught)))
  }, [tab])

  const run = async (action: string, body: Json) => {
    setBusy(true); setError('')
    try {
      const value = await request(action, body)
      setReport(value)
      const result = resultOf(value)
      const profileLabel = String(body.profileName ?? '')
      if (value.status === 'failed' || result.status === 'failed' || result.status === 'FAIL') {
        showToast(`${t('error')}: ${failMessage(value) || t('error')}`)
      } else if (action === 'export' && typeof value.downloadName === 'string') {
        showToast(`${t('exportSuccess')} ${profileLabel}`.trim())
      } else if (action === 'inspect') {
        showToast(t('inspectSuccess'))
      } else if (action === 'verify') {
        if (value.success === true) showToast(`${t('verifySuccess')} ${profileLabel}`.trim())
        else if (result.status === 'FAIL') showToast(`${t('error')}: ${failMessage(value) || t('verifyFailed')}`)
        else showToast(`${t('verifyFinished')} ${profileLabel} · ${String(result.status ?? '')}`.trim())
      }
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : String(caught)
      setError(message)
      showToast(`${t('error')}: ${message}`)
    }
    finally { setBusy(false) }
  }
  const createSelectedProfile = async () => {
    const target = createTarget.trim()
    if (!target) { showToast(t('profileNameRequired')); return }
    if (profiles.some(item => item.name === target)) { showToast(t('profileNameExists')); return }
    setBusy(true); setError('')
    try {
      const value = await request('create-profile', { profileName: target })
      if (value.status === 'failed') {
        showToast(`${t('error')}: ${failMessage(value) || t('error')}`)
      } else {
        setCreateTarget('')
        await loadProfiles()
        showToast(`${t('createSuccess')} ${target}`)
      }
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : String(caught)
      setError(message)
      showToast(`${t('error')}: ${message}`)
    } finally { setBusy(false) }
  }
  const deleteSelectedProfile = async () => {
    const target = deleteTarget.trim()
    if (!target) return
    if (!window.confirm(`${t('deleteProfileWarning')}\n\n${target}`)) return
    setBusy(true); setError('')
    try {
      const value = await request('delete-profile', { profileName: target, confirmDelete: true })
      setDeleteReport(value)
      if (value.status === 'failed') {
        showToast(`${t('error')}: ${failMessage(value) || t('error')}`)
      } else {
        await loadProfiles()
        showToast(`${t('deleteSuccess')} ${target}`)
      }
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : String(caught)
      setError(message)
      showToast(`${t('error')}: ${message}`)
    } finally { setBusy(false) }
  }
  const switchSelectedProfile = async () => {
    const target = switchTarget.trim()
    if (!target) return
    if (target === currentRuntimeProfile) {
      // Switching to the Profile that is already running is a no-op: the
      // requested end state already holds, so report it as a benign result.
      setSwitchReport({ status: 'ok', result: { status: 'already-active', profileName: target, message: `Profile is already active: ${target}`, impact: 'The current DSH process was not changed; the requested Profile is already running.', canContinue: true } })
      showToast(`${t('switchAlreadyActive')} ${target}`)
      return
    }
    if (!window.confirm(`${t('switchProfileWarning')}\n\n${target}`)) {
      setSwitchReport({ status: 'failed', error: { code: 'SWITCH_CANCELED', stage: 'planning', item: target, message: t('switchCanceled') } })
      showToast(t('switchCanceled'))
      return
    }
    setBusy(true); setError(''); setSwitchReport(undefined)
    try {
      const scheduled = await request('switch-profile', { profileName: target, confirmSwitch: true })
      if (scheduled.status === 'failed') { setSwitchReport(scheduled); showToast(`${t('error')}: ${failMessage(scheduled) || t('error')}`); return }
      const operationId = typeof scheduled.operationId === 'string' ? scheduled.operationId : ''
      let last: Json = scheduled
      if (!operationId) { setSwitchReport({ status: 'failed', error: { code: 'SWITCH_REPORT_MISSING', stage: 'scheduling', message: 'Switch operation did not return an operation ID.' } }); showToast(`${t('error')}: ${t('error')}`); return }
      for (let attempt = 0; attempt < 130; attempt += 1) {
        await new Promise(resolve => setTimeout(resolve, 500))
        try {
          const value = await request('switch-status', { operationId })
          last = value
          const result = resultOf(value)
          if (result.status === 'ready' || result.status === 'failed') break
        } catch {
          // The old DSH process is expected to disappear briefly before the new one binds.
        }
      }
      setSwitchReport(last)
      const result = resultOf(last)
      if (result.status === 'ready') {
        await loadProfiles()
        showToast(`${t('switchSuccess')} ${target}`)
      } else if (result.status === 'failed') {
        showToast(`${t('error')}: ${failMessage(last) || t('error')}`)
      }
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : String(caught)
      setError(message)
      showToast(`${t('error')}: ${message}`)
    } finally { setBusy(false) }
  }
  const importPack = async () => {
    if (!file) return
    if (importMode === 'new') {
      const packResult = resultOf(report ?? {})
      const pack = isObject(packResult.pack) ? packResult.pack : {}
      const packProfile = isObject(pack.profile) ? pack.profile : {}
      setNewProfileDraft(importTarget.trim() || String(packProfile.name ?? ''))
      setNewProfileDialogError('')
      setNewProfileDialogOpen(true)
      return
    }
    const target = importTarget.trim() || profiles[0]?.name || ''
    if (!target) { setError(t('noProfiles')); return }
    if (!window.confirm(`${t('overwriteWarning')}\n\n${target}`)) { showToast(t('overwriteCanceled')); setError(''); return }
    setBusy(true); setError('')
    try {
      const value = await request('import', { packBase64: await toBase64(file), targetProfile: target, overwrite: true, confirmOverwrite: true })
      setReport(value)
      if (value.status === 'failed' || !(isObject(value.result) && value.result.status === 'prepared')) {
        showToast(`${t('error')}: ${failMessage(value) || t('error')}`)
      } else {
        await loadProfiles()
        setProfiles(current => isObject(value.profile) ? upsertProfileRow(current, value.profile) : current)
        showToast(`${t('importOverwritten')} ${target}`)
      }
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : String(caught)
      setError(message)
      showToast(`${t('error')}: ${message}`)
    } finally { setBusy(false) }
  }
  const confirmNewProfileImport = async () => {
    if (!file) return
    const target = newProfileDraft.trim()
    if (!target) { setNewProfileDialogError(t('profileNameRequired')); return }
    if (profiles.some(item => item.name === target)) { setNewProfileDialogError(t('profileNameExists')); return }
    setImportTarget(target)
    setNewProfileDialogOpen(false)
    setNewProfileDialogError('')
    setBusy(true); setError('')
    try {
      const value = await request('import', { packBase64: await toBase64(file), targetProfile: target, overwrite: false, confirmOverwrite: false })
      setReport(value)
      if (value.status === 'failed' || !(isObject(value.result) && value.result.status === 'prepared')) {
        showToast(`${t('error')}: ${failMessage(value) || t('error')}`)
      } else {
        await loadProfiles()
        setProfiles(current => isObject(value.profile) ? upsertProfileRow(current, value.profile) : current)
        setProfile(target)
        showToast(`${t('importSuccess')} ${target}`)
      }
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : String(caught)
      setError(message)
      showToast(`${t('error')}: ${message}`)
    } finally { setBusy(false) }
  }
  const inspectFile = async (nextFile: File | undefined) => {
    setFile(nextFile); setReport(undefined); setError('')
    if (nextFile === undefined) return
    await run('inspect', { packBase64: await toBase64(nextFile) })
  }
  const input = <label className={css.label}>{t('choosePack')}<input className={css.file} type="file" accept=".dshcrate,application/zip" onChange={event => { void inspectFile(event.target.files?.[0]) }} /></label>
  const profileSelect = <label className={css.label}>{t('profile')}<select className={css.select} value={profile} onChange={event => setProfile(event.target.value)}>{profiles.map(item => <option key={item.name} value={item.name}>{item.name}</option>)}</select></label>
  const profileManager = <div className={css.inventory} data-field="profileManagement">
    <strong>{t('profileManagement')}</strong>
    <span className={css.muted}>{t('currentRunningProfile')}: {currentRuntimeProfile || t('none')}</span>
    <label className={css.label}>{t('createProfile')}<input className={css.file} value={createTarget} placeholder={t('createProfilePlaceholder')} onChange={event => setCreateTarget(event.target.value)} /></label>
    <span className={css.muted}>{t('createProfileHint')}</span>
    <button className={css.button} type="button" disabled={busy || !createTarget.trim()} onClick={() => void createSelectedProfile()}>{busy ? t('createPending') : t('createProfile')}</button>
    <label className={css.label}>{t('switchProfile')}<select className={css.select} value={switchTarget && switchTarget !== currentRuntimeProfile ? switchTarget : profiles.find(item => item.name !== currentRuntimeProfile)?.name || ''} onChange={event => setSwitchTarget(event.target.value)}>{profiles.filter(item => item.name !== currentRuntimeProfile).map(item => <option key={item.name} value={item.name}>{item.name}</option>)}</select></label>
    <button className={css.button} type="button" disabled={busy || !switchTarget} onClick={() => void switchSelectedProfile()}>{busy ? t('switchPending') : t('switchProfile')}</button>
    <label className={css.label}>{t('deleteProfile')}<select className={css.select} value={deleteTarget || profiles[0]?.name || ''} onChange={event => setDeleteTarget(event.target.value)}>{profiles.map(item => <option key={item.name} value={item.name}>{item.name}</option>)}</select></label>
    <span className={css.muted}>{t('deleteProfileWarning')}</span>
    <button className={css.button} type="button" disabled={busy || !deleteTarget} onClick={() => void deleteSelectedProfile()}>{t('confirmDelete')}</button>
    {switchReport ? <Report value={switchReport} t={t} /> : null}
    {deleteReport ? <Report value={deleteReport} t={t} /> : null}
  </div>

  return <div className={css.section}>
    <style>{STYLE}</style>
    <h2 className={css.heading}>{t('title')}</h2><p className={css.intro}>{t('intro')}</p>
    {profiles.length > 0 ? profileManager : null}
    <div className={css.tabs} role="tablist">
      {(['export', 'import', 'inspect', 'verify', 'history'] as Tab[]).map(item => <button key={item} className={css.tab} data-active={tab === item} type="button" role="tab" onClick={() => setTab(item)}>{t(item)}</button>)}
    </div>
    {error ? <p className={css.error} role="alert">{t('error')}: {error}</p> : null}
    {tab === 'export' ? <div className={css.form}>
      {profiles.length === 0 ? <p className={css.muted}>{t('noProfiles')}</p> : <>
        {profileSelect}
        <div className={css.inventory} data-field="runtimePlugins">
          <strong>{t('runtimePlugins')}{runtimePlugins.length > 0 ? ` · ${runtimePlugins.length}` : ''}</strong>
          <span className={css.muted}>{t('updatedAt')}: {updatedAt || t('none')}</span>
          <button className={css.button} type="button" disabled={busy} onClick={() => { void loadProfiles().catch(caught => setError(caught instanceof Error ? caught.message : String(caught))) }}>{t('refresh')}</button>
          {currentRuntimeProfile && selectedProfile?.name !== currentRuntimeProfile
            ? <span className={css.muted}>{t('runtimePluginsInactive')}</span>
            : runtimePlugins.length === 0
              ? <span className={css.muted}>{t('none')}</span>
              : (() => {
                  const groups = splitOfficial(runtimePlugins)
                  const row = (plugin: Json) => <div className={css.inventoryItem} data-field="runtimePlugin" key={`${String(plugin.id ?? plugin.name)}`}><PluginName name={String(plugin.name ?? 'unknown')} official={plugin.official === true} t={t} /><span>{plugin.enabled === true ? t('runtimeEnabled') : t('runtimeDisabled')} · {String(plugin.phase ?? '—')}</span></div>
                  return <>
                    <PluginGroup label={t('userPlugins')} count={groups.user.length} defaultOpen t={t}>{groups.user.map(row)}</PluginGroup>
                    <PluginGroup label={t('officialPlugins')} count={groups.official.length} defaultOpen={false} t={t}>{groups.official.map(row)}</PluginGroup>
                  </>
                })()}
        </div>
        <div className={css.inventory}><strong>{t('declaredBundles')}</strong>{exportBundles.length === 0 ? <span className={css.muted}>{t('none')}</span> : (() => {
          const groups = splitOfficial(exportBundles)
          const row = (bundle: Json) => {
            const name = String(bundle.name ?? '')
            const conflict = bundle.conflict === true
            return <div className={css.inventoryItem} key={`${name}-${String(bundle.version)}`}><span>{installedBundleLabel(bundle, t)}{conflict ? <span className={css.conflict}> · {t('conflictWarning')}</span> : null}</span><span>{String(bundle.patch ?? '')}</span><select aria-label={`${name} ${t('artifactMode')}`} className={css.select} disabled={conflict} value={modes[name] ?? 'embedded'} onChange={event => setModes(current => ({ ...current, [name]: event.target.value }))}><option value="embedded">{t('embedded')}</option><option value="reference-only">{t('referenceOnly')}</option></select></div>
          }
          return <>
            <PluginGroup label={t('userPlugins')} count={groups.user.length} defaultOpen t={t}>{groups.user.map(row)}</PluginGroup>
            <PluginGroup label={t('officialPlugins')} count={groups.official.length} defaultOpen={false} t={t}>{groups.official.map(row)}</PluginGroup>
          </>
        })()}</div>
        {conflictBundles.length > 0 ? <div className={css.inventory} data-field="conflictBundles"><strong>{t('conflictBundles')}</strong>{conflictBundles.map(bundle => <div className={css.inventoryItem} key={`conflict-${String(bundle.name)}`}><span>{installedBundleLabel(bundle, t)}</span><span className={css.conflict}>{t('conflictWarning')}</span></div>)}</div> : null}
        <button className={css.button} type="button" disabled={busy || !profile} onClick={() => void run('export', { profileName: profile, includeInstalledBundles: true, embed: exportNames.filter(name => (modes[name] ?? 'embedded') === 'embedded'), referenceOnly: exportNames.filter(name => (modes[name] ?? 'embedded') === 'reference-only') })}>{busy ? t('exporting') : t('exportButton')}</button>
        {isObject(report) && typeof report.downloadName === 'string' ? <a href={`/dsh-crate/download?name=${encodeURIComponent(report.downloadName)}`}>{t('download')}</a> : null}
        <ExportPlugins value={report} t={t} />
        <Report value={report} t={t} />
      </>}
    </div> : null}
    {tab === 'import' ? <div className={css.form}>
      {input}
      <label className={css.label}>{t('importMode')}<select className={css.select} value={importMode} onChange={event => setImportMode(event.target.value as ImportMode)}><option value="new">{t('newProfile')}</option><option value="overwrite">{t('overwriteProfile')}</option></select></label>
      {importMode === 'new' ? <label className={css.label}>{t('newProfileName')}<input className={css.file} value={importTarget} placeholder={t('newProfileName')} onChange={event => setImportTarget(event.target.value)} /></label> : <>
        <label className={css.label}>{t('targetProfile')}<select className={css.select} value={importTarget || profiles[0]?.name || ''} onChange={event => setImportTarget(event.target.value)}>{profiles.map(item => <option key={item.name} value={item.name}>{item.name}</option>)}</select></label>
        <p className={css.error}>{t('overwriteWarning')}</p>
      </>}
      {report ? <ImportPreview value={report} t={t} targetProfile={(importMode === 'overwrite' ? (importTarget || profiles[0]?.name) : importTarget) || undefined} overwrite={importMode === 'overwrite'} /> : null}
      {report ? <ImportSuccess value={report} t={t} /> : null}
      {report ? <Report value={report} t={t} /> : null}
      <button className={css.button} type="button" disabled={busy || !file || !canImport || (importMode === 'overwrite' && !importTarget && profiles.length === 0)} onClick={() => void importPack()}>{busy ? t('working') : t('importButton')}</button>
    </div> : null}
    {tab === 'inspect' ? <div className={css.form}>{input}<Report value={report} t={t} /><button className={css.button} type="button" disabled={busy || !file} onClick={async () => { if (file) await run('inspect', { packBase64: await toBase64(file) }) }}>{busy ? t('working') : t('inspectButton')}</button></div> : null}
    {tab === 'verify' ? <div className={css.form}>{profiles.length === 0 ? <p className={css.muted}>{t('noProfiles')}</p> : <>{profileSelect}<button className={css.button} type="button" disabled={busy || !profile} onClick={() => void run('verify', { profileName: profile, mode: 'web' })}>{busy ? t('working') : t('verifyButton')}</button><VerifyReport value={report} t={t} /></>}</div> : null}
    {tab === 'history' ? <ul className={css.history}>{history.length === 0 ? <li className={css.muted}>{t('noHistory')}</li> : history.map((item, index) => <li className={css.historyItem} key={`${item.time}-${index}`}><span>{formatTime(item.time)} · {item.action} · {item.profile ?? item.pack ?? ''}</span><strong className={toneOf(item.status)}>{item.status}</strong></li>)}</ul> : null}
    {newProfileDialogOpen ? <div className={css.modalBackdrop} role="presentation">
      <div className={css.modal} role="dialog" aria-modal="true" aria-labelledby="dsh-crate-new-profile-title">
        <h3 id="dsh-crate-new-profile-title">{t('newProfileName')}</h3>
        <p>{t('confirmImport')}</p>
        <label className={css.label}>{t('newProfileName')}<input autoFocus className={css.file} value={newProfileDraft} onChange={event => { setNewProfileDraft(event.target.value); setNewProfileDialogError('') }} /></label>
        {newProfileDialogError ? <p className={css.error} role="alert">{newProfileDialogError}</p> : null}
        <div className={css.modalActions}>
          <button className={css.button} type="button" onClick={() => setNewProfileDialogOpen(false)}>{t('cancel')}</button>
          <button className={css.button} type="button" onClick={() => void confirmNewProfileImport()}>{t('confirmImportAction')}</button>
        </div>
      </div>
    </div> : null}
    {toast ? <Toast key={toast.key} text={toast.text} onDone={() => setToast(undefined)} /> : null}
  </div>
}
