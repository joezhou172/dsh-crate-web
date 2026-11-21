import assert from 'node:assert/strict'
import { crateRequest, requestFailure, requireProfilesResponse, followUpFailure, errorReport, errorDisplay } from '../src/client/request-feedback.mjs'
import { failureSummaries } from '../src/client/failure-summary.ts'
import { en, zh } from '../src/client/locales.ts'
for (const status of [200, 204, 401, 403, 503]) {
  let count = 0
  await assert.rejects(crateRequest('import', {}, async () => { count++; return new Response(null, { status }) }), error => {
    const value = requestFailure(error)
    assert.equal(value.status, 'UNKNOWN'); assert.equal(value.error.httpStatus, status)
    assert.equal(value.error.automaticRetry, false); assert.equal(errorReport(String(error)).status, 'UNKNOWN')
    return true
  })
  assert.equal(count, 1)
}
await assert.rejects(crateRequest('import', { planOnly: true }, async () => new Response(null, { status: 503 })), error => {
  assert.equal(error.diagnostic.writeRequested, false); assert.equal(error.diagnostic.requestKind, 'import-plan')
  assert.equal(requestFailure(error).status, 'failed'); return true
})
for (const text of ['{', 'null', '[]', '<html>private-value</html>']) {
  await assert.rejects(crateRequest('profiles', {}, async () => new Response(text)), error => {
    assert.ok(!JSON.stringify(error.diagnostic).includes('private-value')); return true
  })
}
const server = { status: 'failed', error: { code: 'SERVICE_NOT_READY', evidence: { retained: true } } }
for (const status of [200, 401, 503]) {
  const value = await crateRequest('profiles', {}, async () => new Response(JSON.stringify(server), { status }))
  assert.deepEqual(value.error, server.error)
  assert.throws(() => requireProfilesResponse(value), error => {
    assert.equal(error.diagnostic.serverReport.error.code, 'SERVICE_NOT_READY')
    const feedback = followUpFailure(error); assert.equal(feedback.status, 'DEGRADED')
    assert.equal(errorReport(JSON.stringify(feedback)).status, 'DEGRADED')
    for (const locale of [en, zh]) {
      assert.equal(errorDisplay(JSON.stringify(feedback), k => locale[k]), locale.postImportRefreshFailed)
      assert.equal(failureSummaries(feedback, k => locale[k])[0].title, locale.postImportRefreshFailed)
    }
    return true
  })
}
assert.throws(() => requireProfilesResponse({ status: 'ok' }))
const valid = { status: 'ok', profiles: [], runtime: {}, runtimePlugins: [] }
assert.equal(requireProfilesResponse(valid), valid)
await assert.rejects(crateRequest('profiles', {}, async () => new Response('{"status":"ok"}', { status: 500 })), e => e.diagnostic.code === 'HTTP_ERROR')
await assert.rejects(crateRequest('import', {}, async () => { throw Error('private transport detail') }), e => e.diagnostic.httpStatus === null && !e.message.includes('private transport detail'))
const broken = new Response(new ReadableStream({ start(c) { c.error(new Error('interrupted')) } }))
await assert.rejects(crateRequest('import', {}, async () => broken), e => e.diagnostic.code === 'RESPONSE_READ_FAILED')
console.log('PASS: request helper, unknown write outcomes, read-only planning, preserved server evidence, profile validation and localized summaries')
