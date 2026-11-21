import assert from 'node:assert/strict'
import { failureSummaries } from '../src/client/failure-summary.ts'
import { zh, en } from '../src/client/locales.ts'

const finding = { code: 'ENVIRONMENT_VERSION_MISMATCH', severity: 'BLOCKER', item: 'dsh', expected: '0.2.1-rc.5', observed: '0.2.2-rc.1' }
for (const locale of [zh, en]) {
  const t = key => locale[key]
  const payload = { status: 'ok', result: { canContinue: false, findings: [finding], error: { details: { findings: [finding] } } } }
  const before = JSON.stringify(payload)
  const summaries = failureSummaries(payload, t)
  assert.equal(summaries.length, 1)
  assert.match(summaries[0].title, /0.2.1-rc.5.*0.2.2-rc.1/)
  assert.equal(summaries[0].next, t('versionMismatchNext'))
  assert.equal(failureSummaries({ error: { details: { findings: [finding] } } }, t)[0].title, summaries[0].title)
  assert.equal(JSON.stringify(payload), before)
  for (const [code, key] of [['REQUIRED_ARTIFACT_MISSING', 'missingArtifactSummary'], ['HASH_MISMATCH', 'integritySummary'], ['PROFILE_EXISTS', 'profileNameExists'], ['SECRET_MISSING', 'missingSecretSummary']]) {
    assert.equal(failureSummaries({ error: { code } }, t)[0].title, t(key))
  }
  assert.deepEqual(failureSummaries({ status: 'ok', result: { canContinue: true } }, t), [])
  const message = 'Readable failure\n' + 'trace'.repeat(10000)
  assert.equal(failureSummaries({ status: 'failed', message }, t)[0].title, 'Readable failure')
}
console.log('PASS: Chinese/English reasons, nested blockers, deduplication, actions, bounded summary, original diagnostic retained')
