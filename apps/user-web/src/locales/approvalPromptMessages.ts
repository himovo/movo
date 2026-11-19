export const approvalPromptMessages = {
  'approval.local_request': { zh: '此操作需要访问本机文件或执行命令，请确认后继续。', en: 'This action needs local file or command access. Review it before continuing.' },
  'approval.allow_once': { zh: '允许一次', en: 'Allow once' },
  'approval.allow_matching_session': { zh: '本会话允许此操作', en: 'Allow this action for this chat' },
  'approval.local_session_hint': { zh: '仅记住相同工具、参数和原因的批准，其他操作仍需确认。', en: 'Remember approval only for the same tool, arguments, and reason. Other actions still need review.' },
  'approval.session_hint': { zh: '在当前会话中允许相同授权范围的操作。', en: 'Allow actions within the same permission scope for this chat.' },
} as const
