export const SKILL_RESOURCE_READ_TOOL = 'skill_resource_read'

const PARAMETERS = Object.freeze({
  type: 'object',
  properties: {
    path: {
      type: 'string',
      minLength: 1,
      description: 'Path relative to the active Skill package, for example assets/contacts.json.',
    },
    start_line: {
      type: 'integer',
      minimum: 1,
      description: 'First line to return. Defaults to 1.',
    },
    line_count: {
      type: 'integer',
      minimum: 1,
      maximum: 500,
      description: 'Maximum number of lines to return. Defaults to 200.',
    },
  },
  required: ['path'],
  additionalProperties: false,
})

export function registerSkillResourceTool(ctx, { provider, invocations }) {
  if (!provider?.hasResourceBundles()) return undefined
  return ctx.tools.register({
    name: SKILL_RESOURCE_READ_TOOL,
    description: 'Read a UTF-8 text resource from the active MOVO Skill package. Use relative paths named in SKILL.md, such as assets/*.json or references/*.md.',
    parameters: PARAMETERS,
    output: {
      schema: { type: 'object' },
      render: (_args, value) => [{ type: 'text', text: JSON.stringify(value) }],
    },
    isConcurrencySafe: () => true,
    execute: async (args, exec) => {
      const sessionId = exec.agent?.id
      if (!sessionId) throw new Error('Skill resource read requires an active session')
      const skillName = invocations.current(sessionId)
      if (!skillName) throw new Error('Select or invoke a Skill before reading package resources')
      return await provider.readTextResource(skillName, {
        path: args.path,
        startLine: args.start_line,
        lineCount: args.line_count,
      })
    },
  })
}
