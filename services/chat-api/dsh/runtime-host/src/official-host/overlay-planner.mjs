function insertedRows(patch) {
  return Array.isArray(patch?.insert) ? patch.insert : []
}

/**
 * Read the entry identifiers already provided by the official DSH bundles.
 * The ASKAI overlay uses this inventory to survive entries moving between
 * official bundles without registering a second copy of the same plugin.
 */
export function collectInsertedEntryIds(patches) {
  return new Set(patches.flatMap(insertedRows).map(row => row?.id).filter(Boolean))
}

/**
 * Missing entries are mounted by ASKAI. Existing official entries retain
 * their module implementation and receive only ASKAI-owned configuration.
 */
export function planOverlayRows(rows, occupiedIds) {
  const patches = []
  const inserts = []
  for (const row of rows) {
    if (!occupiedIds.has(row.id)) {
      inserts.push(row)
      continue
    }
    if (row.config !== undefined) patches.push({ id: row.id, config: row.config })
  }
  if (inserts.length > 0) patches.push({ insert: inserts })
  return patches
}
