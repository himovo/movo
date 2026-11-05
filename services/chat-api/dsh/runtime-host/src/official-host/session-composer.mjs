import { installModelSelection } from '@deepseek-ai/dsh-agent'
import { SessionId } from '@deepseek-ai/dsh-session'

import { ASKAI_ENTERPRISE_PRESET_ID } from './overlay.mjs'
import { normalizePersistedPreset, resolveNativePreset } from './api-compat.mjs'
import { readPersistedSession } from './session-state.mjs'
import { SKILL_RESOURCE_READ_TOOL } from '../skill-resource-tool.mjs'

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
  const pluginTools = (modelProfile?.plugins ?? []).flatMap(plugin => plugin.tool_names ?? [])
  const skills = modelProfile?.skillProfile?.skills ?? []
  const skillTools = []
  if (skills.length > 0) skillTools.push('skill')
  if (skills.some(skill => Boolean(skill.bundle_archive_base64 || skill.bundle_archive_id))) skillTools.push(SKILL_RESOURCE_READ_TOOL)
  if (profile === undefined) return [...new Set([...pluginTools, ...skillTools, 'ask_user_question'])].sort()
  const replaced = new Set(profile.nativeReplacements ?? [])
  const names = profile.tools
    .map(tool => tool.name)
    .filter(name => typeof name === 'string' && name && !replaced.has(name))
  if (replaced.has('external_search')) names.push('web_search')
  names.push(...skillTools, ...pluginTools, 'ask_user_question')
  return [...new Set(names)].sort()
}

export function eligibleEnterpriseTools(enterpriseTools, plugins, { hasWorkspace }) {
  if (hasWorkspace) return [...enterpriseTools]
  const workspaceRequired = new Set((plugins ?? []).flatMap(plugin =>
    Object.entries(plugin.tool_requirements ?? {})
      .filter(([, requirements]) => requirements.includes('workspace'))
      .map(([name]) => name)))
  return enterpriseTools.filter(name => !workspaceRequired.has(name))
}

export class OfficialSessionComposer {
  constructor(ctx, { agentOptions, enterpriseTools, plugins = [] }) {
    this.ctx = ctx
    this.agentOptions = Object.freeze({ ...agentOptions })
    this.enterpriseTools = Object.freeze([...enterpriseTools])
    this.plugins = Object.freeze([...plugins])
  }

  async prepare(requestedPreset, { hasWorkspace = false } = {}) {
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
          this.#restrictEnterpriseSession(agentCtx, hasWorkspace)
        }
      },
    }
  }

  async persistedIdentity(sessionId) {
    const persistence = this.ctx.get('sessionPersistence')
    if (persistence === undefined) throw new Error('official DSH session persistence is unavailable')
    const inspected = await readPersistedSession(persistence, SessionId(sessionId))
    return {
      presetId: normalizePersistedPreset(selectedPreset(inspected.meta, inspected.events)),
      cwd: inspected.meta?.cwd,
      events: inspected.events,
    }
  }

  #restrictEnterpriseSession(agentCtx, hasWorkspace) {
    // Preset tools are scoped to the agent and therefore are intentionally not
    // visible from the Host/root catalog. Restrict against the declared Runtime
    // Profile names directly; pre-filtering through the root catalog silently
    // removed scoped tools such as DSH's native web_search.
    const allow = eligibleEnterpriseTools(this.enterpriseTools, this.plugins, { hasWorkspace })
    agentCtx.tools.restrict({ allow })
  }
}
