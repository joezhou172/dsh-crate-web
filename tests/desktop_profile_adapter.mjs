import assert from 'node:assert/strict'
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, existsSync, symlinkSync } from 'node:fs'
import { join } from 'node:path'
import { DesktopProfiles, safeName } from '../desktop-profile-adapter.mjs'
const root = mkdtempSync(join(import.meta.dirname, '../work/desktop-adapter-unit-'))
function setup(label) {
  const home = join(root, label)
  for (const name of ['desktop', '安全研究 测试', '坏环境']) {
    const dir = join(home, 'profiles', name)
    mkdirSync(join(dir, 'node_modules/dsh-crate-web'), { recursive: true })
    writeFileSync(join(dir, 'package.json'), JSON.stringify({ name, dsh: { profile: { bundles: ['dsh-crate-web'] } } }))
    writeFileSync(join(dir, 'node_modules/dsh-crate-web/package.json'), '{}')
    writeFileSync(join(dir, 'marker'), name)
  }
  return home
}
assert(safeName('安全研究 测试'))
for (const name of ['../x', 'CON', 'desktop/', ' test', 'x.']) assert(!safeName(name))
{
 const home = setup('once'), first = new DesktopProfiles(home)
 first.request({ action: 'switch', target: '安全研究 测试', confirm: true }, 'desktop')
 const next = new DesktopProfiles(home)
 assert.equal(next.select(), '安全研究 测试'); assert.equal(next.select(), '安全研究 测试'); next.ready()
 assert.equal(new DesktopProfiles(home).select(), 'desktop')
 assert.equal(readFileSync(join(home, 'profiles/desktop/marker'), 'utf8'), 'desktop')
}
{
 const home = setup('default'), first = new DesktopProfiles(home)
 first.request({ action: 'switch', target: '安全研究 测试', makeDefault: true, confirm: true }, 'desktop')
 assert.equal(first.read().defaultProfile, 'desktop')
 const next = new DesktopProfiles(home); next.select(); next.ready()
 const cold = new DesktopProfiles(home); assert.equal(cold.select(), '安全研究 测试'); cold.ready()
 next.request({ action: 'default', target: 'desktop', confirm: true }, '安全研究 测试')
 assert.equal(new DesktopProfiles(home).select(), 'desktop')
}
{
 const home = setup('replace'), first = new DesktopProfiles(home)
 first.request({ action: 'replace', target: '安全研究 测试', confirm: true }, 'desktop')
 const next = new DesktopProfiles(home); assert.equal(next.select(), 'desktop')
 assert.equal(readFileSync(join(home, 'profiles/desktop/marker'), 'utf8'), '安全研究 测试')
 const backup = next.transactionPaths(next.read().pending).backup
 assert.equal(readFileSync(join(backup, 'marker'), 'utf8'), 'desktop')
 // Simulate process death before ready: next launch must restore original.
 const recovery = new DesktopProfiles(home); assert.equal(recovery.select(), 'desktop')
 assert.equal(readFileSync(join(home, 'profiles/desktop/marker'), 'utf8'), 'desktop')
 assert.equal(recovery.read().lastResult.restored, true)
 assert.equal(readFileSync(join(home, 'profiles/安全研究 测试/marker'), 'utf8'), '安全研究 测试')
}
{
 const home = setup('locked'), first = new DesktopProfiles(home)
 first.request({ action: 'replace', target: '安全研究 测试', confirm: true }, 'desktop')
 writeFileSync(join(home, 'profiles/desktop/lock'), 'locked')
 const next = new DesktopProfiles(home); next.select()
 assert.equal(next.read().lastResult.status, 'failed')
 assert.equal(next.read().lastResult.restored, false)
 assert.equal(readFileSync(join(home, 'profiles/desktop/marker'), 'utf8'), 'desktop')
}
{
 const home = setup('no-confirm'), first = new DesktopProfiles(home)
 assert.throws(() => first.request({action:'replace',target:'安全研究 测试'}, 'desktop'), /confirmation/)
 assert(!existsSync(first.file))
}
{
 const home = setup('broken-default'), first = new DesktopProfiles(home)
 first.request({action:'default',target:'坏环境',confirm:true},'desktop')
 const cold = new DesktopProfiles(home); assert.equal(cold.select(),'坏环境')
 const recovered = new DesktopProfiles(home); assert.equal(recovered.select(),'desktop')
 assert.equal(recovered.read().defaultProfile,'desktop')
 assert.equal(recovered.read().lastResult.status,'failed')
}
{
 const home = join(root,'first-run');mkdirSync(home)
 assert.equal(new DesktopProfiles(home).select(),'desktop')
}
{
 const home = setup('copy-failure'), first = new DesktopProfiles(home)
 first.request({action:'replace',target:'安全研究 测试',confirm:true},'desktop')
 const paths = first.transactionPaths(first.read().pending)
 mkdirSync(paths.dir,{recursive:true});writeFileSync(paths.stage,'occupied')
 const next = new DesktopProfiles(home);assert.equal(next.select(),'desktop')
 assert.equal(next.read().lastResult.status,'failed')
 assert.equal(next.read().lastResult.restored,false)
 assert.equal(readFileSync(join(home,'profiles/desktop/marker'),'utf8'),'desktop')
 assert(!existsSync(paths.backup))
}
console.log(JSON.stringify({status:'PASS',root,scope:'state transitions, default commit, replacement snapshot, interrupted boot rollback, copy failure preservation, lock and confirmation guards, broken default recovery, first run'}))
