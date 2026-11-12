import type { PaneSendPayload } from '../../composables/usePaneTurnActions'
import type { CodePermissionMode, DshTaskChangeSet, DshWorkspace } from '../../platform/types'
import type { DesktopToolLauncherKind } from '../desktop/desktopToolTabs'
import type { DocumentInfo } from './types'

/** Commands supplied by the app coordinator to each visible chat pane. */
export interface AppChatPaneActions {
  send(key: string, payload: PaneSendPayload): unknown
  stop(key: string): unknown
  refreshSession(sessionId: string): unknown
  openSkills(): unknown
  openTools(): unknown
  openKnowledge(): unknown
  scheduleMessage(payload: { prompt: string; sessionId?: string }): unknown
  clearIntervention(key: string): unknown
  approvalDecided(): unknown
  chooseCodeWorkspace(key: string): unknown
  selectCodeWorkspace(key: string, workspace: DshWorkspace): unknown
  clearCodeWorkspace(key: string): unknown
  codeWorktree(key: string, enabled: boolean): unknown
  startLocalCodeTask(): unknown
  codeSourceRef(key: string, fullRef: string): unknown
  codePermissionMode(key: string, mode: CodePermissionMode): unknown
  codeBranchUpdated(key: string, branch: string): unknown
  codeApproval(key: string, approvalId: string, decision: 'approved' | 'rejected', scope: 'once' | 'session'): unknown
  closeCodePanel(): unknown
  selectDesktopTool(id: string): unknown
  closeDesktopTool(id: string): unknown
  openDesktopTool(kind: DesktopToolLauncherKind): unknown
  openDesktopFileTab(path: string): unknown
  openDesktopDiffTab(path: string, changes?: DshTaskChangeSet): unknown
  openDesktopPreviewTab(document: DocumentInfo): unknown
  codeWorkspaceChange(): unknown
  reviewCodeChanges(changes: DshTaskChangeSet, path?: string): unknown
  openCodeFile(path: string): unknown
}
