export type SearchProviderId = 'tavily' | 'serper' | 'serpapi' | 'baidu_qianfan' | 'volc_ark';

export interface SearchProviderGuide {
  url: string;
  steps: string[];
  note?: string;
}

export const searchProviderGuides: Record<SearchProviderId, SearchProviderGuide> = {
  tavily: {
    url: 'https://app.tavily.com/',
    steps: ['注册或登录 Tavily', '在控制台创建 API Key', '复制 Key 到 MOVO 并测试连接'],
  },
  serper: {
    url: 'https://serper.dev/',
    steps: ['注册或登录 Serper', '进入 Dashboard 获取 API Key', '复制 Key 到 MOVO 并测试连接'],
  },
  serpapi: {
    url: 'https://serpapi.com/manage-api-key',
    steps: ['注册或登录 SerpAPI', '进入 Dashboard 的 API Key 页面', '复制 Private API Key 到 MOVO 并测试连接'],
  },
  baidu_qianfan: {
    url: 'https://console.bce.baidu.com/qianfan/ais/console/apiKey',
    steps: ['登录百度智能云千帆控制台', '在安全认证中创建 API Key', '为 Key 开通百度搜索能力后复制到 MOVO'],
    note: '百度搜索能力可能需要开通计费；Endpoint 通常保持默认值。',
  },
  volc_ark: {
    url: 'https://console.volcengine.com/ark/region:ark+cn-beijing/apikey',
    steps: ['登录火山方舟并创建 API Key', '创建启用了联网能力的应用 Bot', '将 API Key 与 bot- 开头的应用 ID 填入 MOVO'],
    note: '仅有 API Key 不够，还需要填写已启用联网能力的 Bot Model。',
  },
};

export function isSearchProviderId(value: string): value is SearchProviderId {
  return Object.prototype.hasOwnProperty.call(searchProviderGuides, value);
}
