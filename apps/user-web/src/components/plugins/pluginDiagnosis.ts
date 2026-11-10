import type { PluginAvailability } from '../../api/dshPlugins'

export type PluginIssue = 'access' | 'version' | 'package' | 'network' | 'runtime' | 'session' | 'interrupted' | 'unknown'

export function pluginIssue(availability?: PluginAvailability, executionAllowed = true): PluginIssue | null {
  if (!executionAllowed) return 'access'
  if (!availability || ['verified', 'session_exposed', 'runtime_active'].includes(availability.status)) return null
  if (availability.status === 'unverified') {
    return availability.reason === 'plugin_revalidation_interrupted' ? 'interrupted' : null
  }
  if (availability.status === 'version_incompatible' || availability.error_code === 'incompatible-version') return 'version'
  if (availability.status === 'not_exposed' || availability.reason === 'no_global_tool_detected' || availability.reason === 'tools_missing_from_session') return 'session'
  const code = (availability.error_code || '').toLowerCase()
  const reason = availability.reason.toLowerCase()
  if (/network|timeout|econn|enotfound|registry|fetch/.test(`${code} ${reason}`)) return 'network'
  if (/package|install|dependency|pnpm|npm/.test(`${code} ${reason}`)) return 'package'
  if (/runtime|host|load|start|container/.test(`${code} ${reason}`)) return 'runtime'
  return 'unknown'
}

export function requiredDshVersion(availability?: PluginAvailability): string | null {
  if (!availability || pluginIssue(availability) !== 'version') return null
  return availability.reason.match(/@deepseek-ai\/dsh-[\w-]+\s+([~^]?\d[^\s,;]*)/i)?.[1] || null
}
