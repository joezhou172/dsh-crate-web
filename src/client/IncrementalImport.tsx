import { useEffect, useRef, useState } from 'react'
import type { DshCrateLocaleKey } from './locales.ts'
type Json = Record<string, any>
export function IncrementalImport({ file, target, mode, compatibilityPolicy, choiceRevision, t, send, onResult, onBusy }: {
  file?: File; target: string; mode: 'add' | 'update'; compatibilityPolicy: 'compatible' | 'strict';
  t: (key: DshCrateLocaleKey) => string; send: (body: Json) => Promise<Json>; onResult: (value: Json) => void;
  onBusy: (value: boolean) => void;
  choiceRevision?: string;
}) {
  const [plan, setPlan] = useState<Json>()
  const [busy, setBusy] = useState(false)
  useEffect(() => { onBusy(busy); return () => onBusy(false) }, [busy, onBusy])
  const revision = useRef(0)
  useEffect(() => { revision.current++; setPlan(undefined); return () => { revision.current++ } }, [file, target, mode, compatibilityPolicy, choiceRevision])
  const preview = async () => {
    setBusy(true); setPlan(undefined)
    const current = revision.current
    try {
      const value = await send({ targetProfile: target, incremental: mode, planOnly: true, compatibilityPolicy })
      if (current !== revision.current) return
      onResult(value)
      if (value.status === 'ok' && value.result?.plan?.planToken) setPlan(value.result.plan)
    } finally { setBusy(false) }
  }
  const execute = async () => {
    if (!plan || !window.confirm(`${t('incrementalConfirm')}\n\n${target}`)) return
    setBusy(true)
    try { onResult(await send({ targetProfile: target, incremental: mode, planToken: plan.planToken, compatibilityPolicy })) }
    finally { setPlan(undefined); setBusy(false) }
  }
  return <div className="dsh-crate-preview" data-field="incrementalImport">
    <p>{t('snapshotHint')}</p>
    <button className="dsh-crate-secondary" disabled={busy || !file || !target} onClick={() => void preview()}>{t('incrementalPreview')}</button>
    {plan ? <>
      <ul>{(plan.plugins ?? []).map((row: Json) => <li key={row.name}>{row.name} · {t(row.action === 'keep' ? 'incrementalKeep' : row.action === 'add' ? 'incrementalAdd' : 'incrementalUpdate')}</li>)}</ul>
      {plan.storage?.length > 0 ? <ul>{plan.storage.map((row: Json) => <li key={row.path}>{row.path} · {t(row.action === 'keep' ? 'incrementalKeep' : 'incrementalAdd')}</li>)}</ul> : null}
      {plan.retiredBundles?.length > 0 ? <ul role="status">{plan.retiredBundles.map((row: Json) => <li key={row.name}>{row.name} · {t('retiredBundleNotice')}</li>)}</ul> : null}
      {plan.hostRuntimeAdaptations?.length > 0 ? <ul role="status">{plan.hostRuntimeAdaptations.map((row: Json) => <li key={row.name}>{row.name} · {t('hostRuntimeNotice')} · {row.from ?? '—'} → {row.to}</li>)}</ul> : null}
      <span>{t('incrementalConfig')}: {plan.configuration?.length ?? 0}</span>
      <ul>{(plan.configuration ?? []).map((row: Json) => <li key={row.path}>{row.path}</li>)}</ul>
      <button className="dsh-crate-button" disabled={busy} onClick={() => void execute()}>{busy ? t('working') : t('incrementalExecute')}</button>
    </> : null}
  </div>
}
