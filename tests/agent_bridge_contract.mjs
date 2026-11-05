import assert from 'node:assert/strict'
import { createAgentBridge } from '../src/client/agent-bridge.ts'

let activate, dispose, reads = 0, sends = 0
const root = {
  get sessions() { throw Error('cannot get property "sessions" without inject') },
  inject(names, callback) { assert.deepEqual(names, ['sessions']); activate = callback },
}
const bridge = createAgentBridge(root, () => 'unavailable')
assert.equal(bridge.getAgentTarget(), undefined)
await assert.rejects(bridge.forwardToAgent('diagnostic', 'a'), /unavailable/)
let current = 'a'
activate({
  effect(callback) { dispose = callback() },
  sessions: {
    list: { getSnapshot() { reads++; return { current, byId: { a: { title: 'A' } } } } },
    scope(id) { return id === 'a' ? { id } : undefined },
    sessionOf() { return { async prompt(parts, mode) { sends++; assert.equal(mode, 'queue'); return { ok: true } } } },
  },
})
assert.deepEqual(bridge.getAgentTarget(), { id: 'a', title: 'A' })
assert.equal(sends, 0, 'reading diagnostic target must never send')
current = 'b'
await assert.rejects(bridge.forwardToAgent('diagnostic', 'a'), /unavailable/)
current = 'a'
await bridge.forwardToAgent('diagnostic', 'a')
assert.equal(sends, 1)
dispose()
assert.equal(bridge.getAgentTarget(), undefined)
await assert.rejects(bridge.forwardToAgent('diagnostic', 'a'), /unavailable/)
assert(reads > 0)
console.log('PASS: strict injection, missing service, target lock, disposal, no implicit send')
