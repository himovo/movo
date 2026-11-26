export const toolActivationMessages = {
  'shortcuts.skillPromptDefault': { zh: '请使用 Skill「{name}」完成以下任务：', en: 'Use the Skill “{name}” to complete this task:' },
  'toolActivation.selectRequired': { zh: '\u8bf7\u5148\u9009\u62e9\u5141\u8bb8 Agent \u4f7f\u7528\u7684 MCP \u5de5\u5177\u3002', en: 'Select MCP tools for the Agent first.' },
  'toolActivation.unnamed': { zh: '未命名工具', en: 'Unnamed tool' },
  'toolActivation.enableConfirm': { zh: '确认启用「{name}」吗？启用后会参与 Agent / Skill 的工具选择。', en: 'Enable “{name}”? Agents and Skills will be able to select it.' },
  'toolActivation.disableConfirm': { zh: '确认禁用「{name}」吗？禁用后 Agent / Skill 将无法继续调用。', en: 'Disable “{name}”? Agents and Skills will no longer be able to call it.' },
} as const
