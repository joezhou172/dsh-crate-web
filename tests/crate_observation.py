"""标准测试的独立观测记录；不改变业务判定、不终止进程、不需要额外依赖。"""
from __future__ import annotations
import ctypes as c
from datetime import datetime,timezone
import json,os,platform,statistics,sys,threading,time,uuid
from pathlib import Path

def now():return datetime.now(timezone.utc).isoformat()
class Memory(c.Structure):
    _fields_=[('length',c.c_ulong),('load',c.c_ulong)]+[(n,c.c_uint64) for n in ['totalPhysical','availablePhysical','totalPageFile','availablePageFile','totalVirtual','availableVirtual','availableExtendedVirtual']]
class ProcessMemory(c.Structure):
    _fields_=[('cb',c.c_ulong),('pageFaults',c.c_ulong)]+[(n,c.c_size_t) for n in ['peakWorkingSet','workingSet','peakPagedPool','pagedPool','peakNonpagedPool','nonpagedPool','pageFile','peakPageFile','privateBytes']]
class Io(c.Structure):
    _fields_=[(n,c.c_uint64) for n in ['readOperations','writeOperations','otherOperations','readBytes','writeBytes','otherBytes']]
def fields(obj):return {name:getattr(obj,name) for name,_ in obj._fields_}

def summarize_resources(rows):
    """区间差分CPU及离散采样峰值；不把Host资源归因于单个Worker。"""
    valid=[r for r in rows if 'cpu100ns' in r.get('system',{})];cpu=[];by={}
    for a,b in zip(valid,valid[1:]):
        previous=a['system']['cpu100ns'];current=b['system']['cpu100ns']
        total=sum(current[k]-previous[k] for k in ['kernelIncludingIdle','user']);idle=current['idle']-previous['idle']
        if total>0:cpu.append(100*(total-idle)/total)
    for row in valid:
        for process in row.get('processes',[]):by.setdefault(process['pid'],[]).append((row,process))
    processes=[]
    for pid,pairs in by.items():
        rates=[];memory=[p['memory'] for r,p in pairs if p.get('memory')]
        for (a,p),(b,q) in zip(pairs,pairs[1:]):
            elapsed=(b['monotonicNs']-a['monotonicNs'])/1e9;delta=sum(q['cpu100ns'].values())-sum(p['cpu100ns'].values())
            if elapsed>0:rates.append(delta/1e7/elapsed/(b['system']['logicalCpus'] or 1)*100)
        last=pairs[-1][1]
        processes.append({'pid':pid,'role':last['role'],'peakSampledWorkingSetBytes':max((m['workingSet'] for m in memory),default=None),
            'peakSampledPrivateBytes':max((m['privateBytes'] for m in memory),default=None),'cpuPercentOfMachinePeak':max(rates,default=None),
            'finalCumulativeCpuSeconds':sum(last['cpu100ns'].values())/1e7,'finalCumulativeIo':last.get('io')})
    loads=[r['system']['memory']['load'] for r in valid]
    return {'systemCpuPercentPeak':max(cpu,default=None),'systemMemoryLoadPercentRange':[min(loads),max(loads)] if loads else None,
        'processes':processes,'interpretation':'离散采样；Host含Worker和其他业务。I/O为Windows进程累计计数，不能等同物理磁盘吞吐；缺样本为null。'}

class WindowsCounters:
    def __init__(self):
        self.k=c.WinDLL('kernel32',use_last_error=True);self.ps=c.WinDLL('psapi',use_last_error=True)
        k=self.k
        k.OpenProcess.argtypes=[c.c_ulong,c.c_int,c.c_ulong];k.OpenProcess.restype=c.c_void_p
        k.CloseHandle.argtypes=[c.c_void_p];k.CloseHandle.restype=c.c_int
        k.GetProcessTimes.argtypes=[c.c_void_p]+[c.POINTER(c.c_uint64)]*4;k.GetProcessTimes.restype=c.c_int
        k.GetSystemTimes.argtypes=[c.POINTER(c.c_uint64)]*3;k.GetSystemTimes.restype=c.c_int
        k.GlobalMemoryStatusEx.argtypes=[c.POINTER(Memory)];k.GlobalMemoryStatusEx.restype=c.c_int
        k.GetProcessIoCounters.argtypes=[c.c_void_p,c.POINTER(Io)];k.GetProcessIoCounters.restype=c.c_int
        k.GetExitCodeProcess.argtypes=[c.c_void_p,c.POINTER(c.c_ulong)];k.GetExitCodeProcess.restype=c.c_int
        k.QueryFullProcessImageNameW.argtypes=[c.c_void_p,c.c_ulong,c.c_wchar_p,c.POINTER(c.c_ulong)];k.QueryFullProcessImageNameW.restype=c.c_int
        self.ps.GetProcessMemoryInfo.argtypes=[c.c_void_p,c.POINTER(ProcessMemory),c.c_ulong];self.ps.GetProcessMemoryInfo.restype=c.c_int
    def system(self):
        idle,kernel,user=(c.c_uint64() for _ in range(3));memory=Memory();memory.length=c.sizeof(memory)
        if not self.k.GetSystemTimes(c.byref(idle),c.byref(kernel),c.byref(user)) or not self.k.GlobalMemoryStatusEx(c.byref(memory)):raise OSError(c.get_last_error(),'system counters')
        return {'cpu100ns':{'idle':idle.value,'kernelIncludingIdle':kernel.value,'user':user.value},'memory':fields(memory),'logicalCpus':os.cpu_count()}
    def open(self,pid):
        handle=self.k.OpenProcess(0x1010,False,pid)
        if not handle:raise OSError(c.get_last_error(),'OpenProcess for observation')
        image=c.create_unicode_buffer(32768);length=c.c_ulong(len(image))
        if not self.k.QueryFullProcessImageNameW(handle,0,image,c.byref(length)):
            self.k.CloseHandle(handle);raise OSError(c.get_last_error(),'process image')
        return handle,image.value
    def process(self,pid,handle,role,image):
        creation,end,kernel,user=(c.c_uint64() for _ in range(4));memory=ProcessMemory();memory.cb=c.sizeof(memory);io=Io();code=c.c_ulong()
        if not self.k.GetProcessTimes(handle,*[c.byref(x) for x in [creation,end,kernel,user]]):raise OSError(c.get_last_error(),'process times')
        mem_ok=bool(self.ps.GetProcessMemoryInfo(handle,c.byref(memory),memory.cb));io_ok=bool(self.k.GetProcessIoCounters(handle,c.byref(io)))
        exited=bool(end.value);self.k.GetExitCodeProcess(handle,c.byref(code))
        return {'pid':pid,'role':role,'image':image,'creationFiletime':str(creation.value),'cpu100ns':{'kernel':kernel.value,'user':user.value},
                'memory':fields(memory) if mem_ok else None,'io':fields(io) if io_ok else None,'exited':exited,'exitCode':code.value if exited else None}

class Observation:
    def __init__(self,root,name='test',runtime=None,expect_inspector=False):
        self.run_id=str(uuid.uuid4());self.directory=Path(root).resolve()/self.run_id;self.directory.mkdir(parents=True,exist_ok=False)
        self.trace=self.directory/'trace';self.trace.mkdir();self.name=name;self.runtime=Path(runtime).resolve() if runtime else None
        self.expect_inspector=expect_inspector;self.errors=[];self.stop_event=threading.Event();self.lock=threading.RLock();self.handles={};self.samples=[];self.started=time.perf_counter_ns()
        self.details={}
        self.environment_identity={'os':platform.platform(),'machine':platform.machine(),'python':sys.version.split()[0]}
        if self.runtime:
            manifest=self.runtime/'resources/runtime/crate-build.json'
            if manifest.is_file():self.environment_identity['buildDeclaration']=json.loads(manifest.read_text(encoding='utf8'))
        self.counters=WindowsCounters() if os.name=='nt' else None
        self.environment={'CRATE_TEST_ROOT':str(self.directory),'CRATE_TEST_OBSERVATION_DIR':str(self.trace),'CRATE_TEST_RUN_ID':self.run_id}
        self.thread=threading.Thread(target=self._run,name='crate-test-resources',daemon=True)
        self.thread.start()
    def watch(self,pid,role='test-command'):
        if not self.counters:return
        with self.lock:
            if pid in self.handles:return
            try:
                handle,image=self.counters.open(pid)
                if role=='host' and self.runtime and not Path(image).resolve().is_relative_to(self.runtime):
                    self.counters.k.CloseHandle(handle);raise ValueError('日志PID不属于本例运行时')
                self.handles[pid]=(handle,role,image)
            except Exception as error:self.errors.append({'stage':'watch','pid':pid,'error':str(error)})
    def record(self,event,**data):
        with self.lock:
            with (self.directory/'tests.jsonl').open('a',encoding='utf8') as f:f.write(json.dumps({'runId':self.run_id,'atUtc':now(),'monotonicNs':time.perf_counter_ns(),'event':event,**data},ensure_ascii=False)+'\n')
    def checkpoint(self):
        try:
            with self.lock:
                return {'system':self.counters.system() if self.counters else None,
                        'processes':[self.counters.process(pid,h,role,image) for pid,(h,role,image) in self.handles.items()]}
        except Exception as error:
            self.errors.append({'stage':'test-checkpoint','error':str(error)});return {'status':'UNTESTED','error':str(error)}
    def _discover_host(self):
        for p in self.trace.glob('parent-*.jsonl'):
            try:
                with p.open(encoding='utf8') as f:row=json.loads(f.readline(65536))
                if row.get('runId')==self.run_id and row.get('threadId')==0:self.watch(row['pid'],'host')
            except (OSError,ValueError,KeyError):pass
    def _sample(self):
        self._discover_host();row={'runId':self.run_id,'atUtc':now(),'monotonicNs':time.perf_counter_ns(),'system':self.counters.system() if self.counters else {'status':'UNTESTED_PLATFORM'},'processes':[]}
        with self.lock:
            for pid,(handle,role,image) in self.handles.items():
                try:row['processes'].append(self.counters.process(pid,handle,role,image))
                except Exception as error:self.errors.append({'stage':'sample','pid':pid,'error':str(error)})
        return row
    def _run(self):
        with (self.directory/'resources.jsonl').open('x',encoding='utf8') as f:
            while not self.stop_event.is_set():
                started=time.perf_counter()
                try:row=self._sample()
                except Exception as error:row={'atUtc':now(),'observerError':str(error)};self.errors.append({'stage':'system','error':str(error)})
                row['samplingCostMs']=(time.perf_counter()-started)*1000;self.samples.append(row)
                f.write(json.dumps(row,ensure_ascii=False)+'\n');f.flush();self.stop_event.wait(max(0,0.2-(time.perf_counter()-started)))
    def close(self,business_status='UNTESTED'):
        self.stop_event.set();self.thread.join(timeout=3);self._discover_host()
        roles={};stages=[]
        for p in self.trace.glob('*.jsonl'):
            try:
                rows=[json.loads(x) for x in p.read_text(encoding='utf8').splitlines()]
                if any(x.get('runId')!=self.run_id for x in rows):raise ValueError('运行标识不匹配')
                if p.name.startswith(('parent-','worker-')):
                    for i,row in enumerate(rows,1):
                        if row['sequence']!=i:raise ValueError('阶段序号不连续')
                    stages.extend(rows)
                if p.name.startswith('debugger-'):
                    role=rows[0]['role'];hits=[x for x in rows if x['event']=='breakpoint.hit']
                    roles[role]={'configured':sum(x['event']=='breakpoint.configured' for x in rows),'hitCount':len(hits),'labels':[x['label'] for x in hits],
                                 'errors':[x for x in rows if x['event'] in ['protocol.error','unexpected.pause','setup.error']]}
            except Exception as error:self.errors.append({'stage':'trace','file':p.name,'error':str(error)})
        times={};pending={};stage_intervals=[]
        for x in stages:
            event=x['event']
            if event.endswith('.enter'):
                pending.setdefault((x['pid'],x['threadId'],event[:-6]),[]).append(x)
            elif event.endswith(('.return','.throw')):
                label=event.rsplit('.',1)[0];stack=pending.get((x['pid'],x['threadId'],label),[])
                if stack:
                    begin=stack.pop();duration=(int(x['hrtimeNs'])-int(begin['hrtimeNs']))/1e6
                    stage_intervals.append({'pid':x['pid'],'threadId':x['threadId'],'label':label,'enterSequence':begin['sequence'],
                        'endSequence':x['sequence'],'outcome':event.rsplit('.',1)[1],'durationMs':duration})
                    times.setdefault(label,[]).append(duration)
        first=next((x for x in stages if x['event']=='worker.constructor.return'),None);ready=next((x for x in stages if x['event']=='ready.wait.resolve'),None)
        if first and ready:times['inspector.ready']=[(int(ready['hrtimeNs'])-int(first['hrtimeNs']))/1e6]
        final=[]
        with self.lock:
            for pid,(handle,role,image) in self.handles.items():
                try:final.append(self.counters.process(pid,handle,role,image))
                except Exception as error:self.errors.append({'stage':'final-process','pid':pid,'error':str(error)})
                finally:self.counters.k.CloseHandle(handle)
            self.handles.clear()
        coverage='NOT_APPLICABLE'
        if self.expect_inspector:coverage='PASS' if len(set(roles.get('parent',{}).get('labels',[])))==4 and len(set(roles.get('worker',{}).get('labels',[])))==7 and roles['parent']['configured']==4 and roles['worker']['configured']==7 and not any(x['errors'] for x in roles.values()) else 'UNTESTED'
        valid=[x for x in self.samples if 'monotonicNs'in x];intervals=[(b['monotonicNs']-a['monotonicNs'])/1e6 for a,b in zip(valid,valid[1:])]
        report={'schemaVersion':1,'runId':self.run_id,'name':self.name,'businessStatus':business_status,'environment':self.environment_identity,**self.details,
                'observationStatus':'DEGRADED' if self.errors or self.thread.is_alive() or (self.expect_inspector and coverage!='PASS') else 'PASS','breakpointCoverage':coverage,'breakpoints':roles,
                'stageDurationsMs':times,'stageIntervals':stage_intervals,'resourceSummary':summarize_resources(self.samples),'sampleCount':len(self.samples),'nominalIntervalMs':200,'actualIntervalMedianMs':statistics.median(intervals) if intervals else None,
                'actualIntervalMaxMs':max(intervals) if intervals else None,'finalProcessQueries':final,'observerErrors':self.errors,
                'historicalNaturalStartupTimeout':'UNKNOWN','note':'businessStatus仅为调用方本次测试/退出结果，不代表完整兼容验收；观测结果单列。断点/CPU采样会影响时序，缺记录不代表通过。'}
        try:
            with (self.directory/'report.json').open('x',encoding='utf8') as f:json.dump(report,f,ensure_ascii=False,indent=2);f.write('\n')
        except OSError as error:
            report['observationStatus']='DEGRADED';report['observerErrors'].append({'stage':'write-report','error':str(error)})
        return report
