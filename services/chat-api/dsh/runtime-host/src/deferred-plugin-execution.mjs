import { scopeOf } from '@deepseek-ai/dsh-scope'
import { executeDeferredTool } from './deferred-plugin-tools.mjs'
import { readPluginSkillResource, PLUGIN_SKILL_RESOURCE_TOOL } from './deferred-skill-resources.mjs'

export async function executePluginInvocation(ctx, agent, plugins, name, args, signal, operation) {
  if (operation === 'skill' || operation === 'skill-resource') {
    if (!plugins?.some(plugin => plugin.skills?.some(skill => skill.name === name))) {
      throw new Error('Plugin Skill is outside the Runtime profile')
    }
    const skill = await ctx.skills.get(name, { scope: agent, signal, cwd: agent.session.header.cwd })
    if (!skill) throw new Error('Plugin Skill is unavailable')
    if (operation === 'skill-resource') return readPluginSkillResource(skill, args.path)
    if (skill.resourceBase?.kind === 'directory') {
      return { ...skill, resourceBase: { kind: 'opaque',
        description: `Read package-relative text resources with ${PLUGIN_SKILL_RESOURCE_TOOL}, skill=${JSON.stringify(name)}.` } }
    }
    return skill
  }
  if (operation !== 'tool') throw new Error('Unknown plugin invocation operation')
  if (plugins?.filter(plugin => plugin.tool_names?.includes(name)).length !== 1 ||
      !ctx.tools.executable(name, scopeOf(agent.ctx))) {
    throw new Error('Plugin tool is outside the Runtime profile')
  }
  return executeDeferredTool(ctx, agent, name, args, signal)
}
