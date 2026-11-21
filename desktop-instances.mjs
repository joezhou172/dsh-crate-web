import { createServer, connect } from 'node:net'
import { spawn } from 'node:child_process'
import { createHash, randomBytes, randomUUID } from 'node:crypto'
import { existsSync, mkdirSync, readFileSync, writeFileSync, renameSync, readdirSync, lstatSync, cpSync, openSync, closeSync } from 'node:fs'
import { join, resolve, dirname } from 'node:path'

const sleep = ms => new Promise(r => setTimeout(r, ms))
const alive = pid => { if(!Number.isSafeInteger(pid)||pid<1)return false;try{process.kill(pid,0);return true}catch(error){return error.code!=='ESRCH'} }
function ordinaryParents(path) { for(let p=resolve(path);;p=dirname(p)){if(existsSync(p)&&lstatSync(p).isSymbolicLink())throw Error('Linked Desktop instance paths are not supported');if(dirname(p)===p)break} }
const atomic = (path, value) => { const temp=path+'.'+randomUUID();writeFileSync(temp,JSON.stringify(value,null,2),{flag:'wx',mode:0o600});renameSync(temp,path) }
function plainTree(path) { const stat=lstatSync(path);if(stat.isSymbolicLink())throw Error('Desktop instances require ordinary files; export and import linked environments first');if(stat.isDirectory())for(const name of readdirSync(path))plainTree(join(path,name));else if(!stat.isFile())throw Error('Unsupported instance file') }
export async function instanceRequest(record, action='status', confirm=false) {
 return new Promise((resolveResult,reject)=>{
  const socket=connect(record.pipe);let data='',settled=false;const timer=setTimeout(()=>{socket.destroy();reject(Error('Desktop instance did not respond'))},action==='status'?3000:60000)
  socket.on('connect',()=>socket.write(JSON.stringify({token:record.token,action,confirm})+'\n'))
  socket.on('data',chunk=>{data+=chunk;if(data.length>65536){socket.destroy(Error('Desktop response is too large'));return}if(!data.includes('\n'))return;settled=true;clearTimeout(timer);socket.end();try{const response=JSON.parse(data.split('\n')[0]);if(!response.ok)reject(Error(response.error));else resolveResult(response.result)}catch(e){reject(e)}})
  socket.on('error',error=>{clearTimeout(timer);reject(error)});socket.on('close',()=>{clearTimeout(timer);if(!settled)reject(Error('Desktop control connection closed without a response'))})
 })
}

export class DesktopInstances {
 constructor(home, lifecycle, validateProfile) {
  this.home=resolve(home);this.lifecycle=lifecycle;this.validateProfile=validateProfile
  this.catalog=resolve(process.env.DSH_CRATE_INSTANCE_CATALOG||join(this.home,'.dsh-pack/desktop-instances'))
  ordinaryParents(this.catalog)
  this.running=new Map();this.launching=new Map()
 }
 definitions() {
  ordinaryParents(this.catalog)
  if(!existsSync(this.catalog))return []
  return readdirSync(this.catalog,{withFileTypes:true}).filter(e=>e.isDirectory()&&!e.isSymbolicLink()&&/^[a-f0-9]{24}$/.test(e.name)).flatMap(e=>{
   try { const root=join(this.catalog,e.name);ordinaryParents(join(root,'instance.json'));ordinaryParents(join(root,'home'));const value=JSON.parse(readFileSync(join(root,'instance.json'),'utf8'));if(value.id!==e.name||resolve(value.home)!==resolve(root,'home'))return [];return [{...value,root}] }catch{return []}
  })
 }
 definition(id) { const value=this.definitions().find(x=>x.id===id);if(!value)throw Error('Unknown Desktop instance');return value }
 record(definition) { const file=join(definition.root,'runtime.json');ordinaryParents(file);const r=JSON.parse(readFileSync(file,'utf8'));if(r.id!==definition.id||r.home!==definition.home)throw Error('Desktop instance identity mismatch');return r }
 async list() {
  return Promise.all(this.definitions().map(async d=>{let record;try{record=this.record(d);const s=await instanceRequest(record);return {id:d.id,profileName:d.profileName,status:s.ready?'running':'starting',pid:s.pid,current:s.pid===process.pid}}catch{return {id:d.id,profileName:d.profileName,status:alive(record?.pid)?'unknown':'stopped',current:false}}}))
 }
 async start(profileName, id, sharing={}) {
  if(id)return this.startDefinition(this.definition(id))
  const profile=this.validateProfile(profileName)
  const instanceId=createHash('sha256').update(JSON.stringify([this.home,profileName])).digest('hex').slice(0,24)
  const root=join(this.catalog,instanceId),file=join(root,'instance.json')
  ordinaryParents(file)
  if(!existsSync(file)) {
   if(existsSync(join(profile.path,'lock')))throw Error('The source environment is running. Stop it before creating an independent Desktop copy.')
   plainTree(profile.path);mkdirSync(root,{recursive:true});const home=join(root,'home');mkdirSync(join(home,'profiles'),{recursive:true})
   const dest=join(home,'profiles',profileName);if(existsSync(dest))throw Error('An incomplete instance copy exists; its files were preserved')
   cpSync(profile.path,dest,{recursive:true,errorOnExist:true,force:false})
   // Only the local model credential file is reused, never sessions or live databases.
   const credentials=join(this.home,'.credentials.yaml')
   if(sharing.credentials!==true && existsSync(credentials)&&lstatSync(credentials).isFile()&&!lstatSync(credentials).isSymbolicLink())writeFileSync(join(home,'.credentials.yaml'),readFileSync(credentials),{flag:'wx',mode:0o600})
   if(sharing.skills!==true && existsSync(join(this.home,'skills'))){plainTree(join(this.home,'skills'));cpSync(join(this.home,'skills'),join(home,'skills'),{recursive:true,errorOnExist:true,force:false})}
   const launch=join(home,'.dsh-pack/desktop-launch');mkdirSync(launch,{recursive:true});atomic(join(launch,'state.json'),{schemaVersion:1,defaultProfile:profileName})
   atomic(file,{id:instanceId,profileName,home,sharing:{credentials:sharing.credentials===true,skills:sharing.skills===true,sourceHome:this.home},createdAt:new Date().toISOString()})
  }
  return this.startDefinition(this.definition(instanceId))
 }
 async startDefinition(d) {
  if(this.launching.has(d.id))return this.launching.get(d.id)
  const run=this.launch(d).finally(()=>this.launching.delete(d.id));this.launching.set(d.id,run);return run
 }
 async launch(d) {
  try{const s=await instanceRequest(this.record(d));return {status:'already-running',id:d.id,profileName:d.profileName,pid:s.pid}}catch{}
  let prior;try{prior=this.record(d)}catch{}
  if(alive(prior?.pid))throw Error('The previous Desktop process is still present but cannot be contacted. Inspect it before starting again.')
  const userData=join(d.root,'electron');mkdirSync(userData,{recursive:true})
  ordinaryParents(userData);ordinaryParents(join(d.root,'desktop.log'))
  const log=openSync(join(d.root,'desktop.log'),'a'),env={...process.env,DSH_HOME:d.home,DSH_CRATE_INSTANCE_ID:d.id,DSH_CRATE_INSTANCE_CATALOG:this.catalog}
  env.DSH_CRATE_CREDENTIALS_FILE=join(d.home,'.credentials.yaml');env.DSH_CRATE_SKILLS_HOME=d.home
  if(d.sharing?.credentials)env.DSH_CRATE_CREDENTIALS_FILE=join(d.sharing.sourceHome,'.credentials.yaml')
  if(d.sharing?.skills)env.DSH_CRATE_SKILLS_HOME=d.sharing.sourceHome
  delete env.DSH_PACK_ACTIVE_PROFILE;delete env.DSH_CRATE_DESKTOP_ADAPTER;delete env.ELECTRON_RUN_AS_NODE
  const child=spawn(this.lifecycle.executable,[`--user-data-dir=${userData}`],{cwd:d.root,env,windowsHide:false,detached:true,stdio:['ignore',log,log]});closeSync(log);child.unref();this.running.set(d.id,child)
  let failure;child.once('error',e=>{failure=e});child.once('exit',()=>this.running.delete(d.id))
  const deadline=Date.now()+90000
  while(Date.now()<deadline){if(failure)throw failure;if(child.exitCode!==null)throw Error('Desktop exited before becoming ready; instance files and log were preserved');try{const s=await instanceRequest(this.record(d));if(s.ready)return {status:'opened',id:d.id,profileName:d.profileName,pid:s.pid}}catch{}await sleep(300)}
  throw Error('Desktop startup timed out. No process was force-terminated; inspect the instance before retrying.')
 }
 async control(id,action,confirm) {
  if(!confirm)throw Error('Confirm closing this Desktop instance first')
  const d=this.definition(id),record=this.record(d)
  if(action!=='stop'&&action!=='restart')throw Error('Unsupported Desktop operation')
  await instanceRequest(record,action,true)
  if(action==='restart')return {status:'scheduled',id}
  const deadline=Date.now()+30000
  while(Date.now()<deadline){if(!alive(record.pid))return {status:'stopped',id};await sleep(300)}
  throw Error('Desktop has not stopped. No snapshot or forced termination was performed.')
 }
 async serve(getReady) {
  const id=process.env.DSH_CRATE_INSTANCE_ID
  if(!id)return
  const d=this.definition(id);if(d.home!==this.home)throw Error('Instance home mismatch')
  const token=randomBytes(32).toString('hex'),suffix=randomUUID(),pipe=process.platform==='win32'?`\\\\.\\pipe\\dsh-crate-${suffix}`:join(d.root,`${suffix}.sock`)
  let stopping=false
  const server=createServer(socket=>{let data='';socket.setTimeout(65000,()=>socket.destroy());socket.on('error',()=>{});socket.on('data',chunk=>{data+=chunk;if(data.length>65536){socket.destroy();return}if(!data.includes('\n'))return;socket.removeAllListeners('data');void(async()=>{
   const request=JSON.parse(data.split('\n')[0]);if(request.token!==token)throw Error('Invalid instance control identity')
   if(request.action==='status'){socket.end(JSON.stringify({ok:true,result:{id,pid:process.pid,ready:getReady()}})+'\n');return}
   if(!request.confirm||!['stop','restart'].includes(request.action))throw Error('Explicit close confirmation is required')
   if(stopping)throw Error('Desktop is already stopping')
   stopping=true
   try{await this.lifecycle.prepare?.();await this.lifecycle.stop()}catch(error){stopping=false;throw error}
   socket.end(JSON.stringify({ok:true,result:{status:'scheduled'}})+'\n');setTimeout(()=>request.action==='restart'?this.lifecycle.restart():this.lifecycle.quit(),150)
  })().catch(error=>socket.end(JSON.stringify({ok:false,error:String(error)})+'\n'))})})
  await new Promise((res,rej)=>{server.once('error',rej);server.listen(pipe,res)})
  atomic(join(d.root,'runtime.json'),{id,home:this.home,pid:process.pid,pipe,token});this.server=server
 }
}
