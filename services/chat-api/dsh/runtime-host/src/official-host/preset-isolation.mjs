const REQUIRED_AGENT_PLANE_ROWS = Object.freeze([
  'tool-bash',
  'tool-fs',
  'tool-skill',
  'compaction-basic',
  'tool-subagent',
  'agent-instructions',
  'tool-web',
])

function containsPresetRoster(patch) {
  return Array.isArray(patch?.insert)
    && patch.insert.some(row => row?.id === 'agent-presets')
}

/**
 * Reuse the official Web Host's agent-plane isolation block without copying
 * its evolving list into ASKAI. The official block is the contiguous run of
 * disabled rows immediately before the preset roster insertion.
 */
export function extractOfficialPresetIsolation(webAppPatches) {
  const rosterIndex = webAppPatches.findIndex(containsPresetRoster)
  if (rosterIndex < 0) {
    throw new Error('DSH Web patch no longer contains the agent-presets roster')
  }

  const reversed = []
  for (let index = rosterIndex - 1; index >= 0; index -= 1) {
    const patch = webAppPatches[index]
    if (patch?.disabled !== true || typeof patch.id !== 'string') break
    reversed.push(patch)
  }
  const patches = reversed.reverse()
  const disabledIds = new Set(patches.map(patch => patch.id))
  const missing = REQUIRED_AGENT_PLANE_ROWS.filter(id => !disabledIds.has(id))
  if (patches.length === 0 || missing.length > 0) {
    throw new Error(
      `DSH Web preset-isolation contract changed; missing rows: ${missing.join(', ') || '(block empty)'}`,
    )
  }
  return Object.freeze({
    patches: Object.freeze(patches),
    disabledIds: Object.freeze([...disabledIds]),
  })
}
