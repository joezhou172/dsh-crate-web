import { spawnSync } from 'node:child_process'
import assert from 'node:assert/strict'
import { join } from 'node:path'
const runtime = process.argv[2]
if (!runtime) throw Error('Pass an existing DSH runtime directory')
function merge(target, source, mode = 'update') {
  return spawnSync(process.execPath, [join(import.meta.dirname, '../merge-config.mjs'), runtime], {
    env: { ...process.env, ELECTRON_RUN_AS_NODE: '1' }, encoding: 'utf8', input: JSON.stringify({ target, source, mode })
  })
}
const before = '- id: one\n  value: 1\n  keep: true\n'
const after = '- id: one\n  value: 2\n- id: two\n  value: null\n'
for (const mode of ['add', 'update']) {
  const result = merge(before, after, mode)
  assert.equal(result.status, 0, result.stderr)
  const text = JSON.parse(result.stdout).content
  assert.match(text, new RegExp(`value: ${mode === 'add' ? 1 : 2}`))
  assert.match(text, /keep: true/); assert.match(text, /id: two/)
}
assert.notEqual(merge(before, '- id: one\n- id: one\n').status, 0)
assert.notEqual(merge('a: &x 1\nb: *x\n', 'b: 2\n').status, 0)
assert.notEqual(merge('a: 1\na: 2\n', 'b: 2\n').status, 0)
assert.equal(merge('a: !!js process.exit(99)\n', 'b: null\n').status, 0)
console.log(JSON.stringify({ yamlModes: 'PASS', duplicateIds: 'PASS', aliasesBlocked: 'PASS', duplicateKeys: 'PASS', inertJsTag: 'PASS' }))
