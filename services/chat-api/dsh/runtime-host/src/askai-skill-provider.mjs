const PROVIDER_NAME = 'askai-enterprise'

export class AskaiSkillProvider {
  #skills
  #byName

  constructor(skillProfile) {
    this.name = PROVIDER_NAME
    this.#skills = Object.freeze([...(skillProfile?.skills ?? [])].map(skill => Object.freeze(structuredClone(skill))))
    this.#byName = new Map(this.#skills.map(skill => [skill.name, skill]))
  }

  async list() {
    return this.#skills.map(skill => ({
      name: skill.name,
      description: skill.description,
      ...(skill.when_to_use ? { whenToUse: skill.when_to_use } : {}),
      invocation: { modelInvocable: true, userInvocable: true },
      source: `askai:${skill.source_scope}`,
      rank: 100,
      provider: PROVIDER_NAME,
      locator: Object.freeze({ name: skill.name, version: skill.version }),
      metadata: Object.freeze({
        sourceId: skill.source_id,
        version: skill.version,
        kind: skill.kind,
        capabilityRefs: [...(skill.capability_refs ?? [])],
      }),
    }))
  }

  async get(candidate) {
    const skill = this.#byName.get(candidate?.locator?.name)
    if (skill === undefined || candidate?.locator?.version !== skill.version) return undefined
    return {
      name: skill.name,
      description: skill.description,
      ...(skill.when_to_use ? { whenToUse: skill.when_to_use } : {}),
      invocation: { modelInvocable: true, userInvocable: true },
      source: `askai:${skill.source_scope}`,
      provider: PROVIDER_NAME,
      resourceBase: { kind: 'opaque', description: `MOVO immutable Skill ${skill.version}` },
      metadata: candidate.metadata,
      content: skill.content,
    }
  }
}

export function registerAskaiSkillProvider(ctx, skillProfile) {
  if (!Array.isArray(skillProfile?.skills) || skillProfile.skills.length === 0) return undefined
  return ctx.skills.registerProvider(() => new AskaiSkillProvider(skillProfile))
}
