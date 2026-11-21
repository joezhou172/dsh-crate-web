import assert from 'node:assert/strict'
import { mkdtempSync, mkdirSync, writeFileSync, existsSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { randomUUID } from 'node:crypto'
import { DesktopProfiles } from '../desktop-profile-adapter.mjs'
import { DesktopMaintenance } from '../desktop-maintenance.mjs'
const home=mkdtempSync(join(import.meta.dirname,'../work/maintenance-unit-'))
mkdirSync(join(home,'profiles/desktop'),{recursive:true});writeFileSync(join(home,'profiles/desktop/package.json'),'{}')
const manager=new DesktopProfiles(home);manager.select()
const id=randomUUID(),dir=join(home,'.dsh-pack/maintenance',id);mkdirSync(dir,{recursive:true})
writeFileSync(join(dir,'job.json'),JSON.stringify({id,home,target:'desktop',command:join(dir,'runner/runtime/python/python.exe')}))
let restarts=0
const maintenance=new DesktopMaintenance(manager,{stop:async()=>{throw Error('fixture: normal stop timed out')},restart:()=>restarts++})
assert.throws(()=>maintenance.begin(id,false),/Confirm/)
assert.equal(manager.read().maintenance,undefined)
maintenance.begin(id,true);await maintenance.execute()
assert.equal(manager.read().maintenance,undefined)
assert.equal(manager.read().lastResult.failurePhase,'queued')
assert.equal(restarts,0)
assert.equal(existsSync(join(home,'.dsh-pack/snapshots')),false)
assert.equal(readFileSync(join(home,'profiles/desktop/package.json'),'utf8'),'{}')
maintenance.begin(id,true);const state=manager.read();state.maintenance.phase='executing';manager.write(state)
writeFileSync(join(dir,'worker.json'),JSON.stringify({pid:process.pid,finished:false}))
assert.throws(()=>maintenance.startup(),/仍在运行/)
const failedState=manager.read();failedState.maintenance.phase='booting';manager.write(failedState)
const recovery=new DesktopMaintenance(manager,{stop:async()=>{},restart:()=>restarts++})
recovery.invoke=async()=>{throw Error('fixture: backup file is locked')}
await assert.rejects(recovery.failed('client failed'),/backup file is locked/)
assert.equal(manager.read().lastResult.stage,'rollback')
assert.equal(manager.read().lastResult.restored,false)
assert.equal(manager.read().maintenance.phase,'booting')
assert.equal(restarts,0)
console.log(JSON.stringify({status:'PASS',scope:'cancel, stop failure never snapshots or restarts, active worker prevents concurrent recovery'}))
