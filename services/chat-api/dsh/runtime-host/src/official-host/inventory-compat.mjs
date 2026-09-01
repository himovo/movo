function presetEntries(agentPresets = []) {
  return agentPresets.flatMap(preset => preset.rows.map(row => ({
    entryId: `${preset.id}:${row.entryId ?? row.moduleName}`,
    moduleName: row.moduleName,
    enabled: row.enabled !== false,
    fiberPhase: row.fiberPhase ?? null,
    presetId: preset.id,
  })))
}

/** Normalize the synchronous rc inventory and asynchronous 0.1.2 snapshot. */
export async function readPluginInventory(gateway) {
  const snapshot = await gateway.list()
  const entries = Array.isArray(snapshot?.entries) ? snapshot.entries : []
  const agentPresets = Array.isArray(snapshot?.agentPresets) ? snapshot.agentPresets : []
  return Object.freeze({
    ...snapshot,
    entries: Object.freeze([...entries, ...presetEntries(agentPresets)]),
    agentPresets: Object.freeze(agentPresets),
  })
}
