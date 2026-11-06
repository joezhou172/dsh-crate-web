import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
const version = process.env.RELEASE_VERSION
const expected = process.env.EXPECTED_SHA256
assert(/^\d+\.\d+\.\d+-preview\.\d+$/.test(version))
assert(/^[a-f0-9]{64}$/.test(expected))
for (let attempt = 0; attempt < 30; attempt++) {
  const response = await fetch(`https://registry.npmjs.org/dsh-crate-web/${version}?check=${Date.now()}`)
  if (response.status === 404) { await new Promise(r => setTimeout(r, 10000)); continue }
  assert(response.ok, `注册表查询失败：${response.status}`)
  const pkg = await response.json()
  const url = new URL(pkg.dist.tarball)
  assert.equal(url.origin, 'https://registry.npmjs.org')
  const download = await fetch(url)
  assert(download.ok)
  const actual = createHash('sha256').update(Buffer.from(await download.arrayBuffer())).digest('hex')
  assert.equal(actual, expected, 'npm 下载内容与发布前验收包不同')
  console.log(JSON.stringify({ status: 'PASS', version, sha256: actual }))
  process.exit(0)
}
throw new Error('注册表尚未出现该版本；不能宣称下载验证通过')
