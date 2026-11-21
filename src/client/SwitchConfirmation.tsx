import { useEffect, useRef, useState } from 'react'
import type { DshCrateLocaleKey } from './locales.ts'

export function SwitchConfirmation({ target, imported, partial, available, desktop, restartDesktop = false, replace = false, onCancel, onConfirm, t }: {
  target: string; imported: boolean; partial: boolean; available: boolean; desktop: boolean
  restartDesktop?: boolean; replace?: boolean
  onCancel: () => void; onConfirm: (makeDefault: boolean) => void; t: (key: DshCrateLocaleKey) => string
}) {
  const dialog = useRef<HTMLDivElement>(null)
  const [makeDefault, setMakeDefault] = useState(false)
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null
    dialog.current?.querySelector<HTMLButtonElement>('button')?.focus()
    return () => { if (previous?.isConnected) previous.focus() }
  }, [])
  return <div className="dsh-crate-modal-backdrop" role="presentation">
    <div ref={dialog} className="dsh-crate-modal" role="dialog" aria-modal="true" aria-labelledby="crate-switch-title" data-field="switchConfirmation" onKeyDown={event => {
      if (event.key === 'Escape') { event.preventDefault(); onCancel() }
      if (event.key === 'Tab') {
        const buttons = [...(dialog.current?.querySelectorAll<HTMLElement>('button:not(:disabled),input:not(:disabled)') ?? [])]
        const next = event.shiftKey ? buttons.at(-1) : buttons[0]
        if (document.activeElement === (event.shiftKey ? buttons[0] : buttons.at(-1))) { event.preventDefault(); next?.focus() }
      }
    }}>
      <h3 id="crate-switch-title">{t(replace ? 'replaceDesktop' : restartDesktop ? 'restartDesktop' : desktop ? imported ? 'importOpenQuestion' : 'openQuestion' : imported ? 'importSwitchQuestion' : 'switchQuestion')}</h3>
      <p><strong>{target}</strong></p>
      {partial ? <p role="status">{t('partialSwitchWarning')}</p> : null}
      <p>{t(replace ? 'replaceDesktopHint' : restartDesktop ? 'restartDesktopHint' : desktop && available ? 'openEnvironmentHint' : available ? 'switchProfileWarning' : desktop ? 'desktopSwitchUnavailable' : 'switchUnavailable')}</p>
      {restartDesktop ? <label><input type="checkbox" checked={makeDefault} onChange={event => setMakeDefault(event.target.checked)} /> {t('defaultOnNextLaunch')}</label> : null}
      <div className="dsh-crate-modal-actions">
        <button type="button" className="dsh-crate-secondary" onClick={onCancel}>{t('stayCurrent')}</button>
        <button type="button" className="dsh-crate-button" disabled={!available} onClick={() => onConfirm(makeDefault)}>{t(replace ? 'snapshotReplaceRestart' : restartDesktop ? 'restartDesktop' : desktop ? 'openEnvironment' : 'switchNow')}</button>
      </div>
    </div>
  </div>
}
