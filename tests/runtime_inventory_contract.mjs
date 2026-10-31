import assert from 'node:assert/strict'
import { Readable } from 'node:stream'
import { join, resolve } from 'node:path'
import { readRuntimeInventory, inspectorApplicability } from '../runtime-inventory.mjs'
const root=resolve(process.argv[2])
const row={id:'workspace-controller',options:{name:'@deepseek-ai/dsh-api-workspace-controller'},fiber:{state:2}}
const inspector={id:'custom-inspector-id',options:{name:'@deepseek-ai/dsh-experimental-inspector'},fiber:{state:3}}
const snapshot=rows=>readRuntimeInventory({loader:{entries:()=>rows}})
assert.equal(inspectorApplicability(snapshot([row]).rows,true).reason,'not-declared')
assert.equal(inspectorApplicability(snapshot([row,inspector]).rows,true).applicable,true)
assert.equal(inspectorApplicability(snapshot([row,{...inspector,disabled:true}]).rows,true).reason,'disabled')
assert.equal(readRuntimeInventory({}).complete,false)
const partial=readRuntimeInventory({loader:{*entries(){yield row;throw Error('private failure value')}}})
assert.equal(partial.rows.length,1);assert.equal(partial.complete,false)
assert.throws(()=>inspectorApplicability(partial.rows,partial.complete),/not confirmed/)
assert.throws(()=>inspectorApplicability([],true),/not confirmed/)
assert.throws(()=>inspectorApplicability(undefined,true),/not confirmed/)
assert.throws(()=>inspectorApplicability([{name:'x'}],true),/not confirmed/)

// Exercise the actual request handler in both TS source and shipped JavaScript.
const modules=[await import('../src/index.ts'),await import('../lib/index.js')]
for (const [index,module] of modules.entries()) {
 for (const broken of [false,true]) {
  process.env.DSH_HOME=join(root,'case-'+index+'-'+broken)
  const handlers=[]
  const ctx={loader:{*entries(){yield row;if(broken)throw Error('private failure value')}},
   connection:{requestRejection:()=>undefined},effect:fn=>fn(),webServer:{register:r=>{handlers.push(r);return ()=>{}}}}
  module.apply(ctx)
  const request=Readable.from([Buffer.from('{"action":"profiles"}')]);request.method='POST';request.headers={}
  let response
  const res={writeHead:code=>assert.equal(code,200),end:raw=>{response=JSON.parse(raw)}}
  await handlers.find(r=>r.path==='/dsh-crate/api').handler(request,res)
  assert.equal(response.runtimeInventoryComplete,!broken)
  assert.equal(response.runtimePlugins.length,1)
  assert.equal(response.runtimePlugins[0].phase,'active')
  assert.equal(JSON.stringify(response).includes('private failure value'),false)
 }
}
console.log(JSON.stringify({status:'PASS',sourceAndShippedHandlers:4,desktopStarts:0,workerStarts:0,modelRequests:0}))
