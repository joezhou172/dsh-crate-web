/** 可选的 Windows 官方 runner 宿主适配；不改变沙箱策略或 runner 实现。 */
import { createHash } from 'node:crypto'
import { lstat, mkdir, readFile, readdir, writeFile } from 'node:fs/promises'
import { dirname, isAbsolute, join, resolve } from 'node:path'
import { desktopRuntimeRoot } from './desktop.ts'
import { windowsRunnerIdentity as identity } from './windows-runner-identity.ts'

export interface WindowsTerminalConfig { windowsTerminalCompatibility?: boolean }
export interface SandboxHook {
  constructor: { name: string }
  internals: { windowsAclRunnerArgs?: string[]; windowsAclRunnerEntry?: string }
  runnerCommand?: string[]
  windowsAclRunnerInvocation(): string[]
}

const digest = (data: Uint8Array | string) => createHash('sha256').update(data).digest('hex')
const failure = (reason: string) => new Error(`CRATE_WINDOWS_TERMINAL: ${reason}`)

/** 拒绝重解析链接；不允许缓存写入通过已有路径逃出 Home。 */
async function directory(path: string): Promise<void> {
  const parent = dirname(path)
  if (parent !== path) await directory(parent)
  let info
  try { info = await lstat(path) } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error
    await mkdir(path)
    info = await lstat(path)
  }
  if (!info.isDirectory() || info.isSymbolicLink()) throw failure(`目录不是普通目录: ${path}`)
}

/** 完整校验和完成标记之前不安装钩子；已有缓存每次逐字节复核。 */
export async function prepareWindowsRunner(home: string, runtime: string): Promise<string[]> {
  if (!isAbsolute(home)) throw failure('DSH_HOME 必须是显式绝对路径')
  const pkg = JSON.parse(await readFile(join(runtime, 'node_modules/@deepseek-ai/dsh/package.json'), 'utf8'))
  if (pkg.version !== identity.version) throw failure(`不支持 DSH ${String(pkg.version)}`)
  const provider = await readFile(join(runtime, 'node_modules/@deepseek-ai/dsh-sandbox-local/lib/index.js'))
  if (digest(provider) !== identity.providerSha256) throw failure('官方 sandbox provider 字节不匹配')
  const node = resolve(runtime, '..', '..', 'runtime/primary-runtime/dependencies/node/bin/node.exe')
  const nodeInfo = await lstat(node)
  if (!nodeInfo.isFile() || nodeInfo.isSymbolicLink() || digest(await readFile(node)) !== identity.nodeSha256) {
    throw failure('应用随附控制台 Node 字节不匹配')
  }
  const cache = join(home, '.dsh-pack', 'runtime-sources', 'windows-terminal-rc3-' + digest(JSON.stringify(identity)).slice(0, 20))
  await directory(dirname(cache))
  let exists = false
  try {
    const info = await lstat(cache)
    if (!info.isDirectory() || info.isSymbolicLink()) throw failure('runner 缓存不是普通目录')
    exists = true
  } catch (error) { if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error }
  const target = cache
  const receipt = digest(JSON.stringify(identity))
  if (!exists) await mkdir(target)
  if (exists) {
    const marker = join(target, 'complete.sha256')
    const markerInfo = await lstat(marker)
    if (!markerInfo.isFile() || markerInfo.isSymbolicLink() || await readFile(marker, 'utf8') !== receipt) {
      throw failure('runner 缓存未完整准备，保留现场且不自动修复')
    }
    const inspect = async (prefix = ''): Promise<void> => {
      for (const entry of await readdir(join(target, prefix), { withFileTypes: true })) {
        const name = prefix ? `${prefix}/${entry.name}` : entry.name
        if (entry.isSymbolicLink()) throw failure(`runner 缓存含链接: ${name}`)
        if (entry.isDirectory()) await inspect(name)
        else if (!entry.isFile() || (name !== 'complete.sha256' && !Object.hasOwn(identity.files, name))) throw failure(`runner 缓存含额外文件: ${name}`)
      }
    }
    await inspect()
  }
  // 验证源文件后才写入；失败目录保留供诊断，无自动重试或静默覆盖。
  for (const [name, expected] of Object.entries(identity.files)) {
    const source = await readFile(join(runtime, name))
    if (digest(source) !== expected) throw failure(`官方 runner 依赖字节不匹配: ${name}`)
    const destination = join(target, name)
    if (!exists) {
      await directory(dirname(destination))
      await writeFile(destination, source, { flag: 'wx' })
    }
    const info = await lstat(destination)
    if (!info.isFile() || info.isSymbolicLink() || digest(await readFile(destination)) !== expected) {
      throw failure(`runner 缓存字节不匹配: ${name}`)
    }
  }
  if (!exists) await writeFile(join(target, 'complete.sha256'), receipt, { flag: 'wx' })
  return [node, join(cache, 'node_modules/@deepseek-ai/dsh-sandbox-windows-acl/lib/runner.js')]
}

/** 只拥有自己写入的数组；其他插件后来修改时不得把它覆盖回去。 */
export function installWindowsRunnerHook(sandbox: SandboxHook, args: string[]): () => void {
  if (sandbox?.constructor?.name !== 'LocalSandboxProvider' || !sandbox.internals
    || typeof sandbox.windowsAclRunnerInvocation !== 'function' || sandbox.runnerCommand?.length
    || sandbox.internals.windowsAclRunnerArgs !== undefined || sandbox.internals.windowsAclRunnerEntry !== undefined) {
    throw failure('sandbox 服务不受支持或已有 runner 覆盖')
  }
  const internals = sandbox.internals
  const hadOwn = Object.hasOwn(internals, 'windowsAclRunnerArgs')
  const original = internals.windowsAclRunnerArgs
  const owned = [...args]
  internals.windowsAclRunnerArgs = owned
  let disposed = false
  return () => {
    if (disposed) return
    disposed = true
    if (internals.windowsAclRunnerArgs !== owned) return
    if (hadOwn) internals.windowsAclRunnerArgs = original
    else delete internals.windowsAclRunnerArgs
  }
}

export function windowsTerminalRuntime(config: WindowsTerminalConfig): string | undefined {
  if (config.windowsTerminalCompatibility === undefined || config.windowsTerminalCompatibility === false) return undefined
  if (config.windowsTerminalCompatibility !== true) throw failure('windowsTerminalCompatibility 必须为布尔值')
  if (process.platform !== identity.platform || process.arch !== identity.arch) throw failure('仅支持 Windows x64')
  const runtime = desktopRuntimeRoot()
  if (!runtime || !process.env.DSH_HOME || !isAbsolute(process.env.DSH_HOME)) throw failure('仅支持显式隔离 Home 的官方桌面宿主')
  return runtime
}
