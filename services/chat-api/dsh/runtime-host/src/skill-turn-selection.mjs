export function resolveSkillTurnContext(modelProfile, value) {
  const input = value && typeof value === 'object' && !Array.isArray(value) ? { ...value } : {}
  const profile = modelProfile?.skillProfile
  let skillName
  const selectedSkillId = String(input.selected_skill_id || '')
  if (selectedSkillId) {
    const skill = profile?.skills?.find(item => item.source_id === selectedSkillId)
    if (skill === undefined) throw new Error('selected Skill is unavailable in this immutable Runtime Profile')
    skillName = skill.name
  }
  const selectedStyleId = String(input.selected_writing_skill_id || '')
  if (selectedStyleId) {
    const style = profile?.writingStyles?.find(item => item.source_id === selectedStyleId)
    if (style === undefined) throw new Error('selected writing standard is unavailable in this immutable Runtime Profile')
    input.writing_style = { name: style.name, instructions: style.instructions }
  }
  delete input.selected_skill_id
  delete input.selected_writing_skill_id
  return { context: input, skillName }
}

export function invokeSelectedSkill(skillName, text) {
  return skillName ? `/${skillName}\n${text}` : text
}
