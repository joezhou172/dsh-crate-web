import type { ClientContext } from '@deepseek-ai/dsh-client-runtime/client'
import type { AgentBridge } from './ReportDialog.tsx'

/** 仅在用户点击转发时发送；锁定弹窗所展示的会话，不重试、不切换目标。 */
export function createAgentBridge(ctx: ClientContext, unavailable: () => string): AgentBridge {
  return {
    getAgentTarget() {
      const state = ctx.sessions?.list.getSnapshot()
      const id = state?.current
      if (!id || !ctx.sessions.scope(id)) return undefined
      return { id, title: state.byId[id]?.title || id }
    },
    async forwardToAgent(text, targetId) {
      const id = ctx.sessions?.list.getSnapshot().current
      if (!id || id !== targetId) throw new Error(unavailable())
      const scope = ctx.sessions.scope(id)
      const session = scope && ctx.sessions.sessionOf(scope)
      if (!session) throw new Error(unavailable())
      const result = await session.prompt([{ type: 'text', text }], 'queue')
      if (!result.ok) throw new Error(result.error.message)
    },
  }
}
