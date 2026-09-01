/** Resolve a trusted predecessor Session into a native DSH event seed. */
export async function resolveSessionSeed(manager, input) {
  const body = { ...input }
  if (Object.hasOwn(body, 'seed') || Object.hasOwn(body, 'parentSessionId')) {
    throw new Error('raw Session seed is forbidden over the Runtime Host API')
  }
  const hasSeedRuntime = Object.hasOwn(body, 'seedRuntimeId')
  const hasSeedSession = Object.hasOwn(body, 'seedSessionId')
  if (hasSeedRuntime !== hasSeedSession) {
    throw new Error('seed Runtime and Session identity must be supplied together')
  }
  if (!hasSeedRuntime) return body

  const seedRuntimeId = String(body.seedRuntimeId)
  const seedSessionId = String(body.seedSessionId)
  delete body.seedRuntimeId
  delete body.seedSessionId
  body.seed = await manager.exportCompletedSeed(seedRuntimeId, seedSessionId)
  body.parentSessionId = seedSessionId
  return body
}
