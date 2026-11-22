import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import test from 'node:test'
import { verifyPublishedRelease } from '../scripts/verify-published-release.mjs'

const version = '0.1.2-preview.24'
const bytes = Buffer.from('fixture archive')
const expected = createHash('sha256').update(bytes).digest('hex')
const metadata = () => Response.json({ dist: { tarball: 'https://registry.npmjs.org/dsh-crate-web/-/fixture.tgz' } })

function registry(responses) {
  const urls = []
  let time = 1
  return {
    urls,
    options: {
      now: () => time,
      sleep: async ms => { time += ms },
      log: () => {},
      fetch: async (url, init) => {
        assert.equal(init.redirect, 'error')
        urls.push(new URL(url))
        const value = responses.shift()
        assert.ok(value, 'unexpected request')
        if (value instanceof Error) throw value
        return value
      },
    },
  }
}

test('版本可见但 tgz 暂不可下载时，重新获取并核对实际字节', async () => {
  const registryMock = registry([
    new Response(null, { status: 404 }),
    metadata(), new Response(null, { status: 404 }),
    metadata(), new Response(null, { status: 503 }),
    metadata(), new Response(bytes),
  ])
  const report = await verifyPublishedRelease(version, expected, registryMock.options)
  assert.equal(report.sha256, expected)
  const downloads = registryMock.urls.filter(url => url.pathname.endsWith('.tgz'))
  assert.equal(downloads.length, 3)
  assert.equal(new Set(downloads.map(url => url.search)).size, 3)
})

test('超时可重试；超过期限报告最后失败的阶段和状态码', async () => {
  const { options } = registry([new DOMException('timeout', 'TimeoutError'), metadata(), new Response(null, { status: 429 })])
  await assert.rejects(verifyPublishedRelease(version, expected, { ...options, timeoutMs: 20000 }), /tgz.*HTTP 429/)
})

test('凭据错误、非法下载地址和内容哈希不符立即停止', async () => {
  for (const [responses, message] of [
    [[metadata(), new Response(null, { status: 403 })], /tgz.*HTTP 403/],
    [[Response.json({ dist: { tarball: 'https://example.net/file' } })], /地址/],
    [[metadata(), new Response('different bytes')], /SHA-256/],
  ]) {
    const { options } = registry(responses)
    await assert.rejects(verifyPublishedRelease(version, expected, options), message)
  }
})
