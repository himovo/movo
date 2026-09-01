import type { ExternalToolItem, ToolPayload } from '../api/tools';

export const MCP_ENABLED_TOOL_LIMIT = 50;

type ToolLike = Pick<ExternalToolItem, 'type' | 'status' | 'config' | 'discoveredTools' | 'name'>;

export function enabledMcpToolNames(config: Record<string, any> | undefined): string[] {
  const values = Array.isArray(config?.enabledToolNames) ? config?.enabledToolNames : [];
  return Array.from(new Set(values.map((item: unknown) => String(item || '').trim()).filter(Boolean)));
}

export function mcpActivationError(tool: ToolLike | ToolPayload): string {
  if (tool.type !== 'mcp' || tool.status !== 'active') return '';
  const names = enabledMcpToolNames(tool.config);
  if (names.length === 0) {
    return `请先选择允许 Agent 使用的 MCP 工具，最多 ${MCP_ENABLED_TOOL_LIMIT} 个。`;
  }
  if (names.length > MCP_ENABLED_TOOL_LIMIT) {
    return `MCP 已选择 ${names.length} 个工具，超过上限 ${MCP_ENABLED_TOOL_LIMIT} 个，请减少后再启用。`;
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
  if (currentNames.length >= MCP_ENABLED_TOOL_LIMIT) {
    return { names: currentNames, error: `最多只能选择 ${MCP_ENABLED_TOOL_LIMIT} 个 MCP 工具。` };
  }
  return { names: [...currentNames, normalized], error: '' };
}

export function toolStatusConfirmText(tool: ToolLike, enabled: boolean): string {
  const name = tool.name || '未命名工具';
  if (enabled) {
    return `确认启用「${name}」吗？启用后会参与 Agent / Skill 的工具选择。`;
  }
  return `确认禁用「${name}」吗？禁用后 Agent / Skill 将无法继续调用。`;
}
