import type { DshCrateLocaleKey } from './locales.ts'

type Translate = (key: DshCrateLocaleKey) => string
const bytes = (value: unknown): value is number => typeof value === 'number' && Number.isSafeInteger(value) && value >= 0
function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`
  const unit = Math.min(Math.floor(Math.log2(value) / 10), 4)
  return `${(value / 1024 ** unit).toFixed(1)} ${['B', 'KiB', 'MiB', 'GiB', 'TiB'][unit]}`
}
export function SizePreview({ value, stale, t }: { value: unknown; stale: boolean; t: Translate }) {
  const size = value && typeof value === 'object' ? value as Record<string, unknown> : null
  if (stale) return <p className="dsh-crate-muted" data-field="sizePreview" role="status">{t('sizeStale')}</p>
  if (!size || size.status !== 'measured' || !bytes(size.archiveBytes)) {
    return <p className="dsh-crate-muted" data-field="sizePreview">{t('sizeUnavailable')}</p>
  }
  const entries = Array.isArray(size.largestEntries) ? size.largestEntries.filter((entry): entry is { path: string; compressedBytes: number } =>
    !!entry && typeof entry === 'object' && typeof entry.path === 'string' && bytes(entry.compressedBytes)).slice(0, 5) : []
  return <section className="dsh-crate-preview" data-field="sizePreview" aria-label={t('sizeTitle')}>
    <span>{t('sizeTitle')}</span><strong style={{ fontSize: 24, fontVariantNumeric: 'tabular-nums' }}>{formatBytes(size.archiveBytes)}</strong>
    <p className="dsh-crate-muted">{t(size.finalSizeMayChange === false ? 'sizeFrozen' : 'sizeHint')}</p>
    {typeof size.referenceOnlyCount === 'number' && size.referenceOnlyCount > 0 ? <p className="dsh-crate-muted">{t('sizeReferences')}</p> : null}
    {entries.length ? <details><summary>{t('sizeDetails')}</summary>{entries.map(entry =>
      <div className="dsh-crate-inventory-item" key={entry.path}><span>{entry.path}</span><span style={{ whiteSpace: 'nowrap' }}>{formatBytes(entry.compressedBytes)}</span></div>)}</details> : null}
  </section>
}
