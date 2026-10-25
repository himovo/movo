import type { LabelMap } from '../messages'

export const resourceAccessMessages: Record<string, LabelMap> = {
  'legacy.access': { 'zh-CN': '使用权限', 'en-US': 'Access' },
  'legacy.access_44b8122': { 'zh-CN': '{name} · 使用权限', 'en-US': '{name} · Access' },
  'legacy.skill_access': { 'zh-CN': 'Skill 使用权限', 'en-US': 'Skill Access' },
  'legacy.mcp_tool_access': { 'zh-CN': 'MCP / 工具使用权限', 'en-US': 'MCP / Tool Access' },
  'legacy.only_employees_matching_the_audience_can_see_and_use_bfbfd1b': { 'zh-CN': '只有命中适用对象的员工才能看到并使用该 Skill。', 'en-US': 'Only employees matching the audience can see and use this Skill.' },
  'legacy.tools_discovered_from_an_mcp_server_inherit_the_server': { 'zh-CN': 'MCP 服务下发现的工具默认继承该服务的适用对象。', 'en-US': 'Tools discovered from an MCP server inherit the server audience by default.' },
  'legacy.save_access': { 'zh-CN': '保存使用权限', 'en-US': 'Save Access' },
  'legacy.access_policy_saved': { 'zh-CN': '使用权限已保存', 'en-US': 'Access policy saved' },
  'legacy.failed_to_load_access_policy': { 'zh-CN': '加载使用权限失败', 'en-US': 'Failed to load access policy' },
  'legacy.failed_to_save_access_policy': { 'zh-CN': '保存使用权限失败', 'en-US': 'Failed to save access policy' },
  'legacy.configure_the_audience_for_each_skill_mcp_server_or': { 'zh-CN': '具体 Skill、MCP 与工具的使用对象，请在对应资源中配置。', 'en-US': 'Configure the audience for each Skill, MCP server, or tool on that resource.' },
}
