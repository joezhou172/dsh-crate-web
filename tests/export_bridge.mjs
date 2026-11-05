import assert from 'node:assert/strict'
import http from 'node:http'
import {createHash} from 'node:crypto'
import {mkdir,mkdtemp,readFile,writeFile,readdir} from 'node:fs/promises'
import {join,resolve} from 'node:path'
import {pathToFileURL} from 'node:url'
const root=resolve(process.argv[2])
const home=await mkdtemp(join(root,'work','export-bridge-'))
process.env.DSH_HOME=home
process.env.DSH_PACK_CLI='C:/Python314/python.exe'
process.env.DSH_PACK_CLI_PREFIX=JSON.stringify(['-B','-m','dsh_pack'])
process.env.PYTHONPATH=join(root,'core')
const profile=join(home,'profiles','sample'),pkg=join(profile,'node_modules','fixture-plugin')
await mkdir(pkg,{recursive:true})
const manifest=JSON.stringify({name:'sample',dependencies:{'fixture-plugin':'1.0.0'}})
await writeFile(join(profile,'package.json'),manifest)
await writeFile(join(pkg,'package.json'),JSON.stringify({name:'fixture-plugin',version:'1.0.0'}))
await writeFile(join(pkg,'index.js'),'export default {}')
const handlers=new Map()
const {apply}=await import(pathToFileURL(resolve(process.argv[3])).href)
apply({effect:fn=>fn(),connection:{requestRejection:()=>undefined},webServer:{register:route=>{handlers.set(route.path,route.handler);return ()=>{}}}})
const server=http.createServer((req,res)=>handlers.get(req.url.split('?')[0])?.(req,res))
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve))
const url='http://127.0.0.1:'+server.address().port
const api=async(action,body={})=>(await fetch(url+'/dsh-crate/api',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({action,...body})})).json()
const row={name:'fixture-plugin',included:true,selection:{kind:'installed'},artifactMode:'embedded',activateOnImport:false}
const draft={requestVersion:2,profileName:'sample',preset:'custom',dataSelection:[],requiredSecrets:[],compression:'fast',plugins:[row]}
const checks={}
try{
 const catalog=await api('export-catalog',{profileName:'sample'})
 assert.equal(catalog.result.requestVersion,2)
 assert.equal(catalog.result.plugins[0].name,'fixture-plugin')
 const preview=await api('export-plan',draft)
 assert.equal(preview.status,'ok',JSON.stringify(preview))
 assert.ok(preview.result.planId)
 const frozen=await readFile(join(home,'.dsh-pack','ui-work','export-plan-'+preview.result.planId+'.dshcrate'))
 const bad=await api('export',{...draft,compression:'compact',planId:preview.result.planId})
 assert.equal(bad.status,'failed')
 const exported=await api('export',{...draft,planId:preview.result.planId})
 assert.equal(exported.status,'ok',JSON.stringify(exported))
 const download=Buffer.from(await (await fetch(url+'/dsh-crate/download?name='+exported.downloadName)).arrayBuffer())
 assert.deepEqual(download,frozen)
 assert.equal(download.length,preview.result.sizePreview.archiveBytes)
 assert.equal((await api('export',{...draft,planId:preview.result.planId})).status,'failed')
 checks.frozenBytesDraftBindingSingleUse='PASS'
 const reference={...draft,plugins:[{...row,artifactMode:'reference-only'}]}
 const refPlan=await api('export-plan',reference)
 assert.equal(refPlan.status,'ok',JSON.stringify(refPlan))
 assert.equal((await api('export',{...reference,planId:refPlan.result.planId})).status,'failed')
 assert.equal((await api('export',{...reference,planId:refPlan.result.planId,confirmReferences:true})).status,'ok')
 checks.serverReferenceConfirmation='PASS'
 const selected={...draft,compression:'compact',plugins:[{...row,included:false},{name:'dsh-message-edit',included:true,selection:{kind:'registry',version:'0.2.3'},artifactMode:'embedded',activateOnImport:false}]}
 const plan=await api('export-plan',selected)
 assert.equal(plan.status,'ok',JSON.stringify(plan))
 assert.deepEqual(plan.result.plugins.map(p=>p.name),['dsh-message-edit'])
 const final=await api('export',{...selected,planId:plan.result.planId})
 assert.equal(final.status,'ok',JSON.stringify(final))
 assert.equal(await readFile(join(profile,'package.json'),'utf8'),manifest)
 assert.deepEqual(await readdir(join(profile,'node_modules')),['fixture-plugin'])
 checks.liveRegistryExportWithoutSourceInstall='PASS'
 const legacy=await api('export',{profileName:'sample',embed:['fixture-plugin']})
 assert.equal(legacy.status,'ok',JSON.stringify(legacy))
 checks.legacyAPI='PASS'
 await writeFile(join(root,'work','export-bridge-report.json'),JSON.stringify({status:'PASS',checks,home,remotePack:join(home,'.dsh-pack','exports',final.downloadName),snapshotBytes:download.length,sha256:createHash('sha256').update(download).digest('hex')},null,2))
 console.log(JSON.stringify({status:'PASS',checks}))
}finally{server.closeAllConnections();await new Promise(resolve=>server.close(resolve))}
