import assert from 'node:assert/strict'
import { readApiResponse } from '../src/client/api-response.ts'
for (const [body,status,code] of [['',200,'API_EMPTY_RESPONSE'],['',403,'API_ACCESS_REJECTED'],['',401,'API_ACCESS_REJECTED'],['',503,'API_SERVICE_UNAVAILABLE'],['{"status":',200,'API_INVALID_RESPONSE'],['<html>private-token</html>',502,'API_INVALID_RESPONSE'],['null',200,'API_INVALID_RESPONSE'],['[]',200,'API_INVALID_RESPONSE']]) {
  const value=await readApiResponse(new Response(body,{status}),'import')
  assert.equal(value.status,'failed');assert.equal(value.error.code,code)
  assert.equal(value.error.details.action,'import');assert.equal(value.error.details.httpStatus,status)
  assert.ok(!JSON.stringify(value).includes('private-token'))
}
for (const value of [{status:'ok',result:{status:'prepared'}},{status:'failed',error:{code:'ORIGINAL_ERROR',message:'preserve',details:{stage:'install'}}}]) {
 assert.deepEqual(await readApiResponse(new Response(JSON.stringify(value),{status:value.status==='ok'?200:400}),'inspect'),value)
}
const broken=new Response(new ReadableStream({start(controller){controller.error(new Error('connection interrupted'))}}))
assert.equal((await readApiResponse(broken,'import')).error.code,'API_RESPONSE_INTERRUPTED')
console.log('PASS: empty/rejected/unavailable/truncated/non-object/interrupted responses; valid reports preserved; response bodies not leaked')
