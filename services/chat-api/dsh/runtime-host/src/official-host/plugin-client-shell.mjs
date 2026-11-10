import { PLUGIN_CLIENT_SERVICES } from '../plugin-client-services.mjs'

const REQUIRED_MODULE = '@deepseek-ai/dsh-client-ui-renderer'
const MAIN_PAGE_SERVICES = new Set(PLUGIN_CLIENT_SERVICES)

export function pluginClientShellPatches(webAppPatches) {
  const found = new Map()
  for (const patch of webAppPatches) {
    for (const row of patch.insert ?? []) {
      if (MAIN_PAGE_SERVICES.has(row.name)) found.set(row.id, row)
    }
  }
  if (![...found.values()].some(row => row.name === REQUIRED_MODULE)) {
    throw new Error('DSH plugin client shell renderer is missing')
  }
  return [{ insert: [...found.values()] }]
}
