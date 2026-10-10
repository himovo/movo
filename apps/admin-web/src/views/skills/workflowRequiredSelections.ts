import type { WorkflowNodeDraft } from '@/api/skills';

export type RequiredSelectionError = {
  nodeId: string;
  messageKey: 'skills.workflow.selectKnowledgeDocument' | 'skills.workflow.selectTool';
};

export function missingWorkflowSelection(nodes: WorkflowNodeDraft[]): RequiredSelectionError | null {
  for (const node of nodes) {
    const config = node.businessConfig || {};
    if (node.type === 'read_material' && config.sourceType === 'knowledge_document'
      && !String(config.knowledgeSourceId || '').trim()) {
      return { nodeId: String(node.id || ''), messageKey: 'skills.workflow.selectKnowledgeDocument' };
    }
    if (node.type === 'call_tool'
      && !String(config.preferredToolId || config.externalToolId || config.toolId || '').trim()) {
      return { nodeId: String(node.id || ''), messageKey: 'skills.workflow.selectTool' };
    }
  }
  return null;
}
