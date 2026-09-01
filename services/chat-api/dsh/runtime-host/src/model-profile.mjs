const ALLOWED_FIELDS = new Set([
  'profileVersion',
  'modelInstanceId',
  'modelName',
  'displayName',
  'contextWindow',
  'maxOutputTokens',
  'gatewayUrl',
  'accessToken',
  'toolProfile',
  'skillProfile',
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
  }
  return Object.freeze(structuredClone(modelProfile))
}
