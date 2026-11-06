import assert from 'node:assert/strict'
import { mkdir, mkdtemp, writeFile } from 'node:fs/promises'
import { join, resolve } from 'node:path'
import { openProfile, openedProfiles, closeOpenedProfile } from '../src/open-profile.ts'

// Process lifecycle contract; this fixture is not a DSH compatibility test.
const home = await mkdtemp(resolve('work/open-lifecycle-'))
const runner = join(home, 'fixture.mjs')
await mkdir(join(home, 'profiles/安全环境'), { recursive: true })
await mkdir(join(home, 'profiles/broken'), { recursive: true })
await writeFile(runner, `
const spec=JSON.parse(Buffer.from(process.argv[2],'base64url'));
if(process.env.DSH_CRATE_DESKTOP_ADAPTER!=='0')throw Error('Browser runtime inherited desktop control');
if(spec.name==='broken'){process.send({type:'failed',message:'controlled startup failure'});setTimeout(()=>process.exit(1),25)}
else {process.send({type:'ready',profile:spec.name,pid:process.pid,url:'http://127.0.0.1:12345/'});process.on('message',m=>{if(m.type==='stop')process.exit(0)});process.on('disconnect',()=>process.exit(0))}
`)
try {
  const [one, two] = await Promise.all([openProfile(home, '安全环境', home, runner, home), openProfile(home, '安全环境', home, runner, home)])
  assert.equal(one.pid, two.pid, 'concurrent opens must reuse one process')
  assert.deepEqual(openedProfiles(home), ['安全环境'])
  assert.equal((await openProfile(home, '安全环境', home, runner, home)).pid, one.pid)
  await closeOpenedProfile(home, '安全环境')
  assert.deepEqual(openedProfiles(home), [])
  await assert.rejects(openProfile(home, 'broken', home, runner, home), /controlled startup failure/)
  await new Promise(resolve => setTimeout(resolve, 100))
  assert.deepEqual(openedProfiles(home), [])
  console.log('PASS: concurrent open, reuse, stop, startup failure, child cleanup')
} finally {
  for (const name of openedProfiles(home)) await closeOpenedProfile(home, name)
}
