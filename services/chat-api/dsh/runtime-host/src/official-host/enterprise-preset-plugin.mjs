import { ASKAI_RUNTIME_PERSONA } from '../runtime-persona.mjs'

export const name = 'askai-enterprise-preset'
export const inject = ['systemPrompt']

export function apply(ctx) {
  return ctx.systemPrompt.section({
    name: 'deployment:persona',
    order: 0,
    text: ASKAI_RUNTIME_PERSONA,
  })
}
