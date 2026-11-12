// Model-facing names admitted from DSH 0.2.2-rc.2's official Code
// `code` composition. Keep this collision boundary explicit when DSH adds a
// native tool; MOVO enterprise tools must not shadow native Code semantics.
// The pinned-preset compatibility test inventories this same surface. ASKAI
// keeps obsolete names reserved until the rollback train is retired.
export const DSH_CODE_RESERVED_TOOL_NAMES = Object.freeze(new Set([
  'bash', 'read', 'write', 'edit', 'glob', 'grep',
  'job_output', 'job_list', 'job_kill',
  'skill', 'ask_user_question', 'web_search', 'web_fetch', 'read_image', 'present', 'todo_write',
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
