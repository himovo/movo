import type { DshWorkspace } from '../../platform/types'

export type DraftProjectContext = {
  workspace: DshWorkspace
  worktree: boolean
  sourceRef: string
}

export type DraftProjectContextSource = {
  workspace: DshWorkspace | null
  worktree: boolean
  sourceRef: string
}

/** A new conversation inherits project configuration, never execution state. */
export function inheritedDraftProjectContext(
  source: DraftProjectContextSource,
): DraftProjectContext | null {
  if (!source.workspace) return null
  return {
    workspace: source.workspace,
    worktree: source.worktree,
    sourceRef: source.sourceRef || (source.workspace.git_branch
      ? `refs/heads/${source.workspace.git_branch}`
      : 'HEAD'),
  }
}
