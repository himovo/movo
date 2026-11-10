export const pluginShortcutsChanged = 'movo:plugin-shortcuts-changed'

function storageKey(mainId: string, userId: string): string {
  return `movo:plugin-shortcuts:${mainId}:${userId}`
}

export function readPluginShortcuts(mainId: string, userId: string): string[] {
  if (!mainId || !userId || typeof localStorage === 'undefined') return []
  try {
    const value: unknown = JSON.parse(localStorage.getItem(storageKey(mainId, userId)) || '[]')
    return Array.isArray(value) ? [...new Set(value.filter((id): id is string => typeof id === 'string'))] : []
  } catch {
    return []
  }
}

export function setPluginShortcut(mainId: string, userId: string, pluginId: string, selected: boolean): string[] {
  if (!mainId || !userId || typeof localStorage === 'undefined') return []
  const current = readPluginShortcuts(mainId, userId)
  const next = selected ? [...current.filter(id => id !== pluginId), pluginId] : current.filter(id => id !== pluginId)
  localStorage.setItem(storageKey(mainId, userId), JSON.stringify(next))
  window.dispatchEvent(new Event(pluginShortcutsChanged))
  return next
}
