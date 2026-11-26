import { liveSessionEvents } from './session-state.mjs'

/** Read DSH's replay-aware meter and exact routed model metadata. */
export async function readContextUsage(ctx, agent, commandActive = false) {
  const meter = ctx.get('tokenMeter')
  if (!meter) return { available: false }
  const measurement = meter.measure(agent.session)
  const route = agent.session.requestHeader()?.config ?? agent.options
  let capacity = null
  try {
    const model = await ctx.llm.resolveModelInfo(route.provider, route.model)
    capacity = model.context?.contextWindow ?? null
  } catch {
    // Model metadata may be unavailable while the persisted token fold is valid.
  }
  const lifecycle = liveSessionEvents(agent.session).findLast(event =>
    event.type === 'compaction/start' || event.type === 'compaction/end')
  return {
    available: true,
    usedTokens: measurement.totalTokens,
    capacityTokens: capacity,
    modelName: route.model,
    estimated: measurement.baseline.kind !== 'usage' || measurement.surfaceDeltaTokens !== 0,
    revision: measurement.logRevision,
    compacting: commandActive || lifecycle?.type === 'compaction/start',
  }
}
