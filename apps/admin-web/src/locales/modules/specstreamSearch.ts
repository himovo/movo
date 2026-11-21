import type { LabelMap } from '../messages';

export const specstreamSearchMessages: Record<string, LabelMap> = {
  'search.specstream.description': {
    'zh-CN': '使用 SpecStream Search API 检索实时网页，支持快速模式。',
    'en-US': 'Search the live web with the SpecStream Search API in fast mode.',
  },
  'search.specstream.signIn': { 'zh-CN': '登录 SpecStream 控制台', 'en-US': 'Sign in to SpecStream Workspace' },
  'search.specstream.createKey': {
    'zh-CN': '在 Agents & API 页面创建带有 finds:spend 权限的 API Key',
    'en-US': 'Create an API key with the finds:spend scope under Agents & API',
  },
  'search.specstream.test': { 'zh-CN': '将 Key 填入 MOVO 并测试搜索', 'en-US': 'Enter the key in MOVO and test search' },
  'search.specstream.billing': {
    'zh-CN': 'MOVO 默认以 fast 模式调用 SpecStream Search API，仅按实际返回的搜索结果计费。',
    'en-US': 'MOVO calls the SpecStream Search API in fast mode using your configured SpecStream key.',
  },
};
