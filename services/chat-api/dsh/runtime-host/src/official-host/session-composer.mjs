import { installModelSelection } from '@deepseek-ai/dsh-agent'
import { SessionId } from '@deepseek-ai/dsh-session'

import { ASKAI_ENTERPRISE_PRESET_ID } from './overlay.mjs'
import { resolveNativePreset } from './api-compat.mjs'

function selectedPreset(meta, events) {
  let value = typeof meta?.agentPreset === 'string' ? meta.agentPreset : undefined
  for (const event of events ?? []) {
    if (event.type === 'agent-preset/selected' && typeof event.data?.agentPreset === 'string') {
      value = event.data.agentPreset
    }
  }
  return value
}

export function enterpriseToolNames(modelProfile) {
  const profile = modelProfile?.toolProfile
  if (profile === undefined) return modelProfile?.skillProfile?.skills?.length > 0 ? ['skill'] : []
  const replaced = new Set(profile.nativeReplacements ?? [])
  const names = profile.tools
    .map(tool => tool.name)
    .filter(name => typeof name === 'string' && name && !replaced.has(name))
  if (replaced.has('external_search')) names.push('web_search')
  if (modelProfile?.skillProfile?.skills?.length > 0) names.push('skill')
  return [...new Set(names)].sort()
}

export class OfficialSessionComposer {
  constructor(ctx, { agentOptions, enterpriseTools }) {
    this.ctx = ctx
    this.agentOptions = Object.freeze({ ...agentOptions })
    this.enterpriseTools = Object.freeze([...enterpriseTools])
  }

  async prepare(requestedPreset) {
    const presets = this.ctx.get('agentPresets')
    if (presets === undefined) throw new Error('official DSH agent preset registry is unavailable')
    const preset = await resolveNativePreset(presets, requestedPreset)
    return {
      // The durable/public identity remains ASKAI's versioned contract. Only
      // the mounted native preset follows the name shipped by this DSH train.
      presetId: requestedPreset,
      setup: async agentCtx => {
        installModelSelection(agentCtx, {
          current: {
            provider: this.agentOptions.provider,
            model: this.agentOptions.model,
          },
          assembled: undefined,
        })
        await presets.mount(agentCtx, preset.id)
        if (preset.id === ASKAI_ENTERPRISE_PRESET_ID) {
          this.#restrictEnterpriseSession(agentCtx)
        }
      },
    }
  }

  async persistedIdentity(sessionId) {
    const persistence = this.ctx.get('sessionPersistence')
    if (persistence === undefined) throw new Error('official DSH session persistence is unavailable')
    const inspected = await persistence.inspect(SessionId(sessionId))
    return {
      presetId: selectedPreset(inspected.meta, inspected.events),
      cwd: inspected.meta?.cwd,
    }
  }

  #restrictEnterpriseSession(agentCtx) {
    // Preset tools are scoped to the agent and therefore are intentionally not
    // visible from the Host/root catalog. Restrict against the declared Runtime
    // Profile names directly; pre-filtering through the root catalog silently
    // removed scoped tools such as DSH's native web_search.
    agentCtx.tools.restrict({ allow: this.enterpriseTools })
  }
}
