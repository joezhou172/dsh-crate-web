import type { ClientContext } from '@deepseek-ai/dsh-client-runtime/client'
import type {} from '@deepseek-ai/dsh-client-ui-settings/client'
import type {} from '@deepseek-ai/dsh-client-locale/client'
import { DshCratePage, request } from './DshCratePage.tsx'
import { PluginListTab } from './PluginListTab.tsx'
import { en, zh } from './locales.ts'
import type { DshCrateLocaleKey } from './locales.ts'
import { createAgentBridge } from './agent-bridge.ts'

const NS = 'dsh.crate'

declare module '@deepseek-ai/dsh-client-ui-slots' {
  interface LocaleNamespaceMap { 'dsh.crate': DshCrateLocaleKey }
}

export const inject = ['slots', 'locale']

export function apply(ctx: ClientContext): void {
  ctx.effect(() => {
    let stopped = false, attempts = 0, timer: ReturnType<typeof setTimeout>
    const acknowledge = async () => {
      try { const result = await request('maintenance-ready'); if (result.status === 'ok') return } catch { /* Retry until the authenticated route is ready. */ }
      if (!stopped && ++attempts < 30) timer = setTimeout(() => void acknowledge(), 1000)
    }
    void acknowledge()
    return () => { stopped = true; clearTimeout(timer) }
  }, 'dsh-crate-web: maintenance client readiness')
  ctx.effect(() => ctx.locale.register(NS, { en, zh }), 'dsh-crate-web: dictionaries')
  const t = ctx.locale.bind(NS)
  const agentBridge = createAgentBridge(ctx, () => t('agentUnavailable'))
  ctx.slots.inject('settings.section', () => ctx.slots.register({
    name: 'settings.section', id: 'dsh-crate', order: 30, label: () => t('nav'), locale: NS,
    inject: () => ({ agentBridge }),
  }, DshCratePage))
  // Collapsible official/user plugin inventory. The tab id is namespaced
  // (`crate`, not `all`) on purpose: real community plugins such as
  // dsh-web-plugin-manager register the official `all` id for their own
  // catalog, and two `all` tabs would render one shared panel.
  ctx.slots.inject('settings.plugins.tab', () => ctx.slots.register({
    name: 'settings.plugins.tab', id: 'crate', order: 10, label: () => t('pluginListTab'), locale: NS,
  }, PluginListTab))
}
