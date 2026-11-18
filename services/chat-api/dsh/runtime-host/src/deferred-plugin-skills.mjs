// Skill discovery uses installation snapshots; loading a body invokes its provider on demand.
export function registerDeferredSkills(ctx, plugins, invoke) {
  const rows = (plugins ?? []).flatMap(plugin =>
    (plugin.skills ?? []).map(skill => ({ plugin, skill })))
  if (!rows.length) return () => {}
  const unique = rows.filter(row => rows.filter(item => item.skill.name === row.skill.name).length === 1)
  return ctx.skills.registerProvider(() => ({
    name: 'movo-deferred-plugins',
    list: async () => unique.map(({ plugin, skill }) => ({
      name: skill.name, description: skill.description,
      rank: 100,
      source: skill.source || 'plugin', provider: 'movo-deferred-plugins',
      locator: { pluginId: plugin.installation_id, name: skill.name },
      invocation: { userInvocable: skill.userInvocable, modelInvocable: skill.modelInvocable },
    })),
    get: async (candidate, options) => {
      const row = unique.find(item => item.plugin.installation_id === candidate.locator?.pluginId &&
        item.skill.name === candidate.name)
      if (!row || !options.scope?.session) throw new Error('Plugin Skill requires an active conversation')
      return await invoke(row.plugin, row.skill.name, {}, {
        agent: options.scope, signal: options.signal, operation: 'skill',
      })
    },
  }))
}
