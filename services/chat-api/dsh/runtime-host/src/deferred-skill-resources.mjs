import { realpath, readFile, stat } from 'node:fs/promises'
import { resolve, relative, isAbsolute } from 'node:path'

export const PLUGIN_SKILL_RESOURCE_TOOL = 'plugin_skill_resource_read'

export async function readPluginSkillResource(skill, path) {
  if (skill.resourceBase?.kind !== 'directory' || typeof path !== 'string' || isAbsolute(path)) {
    throw new Error('Plugin Skill requires a package-relative resource path')
  }
  const root = await realpath(skill.resourceBase.path)
  const target = await realpath(resolve(root, path))
  const suffix = relative(root, target)
  if (!suffix || suffix.startsWith('..') || isAbsolute(suffix)) throw new Error('Resource is outside the Skill package')
  const info = await stat(target)
  if (!info.isFile() || info.size > 128 * 1024) throw new Error('Skill resource exceeds the text read limit')
  return { content: [{ type: 'text', text: await readFile(target, 'utf8') }] }
}

export function registerDeferredSkillResources(ctx, plugins, invoke) {
  if (!plugins?.some(plugin => plugin.skills?.length)) return () => {}
  return ctx.tools.register({
    name: PLUGIN_SKILL_RESOURCE_TOOL,
    description: 'Read a text resource from an invoked plugin Skill package using its name and a package-relative path.',
    parameters: {
      type: 'object', properties: { skill: { type: 'string' }, path: { type: 'string' } },
      required: ['skill', 'path'], additionalProperties: false,
    },
    output: { schema: {}, render: (_args, value) => value.content },
    execute: async (args, exec) => {
      const matches = plugins.filter(plugin => plugin.skills?.some(skill => skill.name === args.skill))
      if (matches.length !== 1) throw new Error('Plugin Skill is unavailable or ambiguous')
      return invoke(matches[0], args.skill, { path: args.path }, { ...exec, operation: 'skill-resource' })
    },
  })
}
