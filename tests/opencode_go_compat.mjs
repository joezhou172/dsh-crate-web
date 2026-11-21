import assert from 'node:assert/strict'
import { installOpenCodeGoCompatibility } from '../src/opencode-go-compat.ts'
let hook
installOpenCodeGoCompatibility({on(event,handler){assert.equal(event,'llm-pi-ai/request-headers');hook=handler}})
let forwarded=0
const next=()=>{forwarded++;return 'continued'}
const h=new Headers({authorization:'Bearer synthetic-test-only'})
assert.equal(hook({provider:'opencode-go',sessionId:'session-fixture'},h,next),'continued')
assert.equal(h.get('x-opencode-session'),'session-fixture')
assert.equal(h.get('authorization'),'Bearer synthetic-test-only')
const explicit=new Headers({'x-opencode-session':'host-provided'})
hook({provider:'opencode-go',sessionId:'other'},explicit,next)
assert.equal(explicit.get('x-opencode-session'),'host-provided')
const untouched=new Headers()
hook({provider:'another-provider',sessionId:'s'},untouched,next)
assert.equal(untouched.has('x-opencode-session'),false)
assert.throws(()=>hook({provider:'opencode-go'},new Headers(),next),/missing the DSH session identity/)
assert.throws(()=>hook({provider:'opencode-go',sessionId:' '},new Headers(),next),/missing the DSH session identity/)
assert.equal(forwarded,3)
console.log(JSON.stringify({status:'PASS',checks:7,scope:'header hook unit regression; real provider test required'}))
