// 最终 tgz 的干净消费安装门槛；不使用开发源码或跳过 peer 检查。
import assert from 'node:assert/strict'
import { existsSync } from 'node:fs'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { dirname, join, resolve } from 'node:path'
import { spawnSync } from 'node:child_process'
import { pathToFileURL } from 'node:url'

function npmEntry() {
  const candidates = [
    process.env.npm_execpath,
    join(dirname(process.execPath), 'node_modules/npm/bin/npm-cli.js'),
    resolve(dirname(process.execPath), '../lib/node_modules/npm/bin/npm-cli.js'),
  ]
  const entry = candidates.find(path => path && existsSync(path))
  if (!entry) throw new Error('找不到当前 Node 配套的 npm CLI；不下载或替换包管理器')
  return entry
}

async function main() {
  const [input, output] = process.argv.slice(2)
  if (!input || !output) throw new Error('需要最终 tgz 路径和新的独占证据目录')
  const tarball = resolve(input), root = resolve(output)
  assert(tarball.endsWith('.tgz') && existsSync(tarball), '制品必须是已有 tgz')
  await mkdir(root) // 已存在即停止，保留上一轮证据。
  const dirs = ['consumer', 'cache', 'temp', 'user', 'user/roaming', 'user/local', 'dsh-home']
  for (const dir of dirs) await mkdir(join(root, dir), { recursive: true })
  await writeFile(join(root, 'empty.npmrc'), '')
  await writeFile(join(root, 'global.npmrc'), '')
  await writeFile(join(root, 'consumer/package.json'), JSON.stringify({ name: 'crate-clean-consumer', private: true }))
  const allowed = new Set(['SYSTEMROOT', 'WINDIR', 'SYSTEMDRIVE', 'PROGRAMFILES', 'PROGRAMFILES(X86)',
    'PROGRAMW6432', 'OS', 'PROCESSOR_ARCHITECTURE', 'NUMBER_OF_PROCESSORS', 'PATHEXT'])
  const env = Object.fromEntries(Object.entries(process.env).filter(([key]) => allowed.has(key.toUpperCase())))
  const systemRoot = Object.entries(env).find(([key]) => key.toUpperCase() === 'SYSTEMROOT')?.[1]
  Object.assign(env, {
    PATH: dirname(process.execPath) + (process.platform === 'win32' ? ';' + join(systemRoot, 'System32') : ':/usr/bin:/bin'),
    HOME: join(root, 'user'), USERPROFILE: join(root, 'user'), APPDATA: join(root, 'user/roaming'),
    LOCALAPPDATA: join(root, 'user/local'), TEMP: join(root, 'temp'), TMP: join(root, 'temp'), TMPDIR: join(root, 'temp'),
    DSH_HOME: join(root, 'dsh-home'), NODE_COMPILE_CACHE: join(root, 'cache/node'),
    NPM_CONFIG_CACHE: join(root, 'cache/npm'), NPM_CONFIG_USERCONFIG: join(root, 'empty.npmrc'),
    NPM_CONFIG_GLOBALCONFIG: join(root, 'global.npmrc'), NPM_CONFIG_REGISTRY: 'https://registry.npmjs.org',
    NPM_CONFIG_FETCH_RETRIES: '0', NPM_CONFIG_UPDATE_NOTIFIER: 'false',
  })
  if (systemRoot) env.ComSpec = join(systemRoot, 'System32/cmd.exe')
  const command = [npmEntry(), 'install', tarball, '--save-exact', '--no-audit', '--no-fund', '--fetch-retries=0', '--fetch-timeout=25000']
  const result = { status: 'FAIL', tarball, command: [process.execPath, ...command], credentialVariablesInherited: [],
    legacyPeerDeps: false, force: false, ignoreScripts: false, modelRequests: 0, desktopStarts: 0 }
  try {
    const run = spawnSync(process.execPath, command, { cwd: join(root, 'consumer'), env, encoding: 'utf8', timeout: 150000, windowsHide: true, maxBuffer: 4 * 1024 * 1024 })
    await writeFile(join(root, 'stdout.log'), run.stdout || '')
    await writeFile(join(root, 'stderr.log'), run.stderr || '')
    result.exitCode = run.status
    if (run.error) throw run.error
    assert.equal(run.status, 0, '最终 tgz 普通安装失败；详见原始 stderr.log')
    const installed = join(root, 'consumer/node_modules/dsh-crate-web')
    const pkg = JSON.parse(await readFile(join(installed, 'package.json'), 'utf8'))
    assert.equal(pkg.name, 'dsh-crate-web')
    const entry = await import(pathToFileURL(join(installed, 'lib/index.js')))
    assert.equal(typeof entry.apply, 'function')
    assert(entry.inject, '发布入口缺少宿主服务声明')
    const lock = JSON.parse(await readFile(join(root, 'consumer/package-lock.json'), 'utf8'))
    const autoInstalled = Object.keys(lock.packages).filter(key => key.includes('node_modules/@deepseek-ai/'))
    assert.deepEqual(autoInstalled, [], '空环境意外自动安装另一套 DSH')
    Object.assign(result, { status: 'PASS', version: pkg.version, entryExports: Object.keys(entry), autoInstalledHostPackages: autoInstalled })
  } catch (error) {
    result.error = error.message
    process.exitCode = 1
  } finally {
    await writeFile(join(root, 'report.json'), JSON.stringify(result, null, 2) + '\n')
    console.log(JSON.stringify(result))
  }
}
main().catch(error => { console.error(error.message); process.exitCode = 1 })
