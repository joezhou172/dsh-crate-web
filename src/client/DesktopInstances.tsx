import { useEffect, useState } from 'react'
import { css, request, isObject, objects } from './DshCratePage.tsx'
import type { Json } from './DshCratePage.tsx'
import type { DshCrateLocaleKey } from './locales.ts'

export function DesktopInstances({ t, sources, onMode, onError }: {
  t: (key: DshCrateLocaleKey) => string; sources: string[];
  onMode: (mode: 'single' | 'multi') => void; onError: (value: unknown) => void
}) {
  const [mode, setMode] = useState<'single' | 'multi'>('single')
  const [rows, setRows] = useState<Json[]>([])
  const [target, setTarget] = useState('')
  const [busy, setBusy] = useState(false)
  const [loaded, setLoaded] = useState(false)
  const [shareCredentials, setShareCredentials] = useState(false)
  const [shareSkills, setShareSkills] = useState(false)
  const [sharingSupported, setSharingSupported] = useState(false)
  const selected = sources.includes(target) ? target : sources[0] || ''
  const call = async (operation: string, body: Json = {}) => {
    const value = await request('desktop-instances', { operation, ...body })
    if (value.status !== 'ok') throw value
    return isObject(value.result) ? value.result : {}
  }
  const refresh = async () => {
    const result = await call('list')
    setSharingSupported(result.sharingSupported === true)
    setRows(objects(result.instances)); const value = result.mode === 'multi' ? 'multi' : 'single'
    setMode(value); onMode(value); setLoaded(true)
  }
  useEffect(() => { void refresh().catch(onError) }, [])
  const changeMode = async (value: 'single' | 'multi') => {
    setBusy(true)
    try { await call('mode', { mode: value }); await refresh() } catch (error) { onError(error) } finally { setBusy(false) }
  }
  const operate = async (operation: string, body: Json) => {
    if (!window.confirm(t(operation === 'start' && !body.instanceId ? 'desktopCopyConfirm' : operation === 'start' ? 'desktopStartConfirm' : 'desktopStopConfirm'))) return
    setBusy(true)
    try { await call(operation, { ...body, confirmDesktop: true }); await refresh() } catch (error) { onError(error) } finally { setBusy(false) }
  }
  return <section data-field="desktopInstances" className={css.form}>
    <strong>Desktop</strong>
    <label className={css.label}>{t('desktopMode')}<select className={css.select} value={mode} disabled={busy || !loaded} onChange={event => void changeMode(event.target.value as 'single' | 'multi')}>
      <option value="single">{t('desktopSingle')}</option><option value="multi">{t('desktopMulti')}</option>
    </select></label>
    <p className={css.muted}>{t(mode === 'single' ? 'desktopSingleHint' : 'desktopMultiHint')}</p>
    {mode === 'multi' ? <div className="dsh-crate-environment-actions">
      <select aria-label={t('profile')} className={css.select} value={selected} disabled={busy} onChange={event => setTarget(event.target.value)}>{sources.map(name => <option key={name}>{name}</option>)}</select>
      {sharingSupported ? <><label><input type="checkbox" checked={shareCredentials} disabled={busy} onChange={e=>setShareCredentials(e.target.checked)} />{t('shareCredentials')}</label>
      <label><input type="checkbox" checked={shareSkills} disabled={busy} onChange={e=>setShareSkills(e.target.checked)} />{t('shareSkills')}</label>
      <span className={css.muted}>{t('sharingHint')}</span></> : null}
      <button className="dsh-crate-secondary" disabled={busy || !selected} onClick={() => void operate('start', { profileName: selected, shareCredentials, shareSkills })}>{t('desktopNewWindow')}</button>
    </div> : null}
    {rows.map(row => <div className="dsh-crate-environment-row" key={String(row.id)} data-instance={String(row.id)}>
      <div><strong>{String(row.profileName)}</strong><span className={css.muted}> · {t(row.status === 'running' ? 'openedState' : row.status === 'starting' ? 'desktopStarting' : row.status === 'unknown' ? 'statusUnknown' : 'desktopStopped')}{row.current ? ` · ${t('currentRunningProfile')}` : ''}</span></div>
      <div className="dsh-crate-environment-actions">
        {row.status === 'stopped' ? <button className="dsh-crate-secondary" disabled={busy || mode === 'single'} onClick={() => void operate('start', { instanceId: row.id })}>{t('openEnvironment')}</button> : <>
          <button className="dsh-crate-secondary" disabled={busy} onClick={() => void operate('stop', { instanceId: row.id })}>{t('closeEnvironment')}</button>
          <button className="dsh-crate-secondary" disabled={busy} onClick={() => void operate('restart', { instanceId: row.id })}>{t('restartDesktop')}</button>
        </>}
      </div>
    </div>)}
    <button className="dsh-crate-secondary" disabled={busy || !loaded} onClick={() => { setBusy(true); void refresh().catch(onError).finally(() => setBusy(false)) }}>{t('desktopRefresh')}</button>
  </section>
}
