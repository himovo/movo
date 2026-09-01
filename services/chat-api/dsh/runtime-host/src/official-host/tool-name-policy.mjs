// Model-facing names shipped by DSH 0.1.1-rc.2's official `code` preset.
// The pinned-preset compatibility test inventories this same surface. ASKAI
// enterprise tools must not shadow native Code semantics in a scoped catalog.
export const DSH_CODE_RESERVED_TOOL_NAMES = Object.freeze(new Set([
  'bash', 'read', 'write', 'edit', 'glob', 'grep',
  'job_output', 'job_list', 'job_kill',
  'skill', 'ask_user_question', 'web_search', 'read_image', 'todo_write',
  'get_goal', 'create_goal', 'update_goal',
  'send_message', 'interrupt_agent', 'list_agents',
  'workflow', 'ralph', 'exit_plan_mode', 'subagent', 'subagent_fork', 'run_code',
]))

export function assertNoDshCodeToolCollisions(descriptors) {
  const collisions = descriptors
    .map(item => item?.name)
    .filter(name => DSH_CODE_RESERVED_TOOL_NAMES.has(name))
  if (collisions.length > 0) {
    throw new Error(`MOVO enterprise tools collide with DSH Code tools: ${[...new Set(collisions)].join(', ')}`)
  }
}
