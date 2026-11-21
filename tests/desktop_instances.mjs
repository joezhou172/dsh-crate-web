import assert from 'node:assert/strict'
import { createServer } from 'node:net'
import { randomUUID } from 'node:crypto'
import { mkdirSync, mkdtempSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { DesktopInstances, instanceRequest } from '../desktop-instances.mjs'
const root=mkdtempSync(join(import.meta.dirname,'../work/desktop-instances-unit-'))
const pipe=process.platform==='win32'?`\\\\.\\pipe\\crate-test-${randomUUID()}`:join(root,'control.sock')
const server=createServer(socket=>{socket.on('data',()=>socket.end())})
await new Promise(resolve=>server.listen(pipe,resolve))
await assert.rejects(instanceRequest({pipe,token:'fixture'}),/without a response/)
await new Promise(resolve=>server.close(resolve))
const manager=new DesktopInstances(root,{},()=>({path:join(root,'source')}))
const id='a'.repeat(24), dir=join(manager.catalog,id)
mkdirSync(dir,{recursive:true})
writeFileSync(join(dir,'instance.json'),JSON.stringify({id,home:join(dir,'home'),profileName:'test'}))
writeFileSync(join(dir,'runtime.json'),JSON.stringify({id,home:join(dir,'home'),pipe,token:'fixture',pid:process.pid}))
assert.equal((await manager.list())[0].status,'unknown')
await assert.rejects(manager.start('test',id),/still present/)
await assert.rejects(manager.control(id,'stop',false),/Confirm/)
writeFileSync(join(dir,'instance.json'),JSON.stringify({id,home:root,profileName:'test'}))
assert.deepEqual(manager.definitions(),[])
mkdirSync(join(root,'source'),{recursive:true});writeFileSync(join(root,'source/lock'),'fixture')
await assert.rejects(manager.start('test'),/source environment is running/)
console.log(JSON.stringify({status:'PASS',scope:'closed IPC response, unreachable live process, duplicate launch guard, close confirmation, identity and running source guards'}))
