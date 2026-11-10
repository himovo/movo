import type { DshPlugin } from '../../api/dshPlugins'
import { hasStandalonePluginUi } from './pluginUiSurface'

const readyStatuses = new Set(['verified', 'session_exposed', 'runtime_active'])

export function pluginConversationAvailable(plugin: DshPlugin): boolean {
  if (!readyStatuses.has(plugin.availability?.status || '')) return false
  const capabilities = plugin.availability?.capabilities
  return Boolean(
    plugin.availability?.session_tools?.length ||
    capabilities?.skills?.some(skill => skill.userInvocable || skill.modelInvocable) ||
    capabilities?.commands?.length ||
    capabilities?.mcpServers?.some(server => server.tools.length),
  )
}

export function pluginCardStatus(plugin: DshPlugin, executionAllowed: boolean): 'ready' | 'loaded' | 'checking' | 'unavailable' | 'off' {
  if (plugin.availability?.status === 'unverified') return 'checking'
  if (!executionAllowed || !readyStatuses.has(plugin.availability?.status || '')) return 'unavailable'
  if (!plugin.enabled) return 'off'
  if (!pluginConversationAvailable(plugin) && !hasStandalonePluginUi(plugin)) return 'loaded'
  return 'ready'
}
