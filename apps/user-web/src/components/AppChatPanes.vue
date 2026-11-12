<script setup lang="ts">
import type { AgentPolicySnapshot } from '../api/auth'
import type { ChatRuntimePane } from '../composables/useChatRuntimeStore'
import type { CodePaneState } from '../composables/code/useDshCodeRuntime'
import type { DshTaskChangeSet, DshWorkspace } from '../platform/types'
import type { DesktopToolLauncherKind, DesktopToolTab } from './desktop/desktopToolTabs'
import type { AppChatPaneActions } from './chat/appChatPaneActions'
import AppChatPane from './AppChatPane.vue'

defineProps<{
  panes: ChatRuntimePane[]
  serverRunningSessionIds: ReadonlySet<string>
  activeKey: string
  codeStateFor: (key: string) => CodePaneState
  userId?: string
  mainId: string
  authToken: string
  projectWorkspaces: readonly DshWorkspace[]
  projectWorkspacesLoading: boolean
  desktopBrowserRequest: number
  desktopToolTabsFor: (key: string) => DesktopToolTab[]
  desktopActiveToolFor: (key: string) => string | null
  desktopAvailableTools: DesktopToolLauncherKind[]
  desktopCodeReviewPath: string
  desktopCodeReviewChanges: DshTaskChangeSet | null
  desktopCodeFilePath: string
  agentPolicy?: AgentPolicySnapshot
  actions: AppChatPaneActions
}>()
</script>

<template>
  <div
    v-for="pane in panes"
    v-show="pane.key === activeKey"
    :key="pane.key"
    class="h-full w-full"
  >
    <AppChatPane
      :pane="pane"
      :server-run-unattached="Boolean(pane.sessionId && serverRunningSessionIds.has(pane.sessionId) && !pane.running && !pane.foreignRun)"
      :code-state="codeStateFor(pane.key)"
      :active="pane.key === activeKey"
      :user-id="userId"
      :main-id="mainId"
      :auth-token="authToken"
      :project-workspaces="projectWorkspaces"
      :project-workspaces-loading="projectWorkspacesLoading"
      :desktop-browser-request="desktopBrowserRequest"
      :desktop-tool-tabs="desktopToolTabsFor(pane.key)"
      :desktop-active-tool="desktopActiveToolFor(pane.key)"
      :desktop-available-tools="desktopAvailableTools"
      :desktop-code-review-path="desktopCodeReviewPath"
      :desktop-code-review-changes="desktopCodeReviewChanges"
      :desktop-code-file-path="desktopCodeFilePath"
      :agent-policy="agentPolicy"
      @send="(payload) => actions.send(pane.key, payload)"
      @stop="actions.stop(pane.key)"
      @refresh-session="actions.refreshSession(pane.sessionId || '')"
      @open-skills="actions.openSkills()"
      @open-tools="actions.openTools()"
      @open-knowledge="actions.openKnowledge()"
      @schedule-message="actions.scheduleMessage($event)"
      @clear-intervention="actions.clearIntervention(pane.key)"
      @approval-decided="actions.approvalDecided()"
      @choose-code-workspace="actions.chooseCodeWorkspace(pane.key)"
      @select-code-workspace="actions.selectCodeWorkspace(pane.key, $event)"
      @clear-code-workspace="actions.clearCodeWorkspace(pane.key)"
      @code-worktree="actions.codeWorktree(pane.key, $event)"
      @start-local-code-task="actions.startLocalCodeTask()"
      @code-source-ref="actions.codeSourceRef(pane.key, $event)"
      @code-permission-mode="actions.codePermissionMode(pane.key, $event)"
      @code-branch-updated="actions.codeBranchUpdated(pane.key, $event)"
      @code-approval="(approvalId, decision, scope) => actions.codeApproval(pane.key, approvalId, decision, scope)"
      @close-code-panel="actions.closeCodePanel()"
      @select-desktop-tool="actions.selectDesktopTool($event)"
      @close-desktop-tool="actions.closeDesktopTool($event)"
      @open-desktop-tool="actions.openDesktopTool($event)"
      @open-desktop-file-tab="actions.openDesktopFileTab($event)"
      @open-desktop-diff-tab="(path, changes) => actions.openDesktopDiffTab(path, changes)"
      @open-desktop-preview-tab="actions.openDesktopPreviewTab($event)"
      @code-workspace-change="actions.codeWorkspaceChange()"
      @review-code-changes="(changes, path) => actions.reviewCodeChanges(changes, path)"
      @open-code-file="actions.openCodeFile($event)"
    />
  </div>
</template>
