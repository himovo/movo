export type SearchProviderId = 'deepseek' | 'tavily' | 'serper' | 'serpapi' | 'baidu_qianfan' | 'volc_ark';

export interface SearchProviderGuide {
  url: string;
  steps: string[];
  note?: string;
}

export const searchProviderGuides: Record<SearchProviderId, SearchProviderGuide> = {
  deepseek: {
    url: 'https://platform.deepseek.com/api_keys',
    steps: ['search.deepseek.signIn', 'search.deepseek.createKey', 'search.deepseek.test'],
    note: 'search.deepseek.billing',
  },
  tavily: {
    url: 'https://app.tavily.com/',
    steps: ['legacy.sign_up_for_or_sign_in_to_tavily', 'legacy.create_an_api_key_in_the_dashboard', 'legacy.copy_the_key_to_movo_and_test_the_connection'],
  },
  serper: {
    url: 'https://serper.dev/',
    steps: ['legacy.sign_up_for_or_sign_in_to_serper', 'legacy.get_the_api_key_from_the_dashboard', 'legacy.copy_the_key_to_movo_and_test_the_connection'],
  },
  serpapi: {
    url: 'https://serpapi.com/manage-api-key',
    steps: ['legacy.sign_up_for_or_sign_in_to_serpapi', 'legacy.open_the_api_key_page_in_the_dashboard', 'legacy.copy_the_private_api_key_to_movo_and_test'],
  },
  baidu_qianfan: {
    url: 'https://console.bce.baidu.com/qianfan/ais/console/apiKey',
    steps: ['legacy.sign_in_to_the_baidu_qianfan_console', 'legacy.create_an_api_key_under_security_authentication', 'legacy.enable_baidu_search_for_the_key_then_copy_it'],
    note: 'legacy.baidu_search_may_require_billing_the_default_endpoint_normally',
  },
  volc_ark: {
    url: 'https://console.volcengine.com/ark/region:ark+cn-beijing/apikey',
    steps: ['legacy.sign_in_to_volcengine_ark_and_create_an_api', 'legacy.create_an_application_bot_with_web_access_enabled', 'legacy.enter_the_api_key_and_the_bot_application_id'],
    note: 'legacy.an_api_key_alone_is_not_enough_enter_a',
  },
};

export function isSearchProviderId(value: string): value is SearchProviderId {
  return Object.prototype.hasOwnProperty.call(searchProviderGuides, value);
}
