import { useEffect, useState } from 'react'
import type { PropsLocale, PropsRuntime } from '@deepseek-ai/dsh-client-ui-slots'
import type { DshCrateLocaleKey } from './locales.ts'
import {
  css, STYLE, PluginGroup, PluginName, splitOfficial, objects, request,
} from './DshCratePage.tsx'
import type { Json } from './DshCratePage.tsx'

type PluginListTabProps = PropsRuntime<'settings.plugins.tab'> & PropsLocale<'dsh.crate'>

/**
 * Plugins settings tab replacing the official read-only inventory list.
 * Official DSH built-ins are collapsed into their own group while plugins
 * installed or authored by the user stay expanded, so the two kinds are
 * visually separated instead of mixed into one flat list.
 */
export function PluginListTab({ t }: PluginListTabProps) {
  const [plugins, setPlugins] = useState<Json[]>([])
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [tick, setTick] = useState(0)

  useEffect(() => {
    let current = true
    setStatus('loading')
    void request('profiles').then((value) => {
      if (!current) return
      setPlugins(objects(value.runtimePlugins))
      setStatus('ready')
    }).catch(() => {
      if (current) setStatus('error')
    })
    return () => { current = false }
  }, [tick])

  const retry = () => setTick((value) => value + 1)
  const row = (plugin: Json) => (
    <div className={css.inventoryItem} data-field="runtimePlugin" key={`${String(plugin.id ?? plugin.name)}`}>
      <PluginName name={String(plugin.name ?? 'unknown')} official={plugin.official === true} t={t} />
      <span>{plugin.enabled === true ? t('runtimeEnabled') : t('runtimeDisabled')} · {String(plugin.phase ?? '—')}</span>
    </div>
  )

  return (
    <div className={css.section} data-field="pluginListTab">
      <style>{STYLE}</style>
      <div className={css.inventory} data-field="runtimePlugins">
        <strong>{t('runtimePlugins')}{plugins.length > 0 ? ` · ${plugins.length}` : ''}</strong>
        <span className={css.muted}>{t('updatedAt')}: {status === 'ready' ? new Date().toLocaleTimeString() : t('none')}</span>
        <button className={css.button} type="button" disabled={status === 'loading'} onClick={retry}>{t('refresh')}</button>
        {status === 'loading' ? <p className={css.muted}>{t('pluginListLoading')}</p> : null}
        {status === 'error'
          ? <p className={css.error} role="alert">{t('pluginListError')}</p>
          : null}
        {status === 'ready'
          ? (() => {
              const groups = splitOfficial(plugins)
              return (
                <>
                  <PluginGroup label={t('userPlugins')} count={groups.user.length} defaultOpen t={t}>{groups.user.map(row)}</PluginGroup>
                  <PluginGroup label={t('officialPlugins')} count={groups.official.length} defaultOpen={false} t={t}>{groups.official.map(row)}</PluginGroup>
                </>
              )
            })()
          : null}
      </div>
    </div>
  )
}
