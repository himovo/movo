export type ToolApprovalDecision = 'approved' | 'rejected'
export type ToolApprovalGrantScope = 'once' | 'session'

export interface PendingToolApproval {
  action_id: string
  conversation_id: string
  message_id?: string
  tool_name: string
  reason?: string
  arguments?: Record<string, any>
  scope_label?: string
  status: 'pending'
  created_at?: string
}

export async function listPendingToolApprovals(
  authToken: string,
  conversationId?: string,
): Promise<PendingToolApproval[]> {
  const query = new URLSearchParams()
  if (conversationId) query.set('conversation_id', conversationId)
  const response = await fetch(`/askai-api/api/dsh/tool-approvals${query.size ? `?${query}` : ''}`, {
    headers: { Authorization: `Bearer ${authToken}` },
  })
  if (!response.ok) throw new Error(`Approval recovery failed: ${response.status}`)
  const payload = await response.json()
  return Array.isArray(payload?.data) ? payload.data : []
}

export async function decideToolApproval(
  actionId: string,
  decision: ToolApprovalDecision,
  authToken: string,
  grantScope: ToolApprovalGrantScope = 'once',
): Promise<void> {
  const response = await fetch(
    `/askai-api/api/dsh/tool-approvals/${encodeURIComponent(actionId)}/decision`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${authToken}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ decision, grantScope }),
    },
  )
  if (response.ok) return
  const payload = await response.json().catch(() => ({}))
  const detail = payload?.detail
  throw new Error(typeof detail === 'string' ? detail : `Approval failed: ${response.status}`)
}
