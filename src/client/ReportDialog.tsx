import { CrateIcon } from './CrateIcon.tsx'
import { createContext, useContext, useEffect, useRef, useState } from 'react'
import type { DshCrateLocaleKey } from './locales.ts'

type T = (key: DshCrateLocaleKey) => string
export interface AgentTarget { id: string; title: string }
export interface AgentBridge {
  getAgentTarget: () => AgentTarget | undefined
  forwardToAgent: (text: string, targetId: string) => Promise<void>
}
export const ReportContext = createContext<(value: unknown) => void>(() => {})

export function DetailsButton({ value, t }: { value: unknown; t: T }) {
  const open = useContext(ReportContext)
  return <button className="dsh-crate-secondary" type="button" onClick={() => open(value)}>{t('viewDetails')}</button>
}

export function ReportDialog({ value, t, bridge, onClose }: {
  value: unknown; t: T; bridge?: AgentBridge; onClose: () => void
}) {
  const dialog = useRef<HTMLDialogElement>(null)
  const closeButton = useRef<HTMLButtonElement>(null)
  const sending = useRef(false)
  const [busy, setBusy] = useState(false)
  const [sent, setSent] = useState(false)
  const [feedback, setFeedback] = useState<DshCrateLocaleKey>()
  const [sendError, setSendError] = useState('')
  const [target] = useState(() => {
    // Optional forwarding must never prevent viewing/copying the diagnostic.
    try { return bridge?.getAgentTarget() } catch { return undefined }
  })
  const failed = typeof value === 'object' && value !== null && ('status' in value) && ['failed', 'FAIL'].includes(String(value.status))
  const record = value !== null && typeof value === 'object' ? value as Record<string, unknown> : {}
  const diagnostic = record.error !== null && typeof record.error === 'object' ? record.error as Record<string, unknown> : record
  const summary = typeof diagnostic.message === 'string' ? diagnostic.message.split(/\r?\n/)[0] : ''
  const stage = typeof diagnostic.stage === 'string' ? diagnostic.stage : ''
  const text = typeof value === 'string' ? value : JSON.stringify(value, null, 2)
  useEffect(() => {
    if (!busy && (sent || sendError)) closeButton.current?.focus()
  }, [busy, sent, sendError])
  useEffect(() => {
    const previous = document.activeElement === document.body
      ? document.querySelector('.dsh-crate-tab[data-active=true]')
      : document.activeElement
    const element = dialog.current!
    element.showModal()
    // 捕获 Escape，避免外层 DSH 设置弹窗先处理同一按键。
    const escape = (event: KeyboardEvent) => {
      if (event.key === 'Tab') {
        const stops = Array.from(element.querySelectorAll<HTMLElement>('button:not(:disabled), [tabindex="0"], summary'))
          .filter(node => node.getClientRects().length > 0)
        const first = stops[0], last = stops[stops.length - 1]
        if (first && last && (!element.contains(document.activeElement) ||
          (event.shiftKey ? document.activeElement === first : document.activeElement === last))) {
          event.preventDefault()
          ;(event.shiftKey ? last : first).focus()
        }
        return
      }
      if (event.key !== 'Escape') return
      event.preventDefault(); event.stopImmediatePropagation()
      if (!sending.current) onClose()
    }
    document.addEventListener('keydown', escape, true)
    return () => {
      document.removeEventListener('keydown', escape, true)
      element.close()
      if (previous instanceof HTMLElement && previous.isConnected) previous.focus()
    }
  }, [])
  const copy = async () => {
    try { await navigator.clipboard.writeText(text); setFeedback('diagnosticCopied') }
    catch { setFeedback('copyFailed') }
  }
  const forward = async () => {
    if (!target || !bridge || sending.current || sent) return
    sending.current = true
    setBusy(true); setSendError(''); setFeedback(undefined)
    try {
      await bridge.forwardToAgent(`${t('agentPrompt')}\n\n${text}`, target.id)
      setSent(true); setFeedback('forwarded')
    } catch (error) {
      setFeedback('forwardFailed')
      setSendError(error instanceof Error ? error.message : String(error))
    } finally { sending.current = false; setBusy(false) }
  }
  return <dialog ref={dialog} className="dsh-crate-report-dialog" aria-labelledby="crate-report-title" onCancel={event => { event.preventDefault(); if (!busy) onClose() }}>
    <header><div className="dsh-crate-report-heading">{failed ? <span className="dsh-crate-warning" aria-hidden="true">!</span> : <CrateIcon name="file" />}<h3 id="crate-report-title">{t(failed ? 'reportTitle' : 'reportBody')}</h3></div><button ref={closeButton} type="button" className="dsh-crate-close" aria-label={t('close')} disabled={busy} onClick={onClose}><CrateIcon name="close" /></button></header>
    {failed && summary ? <p className="dsh-crate-error-summary">{summary}</p> : null}
    {failed && stage ? <span className="dsh-crate-stage">{stage}</span> : null}
    <label className="dsh-crate-diagnostic-label" htmlFor="crate-diagnostic-text">{t('reportBody')}</label>
    <pre id="crate-diagnostic-text" tabIndex={0} aria-label={t('fullDiagnostic')}>{text}</pre>
    <div className="dsh-crate-recipient"><CrateIcon name="chat" /><span>{t('agentTarget')}</span><strong>{target ? target.title : t('agentUnavailable')}</strong></div>
    <div className="dsh-crate-dialog-actions">
      <button className="dsh-crate-secondary" type="button" onClick={() => void copy()}><CrateIcon name="copy" />{t('copyDiagnostic')}</button>
      <button className="dsh-crate-button" type="button" disabled={!target || busy || sent} title={t('forwardHint')} onClick={() => void forward()}><CrateIcon name="send" />{busy ? t('forwarding') : sent ? t('forwarded') : t('forwardToAgent')}</button>
    </div>
    {feedback ? <p role="status">{t(feedback)}</p> : null}
    {sendError ? <details><summary>{t('forwardFailureDetails')}</summary><pre>{sendError}</pre></details> : null}
  </dialog>
}
