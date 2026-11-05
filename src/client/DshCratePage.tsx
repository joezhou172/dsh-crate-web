import { PluginFilters, emptyPluginFilter, hasPluginFilter, matchesPluginFilter } from './PluginFilters.tsx'
import { ExportSelection, ReferenceConfirmation } from './ExportSelection.tsx'
import type { CatalogPlugin, ExportChoice } from './ExportSelection.tsx'
import { SizePreview } from './SizePreview.tsx'
import { CrateIcon } from './CrateIcon.tsx'
import { DESIGN_STYLE } from './design-style.ts'
import { useEffect, useMemo, useRef, useState } from 'react'
import { DetailsButton, ReportContext, ReportDialog } from './ReportDialog.tsx'
import type { AgentBridge } from './ReportDialog.tsx'
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
  badge: 'dsh-crate-badge', conflict: 'dsh-crate-conflict',
}

export const STYLE = `
.dsh-crate-choice{padding:10px 0;border-bottom:1px solid var(--dsw-alias-border-l2);overflow-wrap:anywhere}
.dsh-crate-choice-controls{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-top:6px}
.dsh-crate-choice-controls>*{min-width:0;max-width:100%}
.dsh-crate-choice label{font-size:13px}
.dsh-crate-section{display:flex;flex-direction:column;gap:12px;max-width:760px;color:var(--dsw-alias-label-primary)}
.dsh-crate-heading{margin:0;font-size:18px;font-weight:600}.dsh-crate-intro,.dsh-crate-muted{margin:0;font-size:13px;color:var(--dsw-alias-label-tertiary)}
.dsh-crate-tabs{display:flex;gap:20px;border-bottom:1px solid var(--dsw-alias-border-l2);overflow:auto}.dsh-crate-tab{border:0;padding:7px 1px 9px;background:transparent;color:var(--dsw-alias-label-tertiary);font:inherit;cursor:pointer;white-space:nowrap}
.dsh-crate-tab[data-active=true]{color:var(--dsw-alias-label-primary);border-bottom:2px solid var(--dsw-alias-label-primary)}.dsh-crate-form{display:flex;flex-direction:column;gap:10px}
.dsh-crate-label{display:flex;flex-direction:column;gap:5px;font-size:13px}.dsh-crate-select,.dsh-crate-file{max-width:100%;min-width:0;padding:7px 8px;border:1px solid var(--dsw-alias-border-l2);border-radius:6px;background-color:var(--dsw-alias-bg-layer-1);color:var(--dsw-alias-label-primary);color-scheme:inherit}.dsh-crate-select option{background-color:var(--dsw-alias-bg-layer-1);color:var(--dsw-alias-label-primary)}.dsh-crate-inventory-item{overflow-wrap:anywhere}.dsh-crate-inventory-item>span{min-width:0}
.dsh-crate-plugin{display:grid;grid-template-columns:minmax(0,1fr) 150px;gap:8px;align-items:center}.dsh-crate-button{align-self:flex-start;border:0;border-radius:6px;padding:8px 13px;background:var(--dsw-alias-state-business-primary);color:white;cursor:pointer}.dsh-crate-button:disabled{cursor:default;opacity:.5}
.dsh-crate-report,.dsh-crate-preview,.dsh-crate-diagnostic{display:flex;flex-direction:column;gap:8px;padding:10px;border:1px solid var(--dsw-alias-border-l2);border-radius:8px;overflow-wrap:anywhere;font-size:12px}.dsh-crate-finding,.dsh-crate-step{padding:7px;border-radius:5px;background:var(--dsw-alias-bg-module-platform)}
.dsh-crate-preview-row{display:grid;grid-template-columns:170px minmax(0,1fr);gap:8px}.dsh-crate-preview-row pre{margin:0;white-space:pre-wrap}.dsh-crate-diagnostic-grid{display:grid;grid-template-columns:150px minmax(0,1fr);gap:6px}.dsh-crate-diagnostic-grid dt{font-weight:600}.dsh-crate-diagnostic-grid dd{margin:0;white-space:pre-wrap}.dsh-crate-step{display:flex;gap:8px;align-items:flex-start}.dsh-crate-step-status{min-width:80px;font-weight:600}
.dsh-crate-history{list-style:none;display:flex;flex-direction:column;gap:8px;padding:0;margin:0}.dsh-crate-history-item{display:flex;justify-content:space-between;gap:10px;padding:8px;border-bottom:1px solid var(--dsw-alias-border-l2);font-size:12px}.dsh-crate-error{color:var(--dsw-alias-state-error-primary)}
.dsh-crate-inventory{display:flex;flex-direction:column;gap:6px;padding:8px;border:1px solid var(--dsw-alias-border-l2);border-radius:8px;font-size:12px}.dsh-crate-inventory-item{display:flex;justify-content:space-between;gap:8px;padding:4px 0;border-bottom:1px solid var(--dsw-alias-border-l2)}.dsh-crate-inventory-item:last-child{border-bottom:0}
.dsh-crate-success{display:flex;flex-direction:column;gap:8px;padding:10px;border:1px solid var(--dsw-alias-state-success-primary);border-radius:8px;background:var(--dsw-alias-state-success-tertiary);font-size:12px}
.dsh-crate-group{display:flex;flex-direction:column;gap:6px}.dsh-crate-group-head{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:2px 0}.dsh-crate-group-toggle{border:0;background:transparent;color:var(--dsw-alias-state-business-primary);font:inherit;font-size:12px;cursor:pointer;padding:2px 4px}.dsh-crate-group-body{display:flex;flex-direction:column;gap:6px}
.dsh-crate-badge{margin-left:6px;padding:1px 5px;border-radius:4px;background:var(--dsw-alias-bg-module-platform);color:var(--dsw-alias-label-tertiary);font-size:11px;border:1px solid var(--dsw-alias-border-l2)}.dsh-crate-conflict{color:var(--dsw-alias-state-error-primary)}
.dsh-crate-modal-backdrop{position:fixed;inset:0;z-index:1000;display:flex;align-items:center;justify-content:center;padding:24px;background:rgba(0,0,0,.58)}.dsh-crate-modal{display:flex;flex-direction:column;gap:12px;width:min(420px,calc(100vw - 48px));padding:18px;border:1px solid var(--dsw-alias-border-l2);border-radius:10px;background:var(--dsw-alias-bg-layer-2);color:var(--dsw-alias-label-primary);box-shadow:0 18px 50px rgba(0,0,0,.45)}.dsh-crate-modal h3{margin:0;font-size:16px}.dsh-crate-modal p{margin:0;font-size:13px;color:var(--dsw-alias-label-tertiary)}.dsh-crate-modal-actions{display:flex;justify-content:flex-end;gap:8px}.dsh-crate-modal-actions button:last-child{background:var(--dsw-alias-state-business-primary);color:#fff}

.dsh-crate-section{min-width:0;width:100%;line-height:1.55}
.dsh-crate-section summary{cursor:pointer;font-weight:600;padding:6px 0}
.dsh-crate-section details[open]>summary{margin-bottom:8px}
.dsh-crate-section pre{white-space:pre-wrap;overflow-wrap:anywhere}
.dsh-crate-secondary{border:1px solid var(--dsw-alias-border-l2);border-radius:6px;padding:8px 12px;background:transparent;color:inherit;font:inherit;cursor:pointer;align-self:flex-start}
.dsh-crate-secondary:disabled{opacity:.5;cursor:default}
.dsh-crate-section button:focus-visible,.dsh-crate-section summary:focus-visible,.dsh-crate-report-dialog :focus-visible{outline:2px solid var(--dsw-alias-state-business-primary);outline-offset:3px}
.dsh-crate-report-dialog{box-sizing:border-box;width:min(840px,calc(100vw - 32px));max-height:calc(100dvh - 32px);padding:20px;border:1px solid var(--dsw-alias-border-l2);border-radius:12px;background:var(--dsw-alias-bg-layer-1);color:var(--dsw-alias-label-primary);overflow:auto}
.dsh-crate-report-dialog::backdrop{background:rgba(0,0,0,.55)}
.dsh-crate-report-dialog header{display:flex;align-items:center;justify-content:space-between;gap:12px}
.dsh-crate-report-dialog h3{margin:0;font-size:18px}
.dsh-crate-report-dialog pre{box-sizing:border-box;max-height:50dvh;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere;padding:12px;border:1px solid var(--dsw-alias-border-l2);border-radius:6px;font-size:12px;line-height:1.6}
.dsh-crate-dialog-actions,.dsh-crate-status-list{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}
.dsh-crate-status-list span{padding:3px 8px;border:1px solid var(--dsw-alias-border-l2);border-radius:5px}
.dsh-crate-report-dialog p{overflow-wrap:anywhere}

@media(max-width:600px){
  [data-dsh-module=settings]:has(.dsh-crate-section){flex-direction:column;width:calc(100vw - 24px);max-width:calc(100vw - 24px)}
  [data-dsh-module=settings]:has(.dsh-crate-section)>nav{width:100%;gap:8px;padding:12px 12px 0}
  [data-dsh-module=settings]:has(.dsh-crate-section)>nav>div:last-child{flex-direction:row;overflow-x:auto}
  [data-dsh-module=settings]:has(.dsh-crate-section)>nav button{flex-shrink:0}
  [data-dsh-module=settings]:has(.dsh-crate-section)>div{min-height:0}
  [data-dsh-module=settings]:has(.dsh-crate-section)>div>div:last-child{padding:0 12px 12px}
  .dsh-crate-section{min-width:0;max-width:100%}
  .dsh-crate-inventory-item{flex-wrap:wrap;justify-content:flex-start}
  .dsh-crate-inventory-item>span:first-of-type{flex:1 1 100%}
  .dsh-crate-preview-row,.dsh-crate-diagnostic-grid{grid-template-columns:minmax(0,1fr)}
  .dsh-crate-section pre{max-width:100%;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere}
}

`

type Tab = 'export' | 'import' | 'inspect' | 'verify' | 'history'
type ImportMode = 'new' | 'overwrite'
export type Json = Record<string, unknown>
interface Profile { name: string; installedBundles: Json[] }
interface HistoryItem { time?: string; action?: string; status?: string; profile?: string; pack?: string; message?: string }
type PageProps = PropsRuntime<'settings.section'> & PropsLocale<'dsh.crate'> & { agentBridge?: AgentBridge }

export function isObject(value: unknown): value is Json { return value !== null && typeof value === 'object' && !Array.isArray(value) }

function resultOf(value: Json): Json {
  return isObject(value.result) ? value.result : value
}

export function objects(value: unknown): Json[] {
  return Array.isArray(value) ? value.filter(isObject) : []
}

function display(value: unknown): string {
  if (typeof value === 'string') return value
  const encoded = JSON.stringify(value, null, 2)
  return encoded === undefined ? String(value) : encoded
}

function pluginLabel(plugin: Json): string {
  const resolved = isObject(plugin.resolved) ? plugin.resolved : {}
  const runtime = isObject(plugin.runtime) ? plugin.runtime : {}
  const version = typeof resolved.version === 'string' && resolved.version !== 'unknown'
    ? resolved.version : runtime.version
  return `${String(plugin.name ?? 'unknown')}@${String(version ?? 'unknown')}`
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
  return <details className={css.inventory} data-field="exportPlugins">
    <summary>{t('exportPlugins')} · {plugins.length}</summary>
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
  </details>
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

export function statusLabel(value: unknown, t: (key: DshCrateLocaleKey) => string): string {
  const labels: Record<string, DshCrateLocaleKey> = {
    PASS: 'statusPass', FAIL: 'statusFail', failed: 'statusFail', UNTESTED: 'statusUntested', DEGRADED: 'statusDegraded',
    UNKNOWN: 'statusUnknown', prepared: 'statusPrepared', ready: 'statusReady', READY: 'statusReady',
    BLOCKED: 'statusBlocked', BLOCKER: 'statusBlocked', NOT_READY: 'statusBlocked', WARNING: 'statusWarning', 'already-active': 'switchAlreadyActive',
    exported: 'exportSuccess', created: 'createSuccess', deleted: 'deleteSuccess',
    YES: 'statusYes', NO: 'statusNo', UNPROVEN: 'statusUnproven', excluded: 'statusExcluded', unsupported: 'statusUnsupported',
    portable: 'statusPortable', 'secret-name-only': 'statusSecretName',
  }
  const key = labels[String(value)]
  return key ? t(key) : String(value ?? t('statusUnknown'))
}

function Report({ value, t }: { value: Json | undefined; t: (key: DshCrateLocaleKey) => string }) {
  if (value === undefined) return null
  const result = resultOf(value)
  const findings = objects(result.findings)
  return <div className={css.report} data-status={String(result.status ?? 'UNKNOWN')}>
    <strong>{t('coreStatus')} · {statusLabel(result.status ?? value.status, t)}</strong>
    {findings.length ? <span>{t('findings')}: {findings.length}</span> : null}
    {diagnosticOf(value) ? <p className={css.error}>{t('failureSummary')}</p> : null}
    <DetailsButton value={value} t={t} />
  </div>
}

function ImportPreview({ value, t, targetProfile, overwrite }: { value: Json; t: (key: DshCrateLocaleKey) => string; targetProfile?: string; overwrite: boolean }) {
  const result = resultOf(value)
  if (typeof result.canContinue !== 'boolean') return null
  const pack = isObject(result.pack) ? result.pack : {}
  const profile = isObject(pack.profile) ? pack.profile : {}
  const requiredPlugins = objects(result.requiredPlugins)
  const optionalPlugins = objects(result.optionalPlugins)
  const warningCount = typeof result.warningCount === 'number' ? result.warningCount : 0
  const environment = isObject(result.environment) ? result.environment : {}
  const secrets = isObject(result.secrets) ? result.secrets : {}
  const target = targetProfile?.trim() || String(result.targetProfile ?? profile.name ?? 'UNKNOWN')
  const safety = overwrite ? t('overwritePreview') : t('willNotOverwrite')
  const blockers = objects(result.findings).filter(item => item.severity === 'BLOCKER')
  return <div className={css.preview}>
    <strong>{t('importPreview')}</strong>
    {!result.canContinue ? <div role="alert" className={css.error} data-field="importBlocker">
      <strong>{t('importBlocked')}</strong>
      {blockers.slice(0, 3).map((item, index) => <p key={index}>{item.code === 'ENVIRONMENT_VERSION_MISMATCH'
        ? `${t('versionMismatch')}: ${String(item.item ?? 'DSH/Node')} · ${t('packRequires')} ${String(item.expected ?? '')} / ${t('currentVersion')} ${String(item.observed ?? '')}`
        : String(item.message ?? item.code ?? t('failureSummary')).split(/\r?\n/)[0]}</p>)}
      <span>{t('blockedNextStep')}</span>
    </div> : null}
    <div className={css.previewRow} data-field="targetProfile"><strong>{t('targetProfile')}</strong><span>{target}</span></div>
    <div className={css.previewRow} data-field="warningCount"><strong>{t('warningCount')}</strong><span>{warningCount}</span></div>
    <div className={css.previewRow} data-field="requiredPlugins"><strong>{t('requiredPlugins')}</strong><span>{requiredPlugins.length}</span></div>
    <div className={css.previewRow} data-field="optionalPlugins"><strong>{t('optionalPlugins')}</strong><span>{optionalPlugins.length}</span></div>
    <details><summary>{t('environment')}</summary><pre>{display(environment)}</pre></details>
    <div className={css.previewRow} data-field="requiredSecrets"><strong>{t('requiredSecrets')}</strong><span>{Array.isArray(secrets.required) ? secrets.required.join(', ') || t('none') : t('none')}</span></div>
    <div className={css.previewRow} data-field="missingSecrets"><strong>{t('missingSecrets')}</strong><span>{Array.isArray(secrets.missing) ? secrets.missing.join(', ') || t('none') : t('none')}</span></div>
    <div className={css.previewRow} data-field="coreDecision"><strong>{t('coreDecision')}</strong><span>{result.canContinue ? t('canProceed') : t('cannotProceed')}</span></div>
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
    <div data-field="installedPlugins"><strong>{t('installedPlugins')}</strong> · {installed.length}</div>
  </div>
}

function VerifyReport({ value, t }: { value: Json | undefined; t: (key: DshCrateLocaleKey) => string }) {
  if (value === undefined) return null
  const result = resultOf(value)
  const steps = objects(result.steps)
  const counts = steps.reduce<Record<string, number>>((all, step) => {
    const key = String(step.status ?? 'UNKNOWN'); all[key] = (all[key] ?? 0) + 1; return all
  }, {})
  return <div className={css.report} data-status={String(result.status ?? 'UNKNOWN')}>
    <strong>{t('coreStatus')} · {statusLabel(result.status, t)}</strong>
    <span>{t('stepCount')}: {steps.length}</span>
    <div className="dsh-crate-status-list">{Object.entries(counts).map(([status, count]) => <span key={status}>{statusLabel(status, t)} {count}</span>)}</div>
    <DetailsButton value={value} t={t} />
  </div>
}

export function DshCratePage({ t, agentBridge }: PageProps) {
  const [detail, setDetail] = useState<{ value: unknown; key: number }>()
  const detailSequence = useRef(0)
  const openDetails = (value: unknown) => setDetail({ value, key: ++detailSequence.current })
  const [managerOpen, setManagerOpen] = useState(false)
  const [tab, setTab] = useState<Tab>('export')
  const [subpage, setSubpage] = useState<'export-plugins' | 'runtime-plugins' | null>(null)
  const pageRoot = useRef<HTMLDivElement>(null)
  const subpageHeading = useRef<HTMLHeadingElement>(null)
  const returnFocus = useRef<HTMLElement | null>(null)
  const mainScroll = useRef(0)
  const scrollOwner = () => {
    let node = pageRoot.current?.parentElement
    while (node) {
      if (/(auto|scroll)/.test(getComputedStyle(node).overflowY)) return node
      node = node.parentElement
    }
    return document.scrollingElement as HTMLElement | null
  }
  const openSubpage = (page: 'export-plugins' | 'runtime-plugins') => {
    returnFocus.current = document.activeElement as HTMLElement
    mainScroll.current = scrollOwner()?.scrollTop ?? 0
    setSubpage(page)
  }
  const closeSubpage = () => setSubpage(null)
  useEffect(() => {
    const owner = scrollOwner()
    if (owner) owner.scrollTop = subpage ? 0 : mainScroll.current
    if (subpage) subpageHeading.current?.focus({ preventScroll: true })
    else returnFocus.current?.focus({ preventScroll: true })
  }, [subpage])
  const [profiles, setProfiles] = useState<Profile[]>([])
  const [profile, setProfile] = useState('')
  const [choices, setChoices] = useState<ExportChoice[]>([])
  const [catalog, setCatalog] = useState<CatalogPlugin[]>([])
  const [catalogReady, setCatalogReady] = useState(false)
  const [compression, setCompression] = useState('fast')
  const [confirmReference, setConfirmReference] = useState(false)
  const [preset, setPreset] = useState('custom')
  const [secretNames, setSecretNames] = useState('')
  const [dataSelection, setDataSelection] = useState<Json[]>([])
  const [dataOwners, setDataOwners] = useState<Record<string, string>>({})
  const [dataKinds, setDataKinds] = useState<Record<string, string>>({})
  const [exportPlan, setExportPlan] = useState<Json>()
  const [reviewedSelection, setReviewedSelection] = useState('')
  const [downloadSelection, setDownloadSelection] = useState('')
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
  const [runtimeFilter, setRuntimeFilter] = useState({ ...emptyPluginFilter })
  const [toast, setToast] = useState<{ key: number; text: string }>()
  const toastSeq = useRef(0)
  const showToast = (text: string) => { toastSeq.current += 1; setToast({ key: toastSeq.current, text }) }
  const [createTarget, setCreateTarget] = useState('')
  const [newProfileDialogOpen, setNewProfileDialogOpen] = useState(false)
  const [newProfileDraft, setNewProfileDraft] = useState('')
  const [newProfileDialogError, setNewProfileDialogError] = useState('')
  useEffect(() => { if (error) openDetails({ status: 'failed', message: error }) }, [error])

  const selectedProfile = useMemo(() => profiles.find(item => item.name === profile), [profiles, profile])
  const installedBundles = selectedProfile?.installedBundles ?? []
  const exportBundles = installedBundles.filter(bundle => bundle.active === true)
  const conflictBundles = installedBundles.filter(bundle => bundle.conflict === true)
  const exportNames = choices.filter(row => row.included).map(row => row.name)
  const requiredSecrets = [...new Set(secretNames.split(/[\s,]+/).filter(Boolean))]
  const invalidSecretNames = requiredSecrets.some(name => !/^[A-Za-z_][A-Za-z0-9_]*$/.test(name))
  const exportBody = {
    requestVersion: 2, profileName: profile, preset, dataSelection, requiredSecrets,
    compression, plugins: choices,
  }
  const exportSignature = JSON.stringify(exportBody)
  const previewExport = async () => {
    if (busyRef.current) return
    busyRef.current = true
    setBusy(true); setError('')
    try {
      const value = await request('export-plan', exportBody)
      if (value.status === 'failed') { openDetails(value); setReviewedSelection(''); return }
      if (typeof resultOf(value).planId !== 'string') throw new Error(t('catalogUnavailable'))
      setExportPlan(resultOf(value))
      setReviewedSelection(exportSignature)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught))
      setReviewedSelection('')
    } finally { busyRef.current = false; setBusy(false) }
  }
  useEffect(() => {
    setDataSelection([]); setDataOwners({}); setDataKinds({}); setSecretNames('')
    setExportPlan(undefined); setReviewedSelection('')
  }, [profile])
  useEffect(() => {
    let disposed = false
    setChoices([]); setCatalog([]); setCatalogReady(false)
    setConfirmReference(false)
    if (profile) void request('export-catalog', { profileName: profile }).then(value => {
      if (disposed) return
      const result = resultOf(value)
      if (value.status === 'failed' || result.requestVersion !== 2) { openDetails(value); return }
      const items = objects(result.plugins) as unknown as CatalogPlugin[]
      setCatalog(items)
      setChoices(items.map(item => ({ name: item.name, included: true, selection: { kind: 'installed' }, artifactMode: 'embedded', activateOnImport: item.active })))
      setCatalogReady(true)
    }).catch(error => { if (!disposed) setError(String(error)) })
    return () => { disposed = true }
  }, [profile])
  useEffect(() => { setConfirmReference(false) }, [exportSignature])
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
    if (busyRef.current) return
    busyRef.current = true
    setBusy(true); setError('')
    if (action === 'export') setDownloadSelection('')
    try {
      const value = await request(action, body)
      setReport(value)
      const result = resultOf(value)
      const profileLabel = String(body.profileName ?? '')
      if (value.status === 'failed' || result.status === 'failed' || result.status === 'FAIL') {
        openDetails(value); showToast(t('error'))
      } else if (action === 'export' && typeof value.downloadName === 'string') {
        setDownloadSelection(exportSignature)
        showToast(`${t('exportSuccess')} ${profileLabel}`.trim())
      } else if (action === 'inspect') {
        showToast(t('inspectSuccess'))
      } else if (action === 'verify' && value.success !== true) {
        showToast(`${t('verifyFinished')} ${profileLabel} · ${statusLabel(result.status, t)}`.trim())
      }
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : String(caught)
      setError(message)
      showToast(t('error'))
    }
    finally { busyRef.current = false; setBusy(false) }
  }
  const createSelectedProfile = async () => {
    const target = createTarget.trim()
    if (!target) { showToast(t('profileNameRequired')); return }
    if (profiles.some(item => item.name === target)) { showToast(t('profileNameExists')); return }
    setBusy(true); setError('')
    try {
      const value = await request('create-profile', { profileName: target })
      if (value.status === 'failed') {
        openDetails(value); showToast(t('error'))
      } else {
        setCreateTarget('')
        await loadProfiles()
        showToast(`${t('createSuccess')} ${target}`)
      }
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : String(caught)
      setError(message)
      showToast(t('error'))
    } finally { busyRef.current = false; setBusy(false) }
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
        openDetails(value); showToast(t('error'))
      } else {
        await loadProfiles()
        showToast(`${t('deleteSuccess')} ${target}`)
      }
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : String(caught)
      setError(message)
      showToast(t('error'))
    } finally { busyRef.current = false; setBusy(false) }
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
      if (scheduled.status === 'failed') { setSwitchReport(scheduled); openDetails(scheduled); showToast(t('error')); return }
      const operationId = typeof scheduled.operationId === 'string' ? scheduled.operationId : ''
      let last: Json = scheduled
      if (!operationId) { setSwitchReport({ status: 'failed', error: { code: 'SWITCH_REPORT_MISSING', stage: 'scheduling', message: 'Switch operation did not return an operation ID.' } }); showToast(t('error')); return }
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
        openDetails(last); showToast(t('error'))
      }
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : String(caught)
      setError(message)
      showToast(t('error'))
    } finally { busyRef.current = false; setBusy(false) }
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
    if (!window.confirm(`${t('overwriteWarning')}\n\n${target}`)) { setError(t('overwriteCanceled')); return }
    setBusy(true); setError('')
    try {
      const value = await request('import', { packBase64: await toBase64(file), targetProfile: target, overwrite: true, confirmOverwrite: true })
      setReport(value)
      if (value.status === 'failed' || !(isObject(value.result) && value.result.status === 'prepared')) {
        openDetails(value); showToast(t('error'))
      } else {
        await loadProfiles()
        setProfiles(current => isObject(value.profile) ? upsertProfileRow(current, value.profile) : current)
        showToast(`${t('importOverwritten')} ${target}`)
      }
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : String(caught)
      setError(message)
      showToast(t('error'))
    } finally { busyRef.current = false; setBusy(false) }
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
        openDetails(value); showToast(t('error'))
      } else {
        await loadProfiles()
        setProfiles(current => isObject(value.profile) ? upsertProfileRow(current, value.profile) : current)
        setProfile(target)
        showToast(`${t('importSuccess')} ${target}`)
      }
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : String(caught)
      setError(message)
      showToast(t('error'))
    } finally { busyRef.current = false; setBusy(false) }
  }
  const inspectFile = async (nextFile: File | undefined) => {
    setFile(nextFile); setReport(undefined); setError('')
    if (nextFile === undefined) return
    await run('inspect', { packBase64: await toBase64(nextFile) })
  }
  const input = <label className={css.label}>{t('choosePack')}<input className={css.file} type="file" accept=".dshcrate,application/zip" onChange={event => { void inspectFile(event.target.files?.[0]) }} /></label>
  const profileSelect = <label className={css.label}>{t('profile')}<select aria-label={t('profile')} className={css.select} value={profile} onChange={event => {
    if (choices.some(row => row.selection.kind === 'registry' || !row.included) && !window.confirm(t('discardExportDraft'))) return
    setProfile(event.target.value)
  }}>{profiles.map(item => <option key={item.name} value={item.name}>{item.name}</option>)}</select></label>
  const profileManager = <details id="crate-profile-manager" className={css.inventory} data-field="profileManagement" open={managerOpen} hidden={!managerOpen}>
    <summary>{t('profileManagement')}</summary>
    <span className={css.muted}>{t('currentRunningProfile')}: {currentRuntimeProfile || t('none')}</span>
    <label className={css.label}>{t('createProfile')}<input className={css.file} value={createTarget} placeholder={t('createProfilePlaceholder')} onChange={event => setCreateTarget(event.target.value)} /></label>
    <span className={css.muted}>{t('createProfileHint')}</span>
    <button className={css.button} type="button" disabled={busy || !createTarget.trim()} onClick={() => void createSelectedProfile()}>{busy ? t('createPending') : t('createProfile')}</button>
    <label className={css.label}>{t('switchProfile')}<select className={css.select} value={switchTarget && switchTarget !== currentRuntimeProfile ? switchTarget : profiles.find(item => item.name !== currentRuntimeProfile)?.name || ''} onChange={event => setSwitchTarget(event.target.value)}>{profiles.filter(item => item.name !== currentRuntimeProfile).map(item => <option key={item.name} value={item.name}>{item.name}</option>)}</select></label>
    <button className={css.button} type="button" disabled={busy || !switchTarget || runtime?.restartConfigured !== true} onClick={() => void switchSelectedProfile()}>{busy ? t('switchPending') : t('switchProfile')}</button>
    {runtime?.restartConfigured === false ? <span className={css.muted}>{t('switchUnavailable')}</span> : null}
    <label className={css.label}>{t('deleteProfile')}<select className={css.select} value={deleteTarget || profiles[0]?.name || ''} onChange={event => setDeleteTarget(event.target.value)}>{profiles.map(item => <option key={item.name} value={item.name}>{item.name}</option>)}</select></label>
    <span className={css.muted}>{t('deleteProfileWarning')}</span>
    <button className={css.button} type="button" disabled={busy || !deleteTarget} onClick={() => void deleteSelectedProfile()}>{t('confirmDelete')}</button>
    {switchReport ? <Report value={switchReport} t={t} /> : null}
    {deleteReport ? <Report value={deleteReport} t={t} /> : null}
  </details>

  return <ReportContext.Provider value={openDetails}><div ref={pageRoot} className={css.section}>
    <style>{STYLE + DESIGN_STYLE}</style>
    <div className="dsh-crate-page" hidden={subpage !== null}>
    <header className="dsh-crate-header">
      <div className="dsh-crate-brand"><CrateIcon name="cube" /><div><h2 className={css.heading}>{t('title')}</h2><p className={css.intro}>{t('intro')}</p></div></div>
      {profiles.length > 0 ? <button className="dsh-crate-manage" type="button" aria-expanded={managerOpen} aria-controls="crate-profile-manager" onClick={() => setManagerOpen(value => !value)}>{t('profileManagement')}</button> : null}
    </header>
    {profiles.length > 0 ? profileManager : null}
    <div className={css.tabs} role="tablist">
      {(['export', 'import', 'inspect', 'verify', 'history'] as Tab[]).map(item => <button key={item} className={css.tab} data-active={tab === item} type="button" role="tab" aria-selected={tab === item} onClick={() => setTab(item)}>{t(item)}</button>)}
    </div>
    {error ? <div role="alert" className={css.error}>{t('failureSummary')} <DetailsButton value={{ status: 'failed', message: error }} t={t} /></div> : null}
    {tab === 'export' ? <div className={css.form}>
      {profiles.length === 0 ? <p className={css.muted}>{t('noProfiles')}</p> : <>
        <h3 className="dsh-crate-section-title">{t('exportHeading')}</h3>
        <div className="dsh-crate-environment">{profileSelect}{profile === currentRuntimeProfile ? <span className="dsh-crate-running"><i aria-hidden="true" />{t('currentRunningProfile')}</span> : null}</div>
        <div className="dsh-crate-page-links">
          <button type="button" className="dsh-crate-page-link" data-field="exportPluginsEntry" disabled={busy} onClick={() => openSubpage('export-plugins')}>
            <span>{t('exportSelection')}</span><span className="dsh-crate-count">{choices.filter(row => row.included).length}/{choices.length}</span><span aria-hidden="true">›</span>
          </button>
          <button type="button" className="dsh-crate-page-link" data-field="runtimePluginsEntry" onClick={() => openSubpage('runtime-plugins')}>
            <span>{t('runtimePlugins')}</span><span className="dsh-crate-count">{runtimePlugins.length}</span><span aria-hidden="true">›</span>
          </button>
        </div>
        <label className={css.label}>{t('compression')}<select aria-label={t('compression')} className={css.select} disabled={busy} value={compression} onChange={event => setCompression(event.target.value)}>
          <option value="fast">{t('compressionFast')}</option><option value="compact">{t('compressionCompact')}</option>
        </select></label>
        {conflictBundles.length > 0 ? <div className={css.inventory} data-field="conflictBundles"><strong>{t('conflictBundles')}</strong>{conflictBundles.map(bundle => <div className={css.inventoryItem} key={`conflict-${String(bundle.name)}`}><span>{installedBundleLabel(bundle, t)}</span><span className={css.conflict}>{t('conflictWarning')}</span></div>)}</div> : null}
        <details><summary>{t('advanced')}</summary>
        <label className="dsh-crate-preset">{t('exportPreset')} <select className={css.select} value={preset} disabled={busy} onChange={event => {
          const value = event.target.value
          setPreset(value)
          if (value !== 'custom') setChoices(rows => rows.map(row => ({ ...row, artifactMode: value === 'freeze' ? 'embedded' : 'reference-only' })))
        }}><option value="share">{t('sharePreset')}</option><option value="freeze">{t('freezePreset')}</option><option value="custom">{t('customPreset')}</option></select></label>
<label className={css.label}>{t('requiredSecrets')}
          <input className={css.file} value={secretNames} disabled={busy} autoComplete="off" spellCheck={false} aria-describedby="crate-secret-hint" aria-invalid={invalidSecretNames} onChange={event => setSecretNames(event.target.value)} />
        </label>
        <p className={css.muted} id="crate-secret-hint">{t('secretNamesHint')}</p>
        {invalidSecretNames ? <p className={css.error} role="alert">{t('invalidSecretNames')}</p> : null}</details>
        {exportPlan ? <div className={css.inventory} data-field="exportPreview">
          <SizePreview value={exportPlan.sizePreview} stale={reviewedSelection !== exportSignature} t={t} />
          {Array.isArray(exportPlan.requiredSecrets) && exportPlan.requiredSecrets.length > 0 ? <><strong>{t('requiredSecrets')}</strong><span data-field="reviewedSecrets">{exportPlan.requiredSecrets.join(', ')}</span></> : null}
          <details><summary>{t('portableData')} · {objects(exportPlan.dataInventory).length}</summary><p>{t('privacyReview')}</p>
          {objects(exportPlan.dataInventory).map((item, index) => {
            const path = typeof item.path === 'string' ? item.path : ''
            const conversation = item.kind === 'conversation'
            const chosen = dataSelection.some(row => row.path === path)
            const owner = conversation ? '@deepseek-ai/dsh-session-persistence-jsonl' : dataOwners[path] || ''
            const selectable = item.selectable === true || item.classification === 'portable'
            return <div className={css.inventoryItem} key={path || index}>
              {selectable ? <input type="checkbox" aria-label={path} disabled={busy || !owner} checked={chosen} onChange={event => {
                setDataSelection(current => event.target.checked
                  ? [...current.filter(row => row.path !== path), { path, owner, kind: conversation ? 'conversation' : dataKinds[path] || 'plugin-data' }]
                  : current.filter(row => row.path !== path))
              }} /> : null}
              <span>{path || String(item.name ?? '')} · {statusLabel(item.classification, t)}</span>
              {selectable && !conversation ? <>
                <select className={css.select} aria-label={path + ' ' + t('dataOwner')} disabled={busy || chosen} value={owner} onChange={event => setDataOwners(current => ({ ...current, [path]: event.target.value }))}>
                  <option value="">{t('chooseOwner')}</option>{objects(exportPlan.plugins).map(plugin => <option key={String(plugin.name)} value={String(plugin.name)}>{String(plugin.name)}</option>)}
                </select>
                <select className={css.select} aria-label={path + ' ' + t('dataKind')} disabled={busy || chosen} value={dataKinds[path] || 'plugin-data'} onChange={event => setDataKinds(current => ({ ...current, [path]: event.target.value }))}>
                  <option value="plugin-data">{t('pluginData')}</option><option value="plugin-config">{t('pluginConfig')}</option><option value="plugin-workflow">{t('pluginWorkflow')}</option>
                </select>
              </> : null}
            </div>
          })}
          </details>
          {isObject(exportPlan.completeness) ? <>
            <strong>{t('completeness')}</strong>
            <p>{t('embedded')}: {Array.isArray(exportPlan.completeness.embedded) ? exportPlan.completeness.embedded.length : 0}
              {' · '}{t('referenceOnly')}: {Array.isArray(exportPlan.completeness.referenceOnly) ? exportPlan.completeness.referenceOnly.length : 0}
              {' · '}{t('offlineRestore')}{': '}{statusLabel(exportPlan.completeness.offlineRestorable ?? 'UNPROVEN', t)}</p>
            <DetailsButton value={exportPlan} t={t} />
          </> : null}
        </div> : null}
        <div className="dsh-crate-export-actions"><button className={reviewedSelection === exportSignature ? 'dsh-crate-secondary' : css.button} type="button" disabled={busy || !profile || !catalogReady || !exportNames.length || invalidSecretNames} onClick={() => void previewExport()}>{busy ? t('working') : t('previewExport')}</button><button className={css.button} type="button" disabled={busy || !profile || invalidSecretNames || reviewedSelection !== exportSignature} onClick={() => { if (choices.some(row => row.included && row.artifactMode === 'reference-only')) setConfirmReference(true); else void run('export', { ...exportBody, planId: exportPlan?.planId }) }}>{busy ? t('exporting') : t('exportButton')}</button>{reviewedSelection !== exportSignature ? <span className={css.muted}>{t('previewFirst')}</span> : null}</div>
        {!busy && downloadSelection === exportSignature && isObject(report) && typeof report.downloadName === 'string' ? <a href={`/dsh-crate/download?name=${encodeURIComponent(report.downloadName)}`}>{t('download')}</a> : null}
        <ExportPlugins value={downloadSelection === exportSignature ? report : undefined} t={t} />
        <Report value={downloadSelection === exportSignature ? report : undefined} t={t} />
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
    {tab === 'history' ? <ul className={css.history}>{history.length === 0 ? <li className={css.muted}>{t('noHistory')}</li> : history.map((item, index) => <li className={css.historyItem} key={`${item.time}-${index}`}><span>{item.time} · {(['export', 'import', 'inspect', 'verify'].includes(item.action ?? '') ? t(item.action as Tab) : item.action)} · {item.profile ?? item.pack ?? ''}</span><strong>{statusLabel(item.status, t)}</strong><DetailsButton value={item} t={t} /></li>)}</ul> : null}
    </div>
    <div className="dsh-crate-page" hidden={subpage === null} data-field="pluginSubpage">
      <header className="dsh-crate-subpage-header">
        <button type="button" className="dsh-crate-secondary dsh-crate-text-button" onClick={closeSubpage}><span aria-hidden="true">←</span>{t('backToExport')}</button>
        <div><h2 ref={subpageHeading} tabIndex={-1} className="dsh-crate-section-title">{subpage === 'runtime-plugins' ? t('runtimePlugins') : t('exportSelection')}</h2>
          <p className={css.muted}>{subpage === 'runtime-plugins' ? currentRuntimeProfile || t('none') : profile}</p></div>
      </header>
      <div className="dsh-crate-page" hidden={subpage !== 'export-plugins'} data-field="exportPluginsPage">
        {catalogReady ? <ExportSelection key={profile} rows={choices} catalog={catalog} disabled={busy} t={t}
          onChange={rows => { setChoices(rows); setPreset('custom') }} onError={openDetails}
          query={packageName => request('registry-versions', { profileName: profile, packageName })} /> : <p className={css.muted}>{t('catalogUnavailable')}</p>}
        <button type="button" className={css.button} onClick={closeSubpage}>{t('doneSelecting')}</button>
      </div>
      <div className="dsh-crate-page" hidden={subpage !== 'runtime-plugins'} data-field="runtimePlugins">
            <p className={css.muted}>{t('exportOnlyHint')}</p>
          <div className="dsh-crate-toolbar"><span className={css.muted}>{t('updatedAt')}: {updatedAt || t('none')}</span>
          <button className="dsh-crate-secondary dsh-crate-text-button" type="button" disabled={busy} onClick={() => { void loadProfiles().catch(caught => setError(caught instanceof Error ? caught.message : String(caught))) }}>{t('refresh')}</button></div>
          {currentRuntimeProfile && selectedProfile?.name !== currentRuntimeProfile
            ? <span className={css.muted}>{t('runtimePluginsInactive')}</span>
            : runtimePlugins.length === 0
              ? <span className={css.muted}>{t('none')}</span>
              : (() => {
                  const runtimeChoice = (name: string) => choices.find(item => item.name === name) ?? choices.filter(item => name.startsWith(item.name + '/')).sort((a, b) => b.name.length - a.name.length)[0]
                  const filtered = runtimePlugins.filter(plugin => matchesPluginFilter(runtimeFilter, String(plugin.name ?? ''), plugin.official === true, runtimeChoice(String(plugin.name ?? ''))?.included))
                  const groups = splitOfficial(filtered)
                  const row = (plugin: Json) => {
                    const name = String(plugin.name ?? 'unknown')
                    const choice = runtimeChoice(name)
                    const required = choice && catalog.some(item => item.name === choice.name && item.official)
                    return <div className={css.inventoryItem} data-field="runtimePlugin" key={String(plugin.id ?? plugin.name)}>
                      {choice ? <label className="dsh-crate-runtime-choice"><input type="checkbox" aria-label={name + ' ' + t('includeInExport')} checked={choice.included} disabled={busy || required} onChange={event => { setChoices(rows => rows.map(item => item.name === choice.name ? { ...item, included: event.target.checked } : item)); setPreset('custom') }} /><span className="dsh-crate-sr-only">{t('includeInExport')}</span></label> : <span aria-hidden="true" />}
                      <div className="dsh-crate-plugin-copy"><PluginName name={name} official={plugin.official === true} t={t} /><span className={css.muted}>{plugin.enabled === true ? t('runtimeEnabled') : t('runtimeDisabled')} · {String(plugin.phase ?? '—')}</span></div>
                      {required || !choice ? <span className={css.muted}>{t(required ? 'officialRequired' : 'runtimeNotExportable')}</span> : null}
                    </div>
                  }
                  return <>
                    <PluginFilters value={runtimeFilter} onChange={setRuntimeFilter} count={filtered.length} total={runtimePlugins.length} t={t} />
                    <PluginGroup key={'user-' + JSON.stringify(runtimeFilter)} label={t('userPlugins')} count={groups.user.length} defaultOpen t={t}>{groups.user.map(row)}</PluginGroup>
                    <PluginGroup key={JSON.stringify(runtimeFilter)} label={t('officialPlugins')} count={groups.official.length} defaultOpen={hasPluginFilter(runtimeFilter)} t={t}>{groups.official.map(row)}</PluginGroup>
                  </>
                })()}
      </div>
    </div>
    {newProfileDialogOpen ? <div className={css.modalBackdrop} role="presentation">
      <div className={css.modal} role="dialog" aria-modal="true" aria-labelledby="dsh-crate-new-profile-title">
        <h3 id="dsh-crate-new-profile-title">{t('newProfileName')}</h3>
        <p>{t('confirmImport')}</p>
        <label className={css.label}>{t('newProfileName')}<input autoFocus className={css.file} value={newProfileDraft} onChange={event => { setNewProfileDraft(event.target.value); setNewProfileDialogError('') }} /></label>
        {newProfileDialogError ? <p className={css.error} role="alert">{newProfileDialogError}</p> : null}
        <div className={css.modalActions}>
          <button className={css.button} type="button" onClick={() => setNewProfileDialogOpen(false)}>{t('cancel')}</button>
          <button className={css.button} type="button" onClick={() => void confirmNewProfileImport()}>{t('importButton')}</button>
        </div>
      </div>
    </div> : null}
    {confirmReference ? <ReferenceConfirmation evidence={objects(exportPlan?.referencePlugins)} rows={choices.filter(row => row.included && row.artifactMode === 'reference-only')} t={t} onCancel={() => setConfirmReference(false)} onConfirm={() => { setConfirmReference(false); void run('export', { ...exportBody, planId: exportPlan?.planId, confirmReferences: true }) }} /> : null}
    {detail ? <ReportDialog key={`report-${detail.key}`} value={detail.value} t={t} bridge={agentBridge} onClose={() => setDetail(undefined)} /> : null}
    {toast ? <Toast key={toast.key} text={toast.text} onDone={() => setToast(undefined)} /> : null}
  </div></ReportContext.Provider>
}
