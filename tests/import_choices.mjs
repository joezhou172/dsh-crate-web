import assert from 'node:assert/strict'
import { mkdtemp, writeFile, readFile, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { randomUUID } from 'node:crypto'
import { selectedPack, sealChoices } from '../src/import-choices.ts'
import { importProblems } from '../src/client/import-problems.ts'
const work = await mkdtemp(join(tmpdir(), 'crate-choices-'))
try {
  const id = randomUUID(), source = join(work, 'original'), prepared = join(work, `import-choice-${id}.dshcrate`)
  await writeFile(source, 'original'); await writeFile(prepared, 'chosen')
  const body = { incremental: 'update', targetProfile: 'existing', compatibilityPolicy: 'compatible', replacementId: id }
  await sealChoices(work, id, source, prepared, body)
  assert.equal(await selectedPack(work, source, body), prepared)
  for (const changed of [{ targetProfile: 'other' }, { incremental: 'add' }, { compatibilityPolicy: 'strict' }, { replacementId: '../outside' }]) {
    await assert.rejects(selectedPack(work, source, { ...body, ...changed }))
  }
  await writeFile(source, 'other'); await assert.rejects(selectedPack(work, source, body))
  await writeFile(source, 'original'); await writeFile(prepared, 'tampered'); await assert.rejects(selectedPack(work, source, body))
  assert.equal(await selectedPack(work, source, {}), source)
  for (const reason of ['NETWORK_INSTALL_FAILED', 'NETWORK_INSTALL_TIMEOUT', 'ENOSPC', 'EACCES', 'HASH_MISMATCH', 'PLUGIN_INSTALL_FAILED']) {
    assert.deepEqual(importProblems({ result: { skippedPlugins: [{ name: 'sample', reason }] } }), [])
  }
  assert.deepEqual(importProblems({ result: { findings: [{ code: 'BUNDLE_PATCH_INVALID', evidence: { plugin: 'sample' } }] } }), [{ name: 'sample', reason: 'BUNDLE_PATCH_INVALID' }])
  assert.deepEqual(importProblems({ result: { skippedPlugins: [{ name: '@deepseek-ai/dsh-base', reason: 'BUNDLE_PATCH_INVALID' }] } }), [])
  console.log('PASS: frozen source/artifact/scope binding and attributable error filtering')
} finally { await rm(work, { recursive: true, force: true }) }
