import { DSH_CODE_RESERVED_TOOL_NAMES } from './official-host/tool-name-policy.mjs'

export function deferredToolOwners(plugins, occupied = []) {
  const candidates = new Map()
  const blocked = new Set([...DSH_CODE_RESERVED_TOOL_NAMES, ...occupied])
  for (const plugin of plugins ?? []) {
    for (const tool of plugin.deferred_tool_contracts ?? []) {
      if (blocked.has(tool.name)) continue
      const matches = candidates.get(tool.name) ?? []
      matches.push({ plugin, tool })
      candidates.set(tool.name, matches)
    }
  }
  return [...candidates.values()].filter(matches => matches.length === 1).map(matches => matches[0])
}
