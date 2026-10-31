// 只发布已经通过检查的 tgz；绝不隐式重新打包或覆盖已发布版本。
import { createHash } from 'node:crypto'
import { readFile } from 'node:fs/promises'
import { join, basename, resolve } from 'node:path'
import { pathToFileURL } from 'node:url'
import { spawnSync } from 'node:child_process'

export function publicationDecision(status, remoteIntegrity, localIntegrity) {
  if (status === 404) return 'publish'
  if (status !== 200) throw new Error(`npm registry 查询失败：HTTP ${status}；停止发布`)
  if (remoteIntegrity !== localIntegrity) throw new Error('此版本已经存在且制品不同；必须升版，禁止覆盖')
  return 'skip'
}

export function publishArguments(tarball) {
  return ['publish', resolve(tarball), '--ignore-scripts', '--access', 'public', '--tag', 'preview', '--registry=https://registry.npmjs.org', '--fetch-retries=0']
}

export function validateAudit(audit, expectedSha256, actualSha256) {
  if (audit.status !== 'PASS' || audit.package !== 'dsh-crate-web'
      || !/^\d+\.\d+\.\d+-[0-9A-Za-z.-]+$/.test(audit.version)
      || !audit.filename || basename(audit.filename) !== audit.filename
      || !/^[a-f0-9]{64}$/.test(expectedSha256 || '')
      || audit.sha256 !== expectedSha256 || actualSha256 !== expectedSha256) {
    throw new Error('发布制品身份或 SHA-256 不符')
  }
}

async function main() {
  const dir = process.argv[2]
  if (!dir) throw new Error('缺少检查制品目录')
  const audit = JSON.parse(await readFile(join(dir, 'audit.json'), 'utf8'))
  if (!audit.filename || basename(audit.filename) !== audit.filename) throw new Error('非法制品路径')
  const tarball = join(dir, audit.filename)
  const data = await readFile(tarball)
  validateAudit(audit, process.env.EXPECTED_SHA256, createHash('sha256').update(data).digest('hex'))
  const integrity = 'sha512-' + createHash('sha512').update(data).digest('base64')
  const url = `https://registry.npmjs.org/${encodeURIComponent(audit.package)}/${encodeURIComponent(audit.version)}`
  const response = await fetch(url, { signal: AbortSignal.timeout(30000), redirect: 'error' })
  const remote = response.status === 200 ? await response.json() : null
  const decision = publicationDecision(response.status, remote?.dist?.integrity, integrity)
  if (decision === 'skip') {
    console.log('相同版本及相同制品已存在，无需重复发布；不更改 dist-tag。')
    return
  }
  const args = publishArguments(tarball)
  const result = spawnSync('npm', args, { stdio: 'inherit', shell: false })
  if (result.error) throw result.error
  if (result.status !== 0) throw new Error('npm 发布失败：请核对包的 Trusted Publisher / 组织发布权限，不要把 token 写入仓库')
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch(error => { console.error(error.message); process.exitCode = 1 })
}
