export const conversationPluginMessages = {
  'plugins.onDemandPolicy': { zh: '按需模式在使用插件能力时准备环境。未运行期间的实时钩子和模型请求干预不生效，历史数据在使用时同步。', en: 'On-demand mode prepares a runtime on use. Live hooks and model request modifications are inactive while unloaded. History is synchronized on use.' },
  'plugins.conversationViews': { zh: '会话插件', en: 'Conversation plugins' },
  'plugins.conversationViewsUnavailable': { zh: '当前会话的插件视图暂不可用', en: 'Plugin views are unavailable for this conversation' },
  'plugins.checkingConversationViews': { zh: '正在检查会话视图…', en: 'Checking conversation views…' },
  'plugins.noConversationViews': { zh: '暂无可用的会话视图', en: 'No conversation views available' },
} as const
