const ALLOWED_FIELDS = new Set([
  'profileVersion',
  'modelInstanceId',
  'modelName',
  'displayName',
  'visionEnabled',
  'contextWindow',
  'maxOutputTokens',
  'gatewayUrl',
  'accessToken',
  'toolProfile',
  'skillProfile',
  'bundleGatewayUrl',
  'pluginGatewayUrl',
  'plugins',
])

function nonEmptyString(value) {
  return typeof value === 'string' && value.length > 0
}

function validateSkillProfile(profile) {
  if (profile === null || typeof profile !== 'object' || Array.isArray(profile) ||
      !Array.isArray(profile.skills) || !Array.isArray(profile.writingStyles)) {
    throw new Error('skillProfile is incomplete')
  }
  const names = new Set()
  for (const skill of profile.skills) {
    if (skill === null || typeof skill !== 'object' || Array.isArray(skill) ||
        !nonEmptyString(skill.name) || !nonEmptyString(skill.version) ||
        !nonEmptyString(skill.source_id) || !nonEmptyString(skill.content) ||
        (skill.display_name !== undefined && typeof skill.display_name !== 'string') ||
        !['personal', 'organization'].includes(skill.source_scope) ||
        !['ordinary', 'workflow'].includes(skill.kind) || names.has(skill.name)) {
      throw new Error('skillProfile contains an invalid Skill definition')
    }
    names.add(skill.name)
  }
  const styleIds = new Set()
  for (const style of profile.writingStyles) {
    if (style === null || typeof style !== 'object' || Array.isArray(style) ||
        !nonEmptyString(style.ref) || !nonEmptyString(style.version) ||
        !nonEmptyString(style.source_id) || !nonEmptyString(style.name) ||
        !nonEmptyString(style.instructions) ||
        !['personal', 'organization'].includes(style.source_scope) ||
        styleIds.has(style.source_id)) {
      throw new Error('skillProfile contains an invalid writing standard')
    }
    styleIds.add(style.source_id)
  }
}

export function normalizeModelProfile(modelProfile, profileVersion) {
  if (modelProfile === undefined) return undefined
  if (modelProfile === null || typeof modelProfile !== 'object' || Array.isArray(modelProfile)) {
    throw new Error('modelProfile must be an object')
  }
  const unknown = Object.keys(modelProfile).filter(key => !ALLOWED_FIELDS.has(key))
  if (unknown.length > 0) throw new Error(`modelProfile contains forbidden fields: ${unknown.join(', ')}`)
  for (const field of ['profileVersion', 'modelInstanceId', 'modelName', 'gatewayUrl', 'accessToken']) {
    if (typeof modelProfile[field] !== 'string' || modelProfile[field].length === 0) {
      throw new Error(`modelProfile is missing ${field}`)
    }
  }
  if (modelProfile.profileVersion !== profileVersion) throw new Error('modelProfile version mismatch')
  if (modelProfile.toolProfile !== undefined) {
    const toolProfile = modelProfile.toolProfile
    if (toolProfile === null || typeof toolProfile !== 'object' || Array.isArray(toolProfile)) {
      throw new Error('toolProfile must be an object')
    }
    if (typeof toolProfile.gatewayUrl !== 'string' || !toolProfile.gatewayUrl ||
        typeof toolProfile.accessToken !== 'string' || !toolProfile.accessToken ||
        !Array.isArray(toolProfile.tools)) {
      throw new Error('toolProfile is incomplete')
    }
  }
  if (modelProfile.skillProfile !== undefined) {
    validateSkillProfile(modelProfile.skillProfile)
    if (modelProfile.skillProfile.skills.some(skill => skill.bundle_archive_id) && !nonEmptyString(modelProfile.bundleGatewayUrl)) {
      throw new Error('modelProfile is missing bundleGatewayUrl')
    }
  }
  if (modelProfile.plugins !== undefined) {
    if (!Array.isArray(modelProfile.plugins)) throw new Error('plugins must be an array')
    const names = new Set()
    for (const plugin of modelProfile.plugins) {
      if (!plugin || typeof plugin !== 'object' || Array.isArray(plugin) ||
          !nonEmptyString(plugin.name) || !nonEmptyString(plugin.version) ||
          !nonEmptyString(plugin.spec) || names.has(plugin.name) ||
          !['personal', 'organization'].includes(plugin.source_scope) ||
          (plugin.archive_id !== undefined && (!/^[0-9a-f]{32}$/.test(plugin.archive_id) ||
            !/^[0-9a-f]{64}$/.test(plugin.archive_digest ?? '') || !nonEmptyString(modelProfile.pluginGatewayUrl))) ||
          (plugin.tool_names !== undefined && (!Array.isArray(plugin.tool_names) ||
            plugin.tool_names.some(name => !nonEmptyString(name))))) {
        throw new Error('plugins contains an invalid DSH plugin declaration')
      }
      names.add(plugin.name)
    }
  }
  return Object.freeze(structuredClone(modelProfile))
}
