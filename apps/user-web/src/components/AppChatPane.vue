<script setup lang="ts">
import { computed, defineAsyncComponent } from 'vue'
import ChatWindowLoadError from './ChatWindowLoadError.vue'
import type { ChatRuntimePane } from '../composables/useChatRuntimeStore'
import type { CodePaneState } from '../composables/code/useDshCodeRuntime'
import type { AgentPolicySnapshot } from '../api/auth'
import type { DshTaskChangeSet, DshWorkspace } from '../platform/types'
import type { DesktopToolLauncherKind, DesktopToolTab } from './desktop/desktopToolTabs'
import { capabilities } from '../platform'

defineOptions({ inheritAttrs: false })

const ChatWindow = defineAsyncComponent({
  loader: () => import('./ChatWindow.vue'),
  errorComponent: ChatWindowLoadError,
  onError(_error, retry, fail, attempts) {
    if (attempts < 2) window.setTimeout(retry, 750)
    else fail()
  },
})

const props = defineProps<{
  pane: ChatRuntimePane
  serverRunUnattached: boolean
  codeState: CodePaneState
  active: boolean
  userId?: string
  mainId?: string
  authToken: string
  projectWorkspaces: readonly DshWorkspace[]
  projectWorkspacesLoading: boolean
  desktopBrowserRequest: number
  desktopToolTabs: DesktopToolTab[]
  desktopActiveTool: string | null
  desktopAvailableTools: DesktopToolLauncherKind[]
  desktopCodeReviewPath: string
  desktopCodeReviewChanges: DshTaskChangeSet | null
  desktopCodeFilePath: string
  agentPolicy?: AgentPolicySnapshot
}>()

const localFolderUnavailable = computed(() => Boolean(
  capabilities.localWorkspacePicker && props.pane.codeProject?.workspace_id &&
  props.projectWorkspaces.find(workspace => workspace.workspace_id === props.pane.codeProject?.workspace_id)?.status !== 'ok',
))
</script>

<template>
  <ChatWindow
    v-bind="$attrs"
    :initial-messages="pane.messages"
    :session-id="pane.sessionId || undefined"
    :model-instance-id="pane.modelInstanceId || undefined"
    :active="active"
    :shared="pane.shared"
    :user-id="userId"
    :main-id="mainId"
    :auth-token="authToken"
    :running="pane.running"
    :server-run-unattached="serverRunUnattached"
    :foreign-run="pane.foreignRun"
    :foreign-run-finished="pane.foreignRunFinished"
    :refreshing-session="pane.refreshingSession"
    :busy-notice="pane.busyNotice"
    :stopping="pane.stopping || codeState.stopping"
    :active-intervention="pane.activeIntervention"
    :code-workspace="codeState.workspace"
    :code-workspaces="projectWorkspaces"
    :code-workspaces-loading="projectWorkspacesLoading"
    :code-session="codeState.session"
    :code-events="codeState.events"
    :code-approvals="codeState.approvals"
    :code-approval-busy="codeState.approvalBusy"
    :code-error="codeState.error"
    :code-workspace-busy="codeState.busy"
    :code-worktree="codeState.worktree"
    :code-source-ref="codeState.sourceRef"
    :code-permission-mode="codeState.permissionMode"
    :code-history-read-only="pane.executionLocation !== 'server' && !codeState.session"
    :code-history-restoring="codeState.restoring"
    :code-history-location="pane.executionLocation === 'server' ? undefined : pane.executionLocation"
    :code-history-project="pane.codeProject"
    :code-history-local-folder-unavailable="localFolderUnavailable"
    :desktop-browser-request="desktopBrowserRequest"
    :browser-session-id="pane.sessionId || pane.key"
    :desktop-tool-tabs="desktopToolTabs"
    :desktop-active-tool="desktopActiveTool"
    :desktop-available-tools="active ? desktopAvailableTools : []"
    :desktop-code-review-path="active ? desktopCodeReviewPath : ''"
    :desktop-code-review-changes="active ? desktopCodeReviewChanges : null"
    :desktop-code-file-path="active ? desktopCodeFilePath : ''"
    :agent-policy="agentPolicy"
  />
</template>
