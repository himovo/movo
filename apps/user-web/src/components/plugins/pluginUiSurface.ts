import type { DshPlugin, PluginAvailability } from '../../api/dshPlugins'

export function hasStandaloneUiSurface(availability?: PluginAvailability): boolean {
  const capabilities = availability?.capabilities
  return Boolean(capabilities?.clientModules?.length)
}

export function hasStandalonePluginUi(plugin: DshPlugin): boolean {
  return hasStandaloneUiSurface(plugin.availability)
}
