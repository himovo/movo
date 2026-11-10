export function resolvePluginCommand(profile, selectedId, line) {
  const match = /^dsh_plugin_command:([0-9a-f]{24}):([A-Za-z0-9_-]+)$/.exec(String(selectedId || ''))
  const name = match ? Buffer.from(match[2], 'base64url').toString('utf8') : ''
  const plugin = match && profile?.plugins?.find(item => item.installation_id === match[1])
  const command = plugin?.commands?.find(item => item.name === name)
  if (!plugin || !command || !name || !String(line || '').startsWith(`/${name}`) ||
      !['', ' ', '\t', '\n'].includes(String(line || '')[`/${name}`.length] ?? '')) {
    throw new Error('selected plugin command is unavailable in this immutable Runtime Profile')
  }
  return { plugin, command }
}

export function requireCurrentCommand(commands, agent, selected) {
  const current = commands.list(agent).find(item => item.name === selected.command.name)
  if (!current || !selected.command.definitionId ||
      String(current.definitionId ?? '') !== selected.command.definitionId) {
    throw new Error('selected plugin command is not provided by the authorized plugin in this Session')
  }
  return current
}
