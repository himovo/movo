import { t, translateSourceText } from '@/composables/i18n';

/** Translate dashboard messages that are returned as legacy human-readable text. */
export function translateDashboardText(value: string | null | undefined): string {
  const text = String(value || '');
  if (!text) return '';

  let match = text.match(/^(\d+) 个工具连接需要检查。$/);
  if (match) return t('legacy.tool_connections_need_attention', { count: match[1] });

  match = text.match(/^(\d+) 个工具尚未测试连通性。$/);
  if (match) return t('legacy.tools_have_not_been_connectivity_tested', { count: match[1] });

  match = text.match(/^(\d+) 个模型最近测试失败。$/);
  if (match) return t('legacy.models_failed_their_recent_health_checks', { count: match[1] });

  match = text.match(/^(\d+) 次调用失败，建议查看 Token 统计。$/);
  if (match) return t('legacy.calls_failed_review_token_statistics', { count: match[1] });

  return translateSourceText(text);
}
