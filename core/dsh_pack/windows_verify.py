"""独立桌面验证器的Win32资源、进程身份和被动TCP表；不依赖测试目录。"""
import ctypes as c
import os,socket

class ProcessEntry(c.Structure):
    _fields_ = [('size', c.c_ulong), ('usage', c.c_ulong), ('pid', c.c_ulong),
        ('heap', c.c_size_t), ('module', c.c_ulong), ('threads', c.c_ulong),
        ('parent', c.c_ulong), ('priority', c.c_long), ('flags', c.c_ulong), ('image', c.c_wchar * 260)]

def process_tree(root_pid):
    kernel = c.WinDLL('kernel32', use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [c.c_ulong, c.c_ulong]
    kernel.CreateToolhelp32Snapshot.restype = c.c_void_p
    kernel.Process32FirstW.argtypes = kernel.Process32NextW.argtypes = [c.c_void_p, c.POINTER(ProcessEntry)]
    kernel.CloseHandle.argtypes = [c.c_void_p]
    handle = kernel.CreateToolhelp32Snapshot(2, 0)
    if handle == c.c_void_p(-1).value:
        raise OSError(c.get_last_error(), 'process snapshot')
    rows = []
    try:
        row = ProcessEntry()
        row.size = c.sizeof(row)
        valid = kernel.Process32FirstW(handle, c.byref(row))
        while valid:
            rows.append((row.pid, row.parent))
            valid = kernel.Process32NextW(handle, c.byref(row))
        error = c.get_last_error()
        if error not in (0, 18):
            raise OSError(error, 'process enumeration')
    finally:
        kernel.CloseHandle(handle)
    owned = {root_pid}
    for _ in range(len(rows) + 1):
        added = {pid for pid, parent in rows if parent in owned} - owned
        if not added:
            return owned
        owned.update(added)
    raise RuntimeError('process ancestry did not converge')

class BasicJobLimits(c.Structure):
    _fields_ = [('processTime', c.c_int64), ('jobTime', c.c_int64), ('flags', c.c_ulong),
        ('minimumWorkingSet', c.c_size_t), ('maximumWorkingSet', c.c_size_t),
        ('activeProcesses', c.c_ulong), ('affinity', c.c_size_t), ('priority', c.c_ulong), ('scheduling', c.c_ulong)]

class JobIo(c.Structure):
    _fields_ = [(name, c.c_uint64) for name in ['readOperations', 'writeOperations', 'otherOperations', 'readBytes', 'writeBytes', 'otherBytes']]

class ExtendedJobLimits(c.Structure):
    _fields_ = [('basic', BasicJobLimits), ('io', JobIo), ('processMemory', c.c_size_t),
        ('jobMemory', c.c_size_t), ('peakProcessMemory', c.c_size_t), ('peakJobMemory', c.c_size_t)]

class OwnedJob:
    """Only the created controller joins; its future children cannot outlive Core."""
    def __init__(self):
        self.kernel = c.WinDLL('kernel32', use_last_error=True)
        self.kernel.CreateJobObjectW.argtypes = [c.c_void_p, c.c_wchar_p]
        self.kernel.CreateJobObjectW.restype = c.c_void_p
        self.kernel.SetInformationJobObject.argtypes = [c.c_void_p, c.c_int, c.c_void_p, c.c_ulong]
        self.kernel.AssignProcessToJobObject.argtypes = [c.c_void_p, c.c_void_p]
        self.kernel.CloseHandle.argtypes = [c.c_void_p]
        self.handle = self.kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise OSError(c.get_last_error(), 'CreateJobObjectW')
        limits = ExtendedJobLimits()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE, no breakaway.
        if not self.kernel.SetInformationJobObject(self.handle, 9, c.byref(limits), c.sizeof(limits)):
            error = c.get_last_error()
            self.close()
            raise OSError(error, 'SetInformationJobObject')

    def assign(self, process):
        if not self.kernel.AssignProcessToJobObject(self.handle, int(process._handle)):
            raise OSError(c.get_last_error(), 'AssignProcessToJobObject')

    def active_processes(self):
        class Accounting(c.Structure):
            _fields_ = [(name, c.c_int64) for name in ['user', 'kernel', 'periodUser', 'periodKernel']] + [
                (name, c.c_ulong) for name in ['pageFaults', 'totalProcesses', 'activeProcesses', 'terminatedProcesses']]
        value = Accounting()
        self.kernel.QueryInformationJobObject.argtypes = [c.c_void_p, c.c_int, c.c_void_p, c.c_ulong, c.c_void_p]
        if not self.kernel.QueryInformationJobObject(self.handle, 1, c.byref(value), c.sizeof(value), None):
            raise OSError(c.get_last_error(), 'QueryInformationJobObject')
        return fields(value)

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None
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


class Row4(c.Structure):
    _fields_=[('state',c.c_ulong),('localAddress',c.c_ubyte*4),('localPort',c.c_ulong),('remoteAddress',c.c_ubyte*4),('remotePort',c.c_ulong),('pid',c.c_ulong)]
class Row6(c.Structure):
    _fields_=[('localAddress',c.c_ubyte*16),('localScope',c.c_ulong),('localPort',c.c_ulong),('remoteAddress',c.c_ubyte*16),('remoteScope',c.c_ulong),('remotePort',c.c_ulong),('state',c.c_ulong),('pid',c.c_ulong)]
STATES={1:'CLOSED',2:'LISTEN',3:'SYN_SENT',4:'SYN_RCVD',5:'ESTABLISHED',6:'FIN_WAIT1',7:'FIN_WAIT2',8:'CLOSE_WAIT',9:'CLOSING',10:'LAST_ACK',11:'TIME_WAIT',12:'DELETE_TCB'}

def tcp_rows():
    dll=c.WinDLL('iphlpapi',use_last_error=True)
    dll.GetExtendedTcpTable.argtypes=[c.c_void_p,c.POINTER(c.c_ulong),c.c_int,c.c_ulong,c.c_ulong,c.c_ulong];dll.GetExtendedTcpTable.restype=c.c_ulong
    rows=[]
    for family,kind in [(socket.AF_INET,Row4),(socket.AF_INET6,Row6)]:
        size=c.c_ulong();status=dll.GetExtendedTcpTable(None,c.byref(size),False,family,5,0)
        if status not in (0,122):raise OSError(status,'TCP表大小查询')
        buf=c.create_string_buffer(size.value+65536);size.value=len(buf)
        status=dll.GetExtendedTcpTable(buf,c.byref(size),False,family,5,0)
        if status:raise OSError(status,'TCP表读取')
        count=c.c_ulong.from_buffer(buf).value
        if 4+count*c.sizeof(kind)>len(buf):raise ValueError('TCP表结构超出缓冲区')
        for i in range(count):
            item=kind.from_buffer_copy(buf,4+i*c.sizeof(kind))
            rows.append({'family':'IPv4' if family==socket.AF_INET else 'IPv6','localAddress':socket.inet_ntop(family,bytes(item.localAddress)),
                'localPort':socket.ntohs(item.localPort&65535),'remoteAddress':socket.inet_ntop(family,bytes(item.remoteAddress)),
                'remotePort':socket.ntohs(item.remotePort&65535),'state':STATES.get(item.state,str(item.state)),'pid':item.pid})
    return rows

