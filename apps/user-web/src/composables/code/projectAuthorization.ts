import type { DesktopProject, SessionSummary } from '../../api/sessions'
import type { DshWorkspace } from '../../platform/types'

/** Local workspace presence is not authorization; MOVO employee ownership is. */
export function reconcileUserBoundProjects(
  projects: readonly DesktopProject[],
  localWorkspaces: readonly DshWorkspace[],
  sessions: readonly SessionSummary[],
  fallbackTitle: (workspaceId: string) => string,
): DshWorkspace[] {
  const localById = new Map(localWorkspaces.map(workspace => [workspace.workspace_id, workspace]))
  const authorized = new Map<string, { title: string; updatedAt: string }>()

  for (const project of projects) {
    authorized.set(project.workspace_id, { title: project.title, updatedAt: project.updated_at })
  }
  for (const session of sessions) {
    const workspaceId = session.code_project?.workspace_id
    if (!workspaceId || authorized.has(workspaceId)) continue
    authorized.set(workspaceId, { title: fallbackTitle(workspaceId), updatedAt: session.updated_at })
  }

  return [...authorized.entries()].map(([workspaceId, binding]) => {
    const local = localById.get(workspaceId)
    if (local) return { ...local, title: binding.title || local.title }
    return {
      workspace_id: workspaceId,
      title: binding.title || fallbackTitle(workspaceId),
      path: '', status: 'missing-dir' as const, session_ids: [],
      created_at: binding.updatedAt || '', updated_at: binding.updatedAt || '',
    }
  }).sort((left, right) => right.updated_at.localeCompare(left.updated_at))
}

export function availableUserProjects(workspaces: readonly DshWorkspace[]): DshWorkspace[] {
  return workspaces.filter(workspace => workspace.status === 'ok')
}
