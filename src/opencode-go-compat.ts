import { AsyncLocalStorage } from 'node:async_hooks'

/** 仅补齐 OpenCode Go 缺失的会话路由头，不改模型、密钥或显式请求头。 */
type RequestIdentity = { provider?: string; sessionId?: string }
type HeaderHook = (request: RequestIdentity, headers: Headers, next: () => unknown) => unknown
type LegacySnapshot = { profiles: Map<string, { headers?: Record<string, string>; [key: string]: unknown }>; [key: string]: unknown }
type LegacyAdapter = {
  config?: { prepareHeaders?: unknown }
  streamWithSnapshot: (request: RequestIdentity, snapshot: LegacySnapshot) => unknown
}
type LegacyContext = {
  llm?: { adapters?: Map<string, { adapter?: LegacyAdapter }> }
  on(event: 'llm/adapters-updated', hook: () => void): unknown
  on(event: 'tools/pre-execute', hook: (exec: { agent?: { session?: { id?: string } } }, next: () => unknown) => unknown, options: { prepend: boolean }): unknown
  effect(setup: () => () => void): unknown
}
export type HeaderHookContext = {
  on(event: string, hook: HeaderHook): unknown
  inject?(services: string[], callback: (ctx: LegacyContext) => void): unknown
}

function sessionIdentity(request: RequestIdentity): string {
  if (typeof request.sessionId !== 'string' || request.sessionId.trim() === '') {
    throw new Error('OpenCode Go request is missing the DSH session identity; retry from a session.')
  }
  return request.sessionId
}

export function installOpenCodeGoCompatibility(ctx: HeaderHookContext): void {
  ctx.on('llm-pi-ai/request-headers', (request, headers, next) => {
    if (request.provider === 'opencode-go' && !headers.has('x-opencode-session')) {
      headers.set('x-opencode-session', sessionIdentity(request))
    }
    return next()
  })
  // 0.2.1 没有请求头事件；仅在旧适配器实例上复制本次请求的配置快照。
  // 不修改共享 provider 配置，也不修改宿主文件，防止并发会话串用身份。
  ctx.inject?.(['llm'], child => {
    const toolSession = new AsyncLocalStorage<{ sessionId: string }>()
    // 旧版自动审核没有把工具所属会话传给 LLM。只沿该次工具调用的
    // 异步链传递真实身份，不使用全局“当前会话”，也不改变审核决定。
    child.on('tools/pre-execute', (exec, next) => {
      const id = exec.agent?.session?.id
      return typeof id === 'string' && id.trim() !== ''
        ? toolSession.run({ sessionId: id }, next)
        : next()
    }, { prepend: true })
    const restores = new Map<LegacyAdapter, () => void>()
    const refresh = () => {
      const adapter = child.llm?.adapters?.get('opencode-go')?.adapter
      if (!adapter || restores.has(adapter) || typeof adapter.config?.prepareHeaders === 'function'
        || typeof adapter.streamWithSnapshot !== 'function' || !Object.isExtensible(adapter)) return
      const original = adapter.streamWithSnapshot
      const descriptor = Object.getOwnPropertyDescriptor(adapter, 'streamWithSnapshot')
      const wrapped: LegacyAdapter['streamWithSnapshot'] = function (this: LegacyAdapter, request, snapshot) {
        if (request.provider !== 'opencode-go') return original.call(this, request, snapshot)
        const profile = snapshot.profiles?.get('opencode-go')
        if (!profile) return original.call(this, request, snapshot)
        if (Object.keys(profile.headers ?? {}).some(name => name.toLowerCase() === 'x-opencode-session')) {
          return original.call(this, request, snapshot)
        }
        const profiles = new Map(snapshot.profiles)
        const identity = request.sessionId === undefined ? { ...request, sessionId: toolSession.getStore()?.sessionId } : request
        profiles.set('opencode-go', { ...profile, headers: { ...profile.headers, 'x-opencode-session': sessionIdentity(identity) } })
        return original.call(this, request, { ...snapshot, profiles })
      }
      adapter.streamWithSnapshot = wrapped
      restores.set(adapter, () => {
        if (adapter.streamWithSnapshot !== wrapped) return
        if (descriptor) Object.defineProperty(adapter, 'streamWithSnapshot', descriptor)
        else Reflect.deleteProperty(adapter, 'streamWithSnapshot')
      })
    }
    child.on('llm/adapters-updated', refresh)
    child.effect(() => { refresh(); return () => { for (const restore of restores.values()) restore(); restores.clear() } })
  })
}
