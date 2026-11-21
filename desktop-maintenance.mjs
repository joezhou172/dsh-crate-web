import { spawn, spawnSync } from 'node:child_process'
import { readFileSync, writeFileSync, renameSync, openSync, closeSync, lstatSync, existsSync } from 'node:fs'
import { join, resolve, toNamespacedPath } from 'node:path'
const save = (path, value) => { writeFileSync(path+'.tmp',JSON.stringify(value),{mode:0o600});renameSync(path+'.tmp',path) }
const windowsBootstrap = String.raw`import os, sys
def long_path(p):
    p = os.path.abspath(p)
    if p.startswith('\\\\?\\'): return p
    if p.startswith('\\\\'): return '\\\\?\\UNC\\' + p[2:]
    return '\\\\?\\' + p
sys.path[:] = [long_path(p) for p in sys.path]
import runpy
sys.argv[0] = 'dsh_pack.maintenance'
runpy.run_module('dsh_pack.maintenance', run_name='__main__')`

export class DesktopMaintenance {
  constructor(manager, lifecycle) { this.manager = manager; this.lifecycle = lifecycle }
  job(id) {
    if (!/^[a-f0-9-]{36}$/.test(id)) throw Error('Invalid maintenance identity')
    const dir = join(this.manager.home, '.dsh-pack/maintenance', id)
    for (const path of [join(this.manager.home, '.dsh-pack'), join(this.manager.home, '.dsh-pack/maintenance'), dir, join(dir, 'job.json')]) if(lstatSync(path).isSymbolicLink()) throw Error('Linked maintenance paths are not supported')
    const job = JSON.parse(readFileSync(join(dir, 'job.json'), 'utf8'))
    if(job.id!==id || resolve(job.home)!==this.manager.home || job.command!==join(dir,'runner/runtime/python/python.exe')) throw Error('Invalid maintenance job')
    if(typeof job.target!=='string'||!job.target||/[\\/:]|^\.{1,2}$/.test(job.target))throw Error('Invalid maintenance target')
    return { ...job, dir }
  }
  invoke(job, rollback=false, sync=false) {
    const args=['-B',...(process.platform==='win32'?['-c',windowsBootstrap]:['-m','dsh_pack.maintenance']),join(job.dir,'job.json'),...(rollback?['--rollback']:[])]
    const env={...process.env,...job.env,DSH_HOME:job.home,DSH_PACK_ACTIVE_PROFILE:'',PYTHONDONTWRITEBYTECODE:'1'}
    const log=openSync(join(job.dir,rollback?'rollback.log':'execution.log'),'a')
    const options={cwd:toNamespacedPath(job.dir),env,windowsHide:true,stdio:['ignore',log,log]}
    // 保留任务路径校验；仅在创建进程时使用 Windows 长路径形式，供 Python 和 DLL 加载。
    const command=toNamespacedPath(job.command)
    if(sync){try{const r=spawnSync(command,args,options);if(r.error||r.status!==0)throw Error('Maintenance recovery failed; retained job: '+job.dir)}finally{closeSync(log)}return}
    return new Promise((res,rej)=>{const child=spawn(command,args,options);closeSync(log);save(join(job.dir,'worker.json'),{pid:child.pid,finished:false});child.once('error',rej);child.once('exit',code=>{save(join(job.dir,'worker.json'),{pid:child.pid,finished:true,code});code===0?res():rej(Error('Maintenance worker failed; retained job: '+job.dir))})})
  }
  result(job) { return JSON.parse(readFileSync(join(job.dir,'result.json'),'utf8')) }
  begin(id, confirm) {
    const state=this.manager.read(),job=this.job(id)
    if(!confirm||state.maintenance||state.pending||job.target!==this.manager.selected)throw Error('Confirm maintenance of the current environment; another operation may be pending')
    state.maintenance={id,phase:'queued',target:job.target};this.manager.write(state)
    return {status:'scheduled',operationId:id,profileName:job.target}
  }
  async execute() {
    const state=this.manager.read(),job=this.job(state.maintenance.id)
    try {
      await this.lifecycle.stop()
      if(existsSync(join(job.home,'profiles',job.target,'lock')))throw Error('Desktop did not release its runtime lock')
      state.maintenance.phase='executing';this.manager.write(state)
      await this.invoke(job)
      const result=this.result(job)
      if(result.status==='restored'){this.finish(job,result);this.lifecycle.restart();return}
      state.maintenance.phase='awaiting-boot';state.recoveryProfile=job.target;this.manager.write(state)
      this.lifecycle.restart()
    } catch(error) {
      const latest=this.manager.read()
      latest.lastResult={status:'failed',stage:'maintenance',failurePhase:latest.maintenance?.phase,message:'停机或维护失败，未继续覆盖环境',details:String(error),report:join(job.dir,'result.json')}
      // A failed stop never permits a snapshot or an import. Keep the desktop open.
      if(latest.maintenance?.phase==='queued'){delete latest.maintenance;this.manager.write(latest);return}
      this.manager.write(latest)
      try{await this.invoke(job,true);this.finish(job,this.result(job));this.lifecycle.restart()}catch(recovery){latest.lastResult.recoveryError=String(recovery);this.manager.write(latest)}
    }
  }
  startup() {
    const state=this.manager.read(),op=state.maintenance
    if(!op)return
    const job=this.job(op.id)
    const workerFile=join(job.dir,'worker.json')
    if(existsSync(workerFile)){
      const worker=JSON.parse(readFileSync(workerFile,'utf8'))
      if(!worker.finished && Number.isSafeInteger(worker.pid)){
        let active=true;try{process.kill(worker.pid,0)}catch(error){if(error.code==='ESRCH')active=false}
        if(active)throw Error('维护执行器仍在运行；为避免并发覆盖，暂不启动此环境，请稍后重试。')
      }
    }
    if(op.phase==='awaiting-boot'){op.phase='booting';state.recoveryProfile=job.target;this.manager.write(state);return}
    if(op.phase==='queued'){delete state.maintenance;state.lastResult={status:'failed',message:'维护在停机前中断，环境未修改'};this.manager.write(state);return}
    this.invoke(job,true,true);this.finish(job,this.result(job))
  }
  finish(job,result) {
    const state=this.manager.read()
    state.lastResult={status:result.status==='restored'?'failed':'ready',stage:'maintenance',profileName:job.target,restored:result.restored===true,message:result.status==='restored'?'导入或启动失败，已恢复原环境':'停机快照和导入完成，桌面已启动',details:result.error,snapshot:result.result?.snapshot,report:join(job.dir,'result.json')}
    if(state.pending?.defaultProbe && state.pending.target===job.target)delete state.pending
    delete state.maintenance;state.recoveryProfile=job.target;this.manager.write(state)
  }
  ready() { const op=this.manager.read().maintenance;if(op?.phase==='booting'){const job=this.job(op.id),result=this.result(job);result.status='ready';save(join(job.dir,'result.json'),result);this.finish(job,result);return true}return false }
  async failed(message) {
    const op=this.manager.read().maintenance;if(op?.phase!=='booting')return false
    const job=this.job(op.id)
    try { await this.lifecycle.stop();await this.invoke(job,true);const result=this.result(job);result.error=message;this.finish(job,result);this.lifecycle.restart();return true }
    catch(error) {
      const state=this.manager.read()
      state.lastResult={status:'failed',stage:'rollback',restored:false,message:'自动恢复未完成，快照和失败目录已保留；解除文件占用或权限问题后重新启动以重试恢复',details:String(error),report:join(job.dir,'result.json')}
      this.manager.write(state)
      throw error
    }
  }
}
