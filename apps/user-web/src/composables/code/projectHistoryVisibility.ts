import type { SessionSummary } from '../../api/sessions'
import type { DshWorkspace } from '../../platform/types'
import { sortSessionsByRecentActivity } from '../../utils/sessionOrdering'

type ProjectGroup = { workspaceId: string; title: string; items: SessionSummary[] }

/** Only folders available on this device belong in the active Projects section. */
export function projectHistoryVisibility(
  sessions: readonly SessionSummary[],
  workspaces: readonly DshWorkspace[],
  titles: Readonly<Record<string, string>>,
): { ordinary: SessionSummary[]; projects: ProjectGroup[]; unavailableIds: Set<string> } {
  const available = new Map(workspaces.filter(item => item.status === 'ok').map(item => [item.workspace_id, item]))
  const grouped = new Map<string, SessionSummary[]>()
  const ordinary: SessionSummary[] = []
  const unavailableIds = new Set<string>()
  for (const session of sessions) {
    const workspaceId = session.code_project?.workspace_id
    if (!workspaceId) {
      ordinary.push(session)
    } else if (available.has(workspaceId)) {
      grouped.set(workspaceId, [...(grouped.get(workspaceId) || []), session])
    } else {
      ordinary.push(session)
      unavailableIds.add(session.id)
    }
  }
  const projects = [...available.values()]
    .sort((left, right) => right.updated_at.localeCompare(left.updated_at))
    .map(workspace => ({
      workspaceId: workspace.workspace_id,
      title: titles[workspace.workspace_id] || workspace.title,
      items: sortSessionsByRecentActivity(grouped.get(workspace.workspace_id) || []),
    }))
  return { ordinary: sortSessionsByRecentActivity(ordinary), projects, unavailableIds }
}
