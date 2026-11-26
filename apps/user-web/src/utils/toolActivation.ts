import type { ExternalToolItem, ToolPayload } from '../api/tools';
import { t } from '../composables/i18n';

type ToolLike = Pick<ExternalToolItem, 'type' | 'status' | 'config' | 'discoveredTools' | 'name'>;

export function enabledMcpToolNames(config: Record<string, any> | undefined): string[] {
  const values = Array.isArray(config?.enabledToolNames) ? config?.enabledToolNames : [];
  return Array.from(new Set(values.map((item: unknown) => String(item || '').trim()).filter(Boolean)));
}

export function mcpActivationError(tool: ToolLike | ToolPayload): string {
  if (tool.type !== 'mcp' || tool.status !== 'active') return '';
  const names = enabledMcpToolNames(tool.config);
  if (names.length === 0) {
    return t('toolActivation.selectRequired');
  }
  return '';
}

export function nextMcpToolSelection(current: string[], name: string, checked: boolean): { names: string[]; error: string } {
  const normalized = String(name || '').trim();
  const currentNames = Array.from(new Set(current.map((item) => String(item || '').trim()).filter(Boolean)));
  if (!normalized) return { names: currentNames, error: '' };
  if (!checked) {
    return { names: currentNames.filter((item) => item !== normalized), error: '' };
  }
  if (currentNames.includes(normalized)) return { names: currentNames, error: '' };
  return { names: [...currentNames, normalized], error: '' };
}

export function toolStatusConfirmText(tool: ToolLike, enabled: boolean): string {
  const name = tool.name || t('toolActivation.unnamed');
  if (enabled) {
    return t('toolActivation.enableConfirm', { name });
  }
  return t('toolActivation.disableConfirm', { name });
}
