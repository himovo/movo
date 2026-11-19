import type { SessionSummary } from '../../api/sessions'
import type { DshWorkspace } from '../../platform/types'
import { sortSessionsByRecentActivity } from '../../utils/sessionOrdering'

export type ProjectGroup = {
  workspaceId: string
  title: string
  items: SessionSummary[]
  location?: 'local' | 'other'
  unavailable?: boolean
}

/** Execution availability never changes a Code task into an ordinary chat. */
export function projectHistoryVisibility(
  sessions: readonly SessionSummary[],
  workspaces: readonly DshWorkspace[],
  titles: Readonly<Record<string, string>>,
): { ordinary: SessionSummary[]; projects: ProjectGroup[]; unavailableIds: Set<string> } {
  const local = new Map(workspaces.filter(item => Boolean(item.path)).map(item => [item.workspace_id, item]))
  const groups = new Map<string, ProjectGroup>()
  const ordinary: SessionSummary[] = []
  const unavailableIds = new Set<string>()
  for (const workspace of local.values()) {
    groups.set(`local:${workspace.workspace_id}`, {
      workspaceId: workspace.workspace_id, title: titles[workspace.workspace_id] || workspace.title,
      location: 'local', unavailable: workspace.status !== 'ok', items: [],
    })
  }
  for (const session of sessions) {
    const workspaceId = session.code_project?.workspace_id
    const isCode = Boolean(session.code_project) || session.runtime_preset_id === 'code'
      || session.execution_location === 'desktop' || session.execution_location === 'remote_sandbox'
    if (!isCode) { ordinary.push(session); continue }
    const workspace = workspaceId ? local.get(workspaceId) : undefined
    const location = workspace && session.execution_location !== 'remote_sandbox' ? 'local' : 'other'
    if (location !== 'local' || workspace?.status !== 'ok') unavailableIds.add(session.id)
    const key = `${location}:${workspaceId || session.id}`
    const group = groups.get(key) || {
      workspaceId: location === 'local' ? workspaceId! : key,
      title: workspaceId ? titles[workspaceId] || workspaces.find(item => item.workspace_id === workspaceId)?.title || workspaceId.slice(0, 8) : session.title,
      location, unavailable: location !== 'local' || workspace?.status !== 'ok', items: [],
    }
    group.items.push(session)
    groups.set(key, group)
  }
  const projects = [...groups.values()].map(group => ({ ...group, items: sortSessionsByRecentActivity(group.items) }))
  return { ordinary: sortSessionsByRecentActivity(ordinary), projects, unavailableIds }
}
