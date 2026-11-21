import { useRef, useState } from 'react'
import type { DshCrateLocaleKey } from './locales.ts'
type Json = Record<string, any>
export function ImportVersionChoices({ problems, prepared, t, query, apply, clear, onError }: {
  problems: { name: string; reason: string }[]; prepared?: Json;
  t: (key: DshCrateLocaleKey) => string; query: (name: string, version?: string) => Promise<Json>;
  apply: (choices: Json[]) => Promise<void>; clear: () => void; onError: (value: Json) => void;
}) {
  const [candidates, setCandidates] = useState<Record<string, Json[]>>({})
  const [selected, setSelected] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState('')
  const revision = useRef(0)
  const lookup = async (name: string) => {
    const rev = ++revision.current; setLoading(name)
    try {
      const value = await query(name)
      if (rev !== revision.current) return
      if (value.status === 'failed') { onError(value); return }
      setCandidates(current => ({ ...current, [name]: (value.result?.candidates ?? []).slice().reverse() }))
    } catch (error) { onError({ status: 'failed', error: { message: String(error) } }) }
    finally { if (rev === revision.current) setLoading('') }
  }
  const choices = Object.entries(selected).filter(([, v]) => v).map(([name, version]) =>
    version === 'skip' ? { name, action: 'skip' } : { name, action: 'replace', version })
  const select = async (name: string, version: string) => {
    setSelected(current => ({ ...current, [name]: version }))
    if (!version || version === 'skip') return
    const rev = ++revision.current; setLoading(name)
    try {
      const value = await query(name, version)
      if (rev !== revision.current) return
      if (value.status === 'failed') { onError(value); return }
      const detail = value.result?.candidates?.find((row: Json) => row.version === version)
      if (detail) setCandidates(current => ({ ...current, [name]: (current[name] ?? []).map(row => row.version === version ? detail : row) }))
    } catch (error) { onError({ status: 'failed', error: { message: String(error) } }) }
    finally { if (rev === revision.current) setLoading('') }
  }
  const ready = choices.every(choice => choice.action === 'skip' || candidates[choice.name]?.some(row => row.version === choice.version && !row.metadataPending && !row.deprecated))
  if (!problems.length && !prepared) return null
  return <section className="dsh-crate-preview" data-field="importVersionChoices">
    <strong>{t('importVersionTitle')}</strong>
    <p>{t('importVersionHint')}</p>
    {prepared ? <>
      <ul>{(prepared.choices ?? []).map((row: Json) => <li key={row.name}>{row.name} · {row.from} → {row.action === 'skip' ? t('importVersionSkip') : row.to}</li>)}</ul>
      <p>{t('importVersionPrepared')}</p>
      <button className="dsh-crate-secondary" onClick={clear}>{t('importVersionReset')}</button>
    </> : <>
      {problems.map(problem => <div key={problem.name} className="dsh-crate-form">
        <label className="dsh-crate-label">{problem.name}<select className="dsh-crate-select" disabled={!!loading} aria-label={`${t('chooseVersion')} ${problem.name}`} value={selected[problem.name] ?? ''}
          onChange={event => void select(problem.name, event.target.value)}>
          <option value="">{t('importVersionOriginal')}</option><option value="skip">{t('importVersionSkip')}</option>
          {(candidates[problem.name] ?? []).map(row => <option key={row.version} value={row.version} disabled={!!row.deprecated}>
            {row.version} · {row.deprecated ? t('importVersionDeprecated') : t('importVersionUnknown')}
          </option>)}
        </select></label>
        <button className="dsh-crate-secondary" disabled={!!loading} onClick={() => void lookup(problem.name)}>{loading === problem.name ? t('working') : t('importVersionLookup')}</button>
        {selected[problem.name] && selected[problem.name] !== 'skip' ? <button className="dsh-crate-secondary" onClick={() => onError({
          ...candidates[problem.name]?.find(row => row.version === selected[problem.name]), message: t('versionUntested'),
        })}>{t('viewDetails')}</button> : null}
      </div>)}
      <button className="dsh-crate-button" disabled={!choices.length || !!loading || !ready} onClick={() => void apply(choices)}>{t('importVersionPrepare')}</button>
    </>}
  </section>
}
