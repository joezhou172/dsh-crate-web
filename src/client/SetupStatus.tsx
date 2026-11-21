import { useEffect, useState } from 'react'
import { css, isObject, request, type Json } from './DshCratePage.tsx'
import type { DshCrateLocaleKey } from './locales.ts'

export function SetupStatus({ t, onError }: { t: (key: DshCrateLocaleKey) => string; onError: (value: unknown) => void }) {
  const [state, setState] = useState<Json>({}), [busy, setBusy] = useState(false)
  useEffect(() => {
    let stopped = false, timer: ReturnType<typeof setTimeout>
    const poll = async () => {
      try {
        const response = await request('setup-status')
        if (!stopped && response.status === 'ok' && isObject(response.result)) setState(response.result)
        else if (!stopped && response.status === 'failed') setState(value => ({ ...value, desktop: { status: 'failed', error: response.error } }))
      } catch { /* An expected restart temporarily disconnects the page. */ }
      if (!stopped) timer = setTimeout(() => void poll(), 5000)
    }
    void poll(); return () => { stopped = true; clearTimeout(timer) }
  }, [])
  const desktop = isObject(state.desktop) ? state.desktop : {}, update = isObject(state.update) ? state.update : {}, operation = isObject(state.operation) ? state.operation : {}
  const waiting = operation.status === 'waiting-exit' || operation.status === 'applying'
  const label: DshCrateLocaleKey = waiting ? 'setupWaiting' : desktop.status === 'ready' ? 'setupReady' : desktop.status === 'installed' ? 'setupInstalled' : desktop.status === 'unsupported' ? 'setupUnsupported' : desktop.status === 'failed' ? 'setupFailed' : 'setupPreparing'
  const act = async (action: string, data: Json = {}) => {
    setBusy(true)
    try {
      const value = await request(action, data)
      if (value.status !== 'ok') throw value
      const next = await request('setup-status'); if (isObject(next.result)) setState(next.result)
    } catch (error) { onError(error) } finally { setBusy(false) }
  }
  return <details data-field="crateSetup" className={css.inventory}>
    <summary>{t('setupTitle')}{desktop.status === 'ready' ? ` · ${t('setupReady')}` : ''}{update.available ? ` · ${t('stableAvailable')}` : ''}</summary>
    {desktop.status !== 'not-applicable' ? <section aria-label={t('setupDesktop')}>
      <p role="status">{t(label)}</p>
      {desktop.status === 'ready' && !waiting ? <button className="dsh-crate-secondary" disabled={busy} onClick={() => {
        if (window.confirm(t('setupConfirm'))) void act('setup-apply', { confirmRestart: true })
      }}>{t('setupEnable')}</button> : null}
      {desktop.status === 'failed' ? <button className="dsh-crate-secondary" disabled={busy} onClick={() => void act('setup-retry')}>{t('retry')}</button> : null}
      {desktop.error ? <button className="dsh-crate-secondary" onClick={() => onError(desktop)}>{t('setupDetails')}</button> : null}
      {operation.status === 'failed' ? <p>{t('setupOperationFailed')} <button className="dsh-crate-secondary" onClick={() => onError(operation)}>{t('setupDetails')}</button></p> : null}
    </section> : null}
    <section aria-label={t('stableUpdates')}>
      <p>{t('currentVersion')}: {String(update.current || '—')}{update.preview ? ` · ${t('previewVersion')}` : ''}</p>
      {update.deprecated ? <p>{t('deprecatedVersion')} <button className="dsh-crate-secondary" onClick={() => onError({ status: 'deprecated', message: update.deprecated })}>{t('setupDetails')}</button></p> : null}
      <p role="status">{t(update.status === 'failed' ? 'stableCheckFailed' : update.status !== 'checked' ? 'stableChecking' : update.available ? 'stableAvailable' : 'stableNoUpdate')}{update.available ? ` ${String(update.available)}` : ''}</p>
      <span className={css.muted}>{t('stableOnlyHint')}</span>
      <button className="dsh-crate-secondary" disabled={busy || update.status === 'checking'} onClick={() => void act('update-check')}>{t('stableCheck')}</button>
      {update.available ? <a href="https://www.npmjs.com/package/dsh-crate-web" target="_blank" rel="noreferrer">{t('stableView')}</a> : null}
      {update.error ? <button className="dsh-crate-secondary" onClick={() => onError(update)}>{t('setupDetails')}</button> : null}
    </section>
  </details>
}
