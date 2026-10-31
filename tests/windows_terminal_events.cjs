'use strict';
const fs=require('fs'),vm=require('vm'),events=require('events'),assert=require('assert/strict'),path=require('path');
const root=__dirname;const fixture=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));const old={modules:fixture.original};
const patched=fixture.fixedTerminal;
function make(isPatched){
 let agent;const cache={};
 function FakeAgent(){
  agent=this;this.outSocket=new events.EventEmitter();this.inSocket={write(){}};this.innerPid=0;this.fd=0;this.pty=1;this.exitCode=undefined;this.kills=0;
  const err=new events.EventEmitter(),exit=new events.EventEmitter();
  const subscribe=(e,fn)=>{e.on('event',fn);return{dispose(){e.off('event',fn)}}};
  this.onError=fn=>subscribe(err,fn);this.onProcessExit=fn=>subscribe(exit,fn);
  this.fail=e=>err.emit('event',e);this.nativeExit=c=>{this.exitCode=c;exit.emit('event',c)};
  this.kill=()=>{this.kills++};
 }
 function load(name){
  if(cache[name])return cache[name].exports;const module={exports:{}};cache[name]=module;
  const req=id=>id==='./windowsPtyAgent'?{WindowsPtyAgent:FakeAgent}:id==='./utils'?{assign:Object.assign}:id.startsWith('./')?load(id.slice(2)+'.js'):require(id);
  const code=name==='windowsTerminal.js'&&isPatched?patched:old.modules[name];
  vm.runInThisContext('(function(require,module,exports,process,console){'+code+'\n})',{filename:name})(req,module,module.exports,process,console);return module.exports;
 }
 const Terminal=load('windowsTerminal.js').WindowsTerminal,terminal=new Terminal('fake.exe',[],{env:{},cwd:__dirname});
 const exits=[];terminal.onExit(e=>exits.push(e.exitCode));return {terminal,agent,exits};
}
const cases=[];async function test(name,fn){await fn();cases.push({name,status:'PASS'})}
(async()=>{
 await test('original reproduces undefined code on pipe-first order',()=>{const x=make(false);x.agent.innerPid=42;x.agent.outSocket.emit('ready_datapipe');x.agent.outSocket.emit('close');x.agent.nativeExit(127);assert.deepEqual(x.exits,[undefined])});
 for(const code of [0,127])for(const nativeFirst of [true,false])await test(`fixed exact code ${code}, nativeFirst=${nativeFirst}`,async()=>{
  const x=make(true);assert.equal(x.terminal.pid,0);x.agent.innerPid=42;x.agent.outSocket.emit('ready_datapipe');assert.equal(await x.terminal.processReady,42);
  if(nativeFirst)x.agent.nativeExit(code);else x.agent.outSocket.emit('close');assert.equal(x.exits.length,0);
  if(nativeFirst)x.agent.outSocket.emit('close');else x.agent.nativeExit(code);
  x.agent.nativeExit(code);x.agent.outSocket.emit('close');assert.deepEqual(x.exits,[code]);
 });
 await test('connection failure rejects readiness and exits once',async()=>{const x=make(true);const error=new Error('connection failed');x.agent.fail(error);await assert.rejects(x.terminal.processReady,e=>e===error);x.agent.fail(error);assert.deepEqual(x.exits,[-1]);x.terminal.kill();x.terminal.kill();assert.equal(x.agent.kills,1)});
 await test('kill before connection is immediate and idempotent',async()=>{const x=make(true);x.terminal.kill();x.terminal.kill();await assert.rejects(x.terminal.processReady,/before its process connected/);assert.equal(x.agent.kills,1)});
 await test('kill after connection before first data is immediate',async()=>{const x=make(true);x.agent.innerPid=43;x.agent.outSocket.emit('ready_datapipe');await x.terminal.processReady;x.terminal.kill();assert.equal(x.agent.kills,1)});
 await test('invalid connected PID rejects readiness',async()=>{const x=make(true);x.agent.outSocket.emit('ready_datapipe');await assert.rejects(x.terminal.processReady,/valid child pid/);x.terminal.kill()});
 await providerTests();console.log(JSON.stringify({status:"PASS",cases:cases.length}));
})().catch(e=>{console.error(e);process.exitCode=1});

const source=fixture.subprocess.replace(/\r\n/g,'\n');
const start=source.indexOf('async spawnTerminal(spec) {'),end=source.indexOf('\n\t}\n};',start)+3;
assert.ok(start>=0&&end>start);const method=source.slice(start,end);let term,constructed=[];
class Handle {constructor(t){this.pid=t.pid;this.done=new Promise(()=>{});constructed.push(this.pid)}}
const runtime=vm.runInNewContext('({'+method+'})',{targetEnvironment:()=>({}),createProcessInspector:()=>({}),prepareShellActivity:()=>undefined,requireNodePty:()=>({spawn:()=>term}),LocalTerminalHandle:Handle,Promise,Number,Error,AggregateError,process});
runtime.internals={platform:'win32'};runtime.selectContainmentMode=()=>undefined;runtime.terminals=new Set();
const spec=()=>({argv:['runner.exe'],cwd:root,terminalType:'xterm'});
function terminal(){let resolve,reject;const t={pid:0,kills:0,processReady:new Promise((a,b)=>{resolve=a;reject=b})};t.connect=()=>{t.pid=123;resolve(123)};t.kill=()=>{t.kills++;reject(new Error('cancelled before connected'))};return t}

async function providerTests(){
 await test('handle construction waits for positive PID',async()=>{term=terminal();const pending=runtime.spawnTerminal(spec());assert.deepEqual(constructed,[]);term.connect();assert.equal((await pending).pid,123);assert.deepEqual(constructed,[123])});
 await test('abort while connecting rejects without PID0 handle',async()=>{term=terminal();const c=new AbortController(),pending=runtime.spawnTerminal({...spec(),signal:c.signal});c.abort();await assert.rejects(pending,/cancelled/);assert.ok(term.kills>=1);assert.deepEqual(constructed,[123])});
 await test('missing readiness contract is rejected and cleaned',async()=>{term={pid:0,kills:0,kill(){this.kills++}};await assert.rejects(runtime.spawnTerminal(spec()),/readiness contract/);assert.equal(term.kills,1)});
 await test('invalid PID after readiness is rejected',async()=>{term={pid:0,kills:0,processReady:Promise.resolve(),kill(){this.kills++}};await assert.rejects(runtime.spawnTerminal(spec()),/invalid child pid/);assert.equal(term.kills,1)});
 const bash=fixture.bash;const a=bash.indexOf('function startupExitError('),b=bash.indexOf('\nasync function startupSession',a);const errorFn=vm.runInNewContext('('+bash.slice(a,b)+')');
 await test('startup error retains exit code, original output and truncation',()=>{const e=errorFn({sessionStatus:{kind:'exited',exitCode:127},viewport:'null stdin handle',truncated:true});assert.equal(e.exitCode,127);assert.match(e.message,/127/);assert.match(e.message,/null stdin handle/);assert.equal(e.startupOutputTruncated,true)});
}
