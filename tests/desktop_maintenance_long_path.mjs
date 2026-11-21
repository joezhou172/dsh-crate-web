import assert from 'node:assert/strict'
import { mkdtempSync, mkdirSync, cpSync, writeFileSync, readFileSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { randomUUID } from 'node:crypto'
import { DesktopMaintenance } from '../desktop-maintenance.mjs'

if (process.platform !== 'win32') {
  console.log(JSON.stringify({status:'UNTESTED',reason:'Windows-only native loader regression'}))
} else {
  const repo=resolve(import.meta.dirname,'..')
  const root=mkdtempSync(join(repo,'work/maintenance-long-path-'))
  const home=join(root,'isolated-environment-with-a-deliberately-long-path','additional-component-for-native-library-path-validation','nested-home')
  const id=randomUUID(),dir=join(home,'.dsh-pack/maintenance',id),runner=join(dir,'runner')
  mkdirSync(runner,{recursive:true})
  cpSync(join(repo,'runtime/python'),join(runner,'runtime/python'),{recursive:true})
  cpSync(join(repo,'core'),join(runner,'core'),{recursive:true})
  const command=join(runner,'runtime/python/python.exe')
  assert.ok(command.length>260)
  const target=join(home,'profiles/desktop');mkdirSync(target,{recursive:true})
  writeFileSync(join(target,'package.json'),'{}')
  writeFileSync(join(dir,'job.json'),JSON.stringify({id,home,target:'desktop',args:[],env:{},command}))
  const maintenance=new DesktopMaintenance({home},{})
  const job=maintenance.job(id)
  await maintenance.invoke(job,true)
  assert.equal(maintenance.result(job).status,'restored')
  maintenance.invoke(job,true,true)
  assert.equal(maintenance.result(job).status,'restored')
  assert.equal(readFileSync(join(target,'package.json'),'utf8'),'{}')
  console.log(JSON.stringify({status:'PASS',commandLength:command.length,asyncWorker:'PASS',syncRecovery:'PASS',targetUnchanged:true,scope:'Actual embedded Python and native modules in deep path; no import mutation'}))
}
