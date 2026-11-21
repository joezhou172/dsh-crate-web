import type { ClientContext } from '@deepseek-ai/dsh-client-runtime/client'
import type { AgentBridge } from './ReportDialog.tsx'

/** 仅在用户点击转发时发送；锁定弹窗所展示的会话，不重试、不切换目标。 */
export function createAgentBridge(ctx: ClientContext, unavailable: () => string): AgentBridge {
  // Cordis 0.2.2 enforces service ownership even for optional property access.
  // Keep diagnostics available while sessions is absent or being disposed.
  let sessionContext: ClientContext | undefined
  ctx.inject(['sessions'], injected => {
    injected.effect(() => {
      sessionContext = injected
      return () => { if (sessionContext === injected) sessionContext = undefined }
    }, 'dsh-crate-web: optional diagnostic recipient')
  })
  return {
    getAgentTarget() {
      const sessions = sessionContext?.sessions
      const state = sessions?.list.getSnapshot()
      const id = state?.current
      if (!id || !sessions?.scope(id)) return undefined
      return { id, title: state.byId[id]?.title || id }
    },
    async forwardToAgent(text, targetId) {
      const sessions = sessionContext?.sessions
      const id = sessions?.list.getSnapshot().current
      if (!id || id !== targetId) throw new Error(unavailable())
      const scope = sessions?.scope(id)
      const session = scope && sessions?.sessionOf(scope)
      if (!session) throw new Error(unavailable())
      const result = await session.prompt([{ type: 'text', text }], 'queue')
      if (!result.ok) throw new Error(result.error.message)
    },
  }
}
