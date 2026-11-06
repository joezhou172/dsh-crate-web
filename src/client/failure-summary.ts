import type { DshCrateLocaleKey } from './locales.ts'
type Row = Record<string, unknown>
const object = (v: unknown): v is Row => !!v && typeof v === 'object' && !Array.isArray(v)
const rows = (v: unknown): Row[] => Array.isArray(v) ? v.filter(object) : []
const short = (v: unknown): string => typeof v === 'string' ? v.split(/\r?\n/)[0]!.slice(0, 180) : ''

/** Summaries never replace or mutate the full diagnostic supplied to Details. */
export function failureSummaries(value: Row, t: (key: DshCrateLocaleKey) => string) {
  const result = object(value.result) ? value.result : value
  const error = object(result.error) ? result.error : object(value.error) ? value.error : undefined
  const details = error && object(error.details) ? error.details : {}
  const findings = [...rows(result.findings), ...rows(details.findings)]
    .filter(row => row.severity === 'BLOCKER' || row.status === 'FAIL')
  const candidates = findings.length ? findings : error ? [error]
    : value.status === 'failed' || result.canContinue === false ? [result] : []
  const seen = new Set<string>()
  return candidates.flatMap(item => {
    const code = String(item.code ?? '')
    let title = short(item.message) || t('failureSummary')
    let next = t('failureDetailsHint')
    if (code === 'ENVIRONMENT_VERSION_MISMATCH' || code === 'PLUGIN_VERSION_MISMATCH') {
      const evidence = object(item.evidence) ? item.evidence : {}
      title = `${t('versionMismatch')} · ${short(item.item) || 'DSH/Node'}: ${t('packRequires')} ${short(item.expected) || short(evidence.required) || '?'} / ${t('currentVersion')} ${short(item.observed) || short(evidence.current) || '?'}`
      next = t('versionMismatchNext')
    } else if (code === 'REQUIRED_ARTIFACT_MISSING' || code === 'PLUGIN_MISSING') {
      title = `${t('missingArtifactSummary')}${short(item.item) ? ` · ${short(item.item)}` : ''}`
      next = t('missingArtifactNext')
    } else if (['HASH_OR_INTEGRITY_ERROR', 'HASH_MISMATCH', 'INTEGRITY_FILE_MISSING', 'INTEGRITY_FILE_SET_MISMATCH'].includes(code)) {
      title = t('integritySummary'); next = t('integrityNext')
    } else if (code === 'PROFILE_EXISTS') {
      title = t('profileNameExists'); next = t('profileExistsNext')
    } else if (code === 'SECRET_MISSING') {
      title = t('missingSecretSummary'); next = t('missingSecretNext')
    }
    if (seen.has(title)) return []
    seen.add(title)
    return [{ title, next }]
  }).slice(0, 3)
}
