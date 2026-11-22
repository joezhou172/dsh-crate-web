import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { setTimeout as delay } from 'node:timers/promises'
import { pathToFileURL } from 'node:url'

const registry = 'https://registry.npmjs.org'
const transientNetworkCodes = new Set([
  'EAI_AGAIN', 'ECONNRESET', 'ETIMEDOUT', 'UND_ERR_SOCKET',
  'UND_ERR_CONNECT_TIMEOUT', 'UND_ERR_HEADERS_TIMEOUT', 'UND_ERR_BODY_TIMEOUT',
])

class RetryableError extends Error {}

export async function verifyPublishedRelease(version, expected, {
  fetch = globalThis.fetch, now = Date.now, sleep = delay, log = console.warn,
  timeoutMs = 10 * 60 * 1000,
} = {}) {
  assert(/^\d+\.\d+\.\d+-preview\.\d+$/.test(version), 'Preview 版本无效')
  assert(/^[a-f0-9]{64}$/.test(expected), '缺少有效的 SHA-256')
  const deadline = now() + timeoutMs
  let lastError

  async function read(url, stage, decode) {
    url.searchParams.set('check', String(now()))
    const remaining = deadline - now()
    if (remaining <= 0) throw new RetryableError(`${stage} 超时`)
    try {
      const response = await fetch(url, {
        redirect: 'error', signal: AbortSignal.timeout(Math.min(30000, remaining)),
      })
      if (!response.ok) {
        const status = response.status
        await response.body?.cancel()
        const message = `${stage} 返回 HTTP ${status}`
        if ([404, 408, 429, 500, 502, 503, 504].includes(status)) throw new RetryableError(message)
        throw new Error(message)
      }
      return await decode(response)
    } catch (error) {
      if (error.name === 'TimeoutError' || transientNetworkCodes.has(error.cause?.code)) {
        throw new RetryableError(`${stage} 请求失败（${error.cause?.code || error.name}）`, { cause: error })
      }
      throw error
    }
  }

  do {
    try {
      const metadata = await read(new URL('/dsh-crate-web/' + version, registry), '版本元数据', r => r.json())
      const url = new URL(metadata.dist.tarball)
      assert.equal(url.origin, registry, 'tgz 下载地址必须属于 npm 官方注册表')
      const bytes = await read(url, 'tgz 下载', r => r.arrayBuffer())
      const actual = createHash('sha256').update(Buffer.from(bytes)).digest('hex')
      assert.equal(actual, expected, 'npm 下载制品的 SHA-256 与验收包不一致')
      return { status: 'PASS', version, sha256: actual }
    } catch (error) {
      if (!(error instanceof RetryableError)) throw error
      lastError = error
      const waitMs = Math.min(10000, deadline - now())
      if (waitMs <= 0) break
      log(`npm 发布后验证：${error.message}；等待 ${waitMs / 1000} 秒。`)
      await sleep(waitMs)
    }
  } while (now() < deadline)
  throw new Error(`npm 发布后验证超时：${lastError.message}`, { cause: lastError })
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  verifyPublishedRelease(process.env.RELEASE_VERSION, process.env.EXPECTED_SHA256)
    .then(report => console.log(JSON.stringify(report)))
    .catch(error => { console.error(error.message); process.exitCode = 1 })
}
