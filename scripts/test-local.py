"""标准本地测试入口：每轮及每个单元用例均记录结果和资源。"""
from pathlib import Path
from datetime import datetime,timezone
import argparse,json,os,subprocess,sys,time,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'tests'),str(ROOT/'core')]
from crate_observation import Observation
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=ROOT/'work/test-observations');p.add_argument('--pattern',default='test_*.py');p.add_argument('command',nargs=argparse.REMAINDER);a=p.parse_args()
    output=a.output.resolve()
    if not output.is_relative_to((ROOT/'work').resolve()):p.error('测试证据仅允许写入项目work目录')
    observation=Observation(output,'command' if a.command else a.pattern);temp=observation.directory/'temp';temp.mkdir()
    os.environ.update(observation.environment,TEMP=str(temp),TMP=str(temp));exit_code=1
    if os.name=='nt':
        # 主机ComSpec可能仍含未展开的%SystemRoot%；仅规范本轮子进程环境。
        shell=Path(os.environ.get('SystemRoot',r'C:\Windows'))/'System32/cmd.exe'
        if not shell.is_file():raise RuntimeError('本轮测试找不到Windows命令解释器')
        observation.details['commandInterpreter']={'path':str(shell),'scope':'this-test-process-only'}
        os.environ['ComSpec']=str(shell)
    try:
        if a.command:
            command=a.command[1:] if a.command[0]=='--' else a.command
            if not command:p.error('缺少测试命令')
            with (observation.directory/'stdout.log').open('xb') as stdout,(observation.directory/'stderr.log').open('xb') as stderr:
                process=subprocess.Popen(command,cwd=ROOT,stdout=stdout,stderr=stderr,shell=False)
                observation.watch(process.pid);exit_code=process.wait()
        else:
            class Result(unittest.TextTestResult):
                def startTest(self,test):
                    super().startTest(test);self.case_start=time.perf_counter_ns();self.case_status='PASS'
                    observation.record('test.start',test=test.id(),resource=observation.checkpoint())
                def stopTest(self,test):
                    observation.record('test.complete',test=test.id(),status=self.case_status,elapsedMs=(time.perf_counter_ns()-self.case_start)/1e6,resource=observation.checkpoint());super().stopTest(test)
                def addSuccess(self,test):super().addSuccess(test);observation.record('test.end',test=test.id(),status='PASS')
                def addFailure(self,test,error):self.case_status='FAIL';super().addFailure(test,error);observation.record('test.end',test=test.id(),status='FAIL')
                def addError(self,test,error):self.case_status='FAIL_ERROR';super().addError(test,error);observation.record('test.end',test=test.id(),status='FAIL_ERROR')
                def addSkip(self,test,reason):self.case_status='UNTESTED';super().addSkip(test,reason);observation.record('test.end',test=test.id(),status='UNTESTED',reason=reason)
                def addSubTest(self,test,subtest,error):
                    if error is not None:self.case_status='FAIL'
                    super().addSubTest(test,subtest,error)
                    observation.record('test.subtest',test=test.id(),status='FAIL' if error else 'PASS')
            observation.watch(os.getpid(),'test-runner')
            suite=unittest.defaultTestLoader.discover(str(ROOT/'tests'),pattern=a.pattern)
            with (observation.directory/'tests.log').open('x',encoding='utf8') as log:
                result=unittest.TextTestRunner(stream=log,verbosity=2,resultclass=Result).run(suite)
            observation.details['unitSummary']={'run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped)}
            exit_code=0 if result.wasSuccessful() else 1
    finally:
        report=observation.close('PASS' if exit_code==0 else 'FAIL')
        print(json.dumps({'exitCode':exit_code,'observation':str(observation.directory),'observationStatus':report['observationStatus'],'sampleCount':report['sampleCount']},ensure_ascii=False))
    return exit_code
if __name__=='__main__':raise SystemExit(main())
