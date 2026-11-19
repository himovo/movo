import { ref, type Ref } from 'vue'
import { createDesktopProject } from '../../api/sessions'
import type { UserProfile } from '../../api/auth'
import { renameDshWorkspace, selectDshWorkspace } from '../../platform'
import type { DshWorkspace } from '../../platform/types'
import { t } from '../i18n'

type ProjectCreationOptions = {
  canUseCode: Ref<boolean>
  localWorkspacePicker: boolean
  currentView: Ref<string>
  activeChatKey: Ref<string>
  token: Ref<string>
  profile: Ref<UserProfile | null>
  syncIdentity: (token: string, userId: string | number | null | undefined) => Promise<boolean>
  onAuthExpired: () => void
  getPane: (key: string) => { key: string } | undefined
  startLocalSession: () => { key: string }
  setDraftProject: (key: string, workspace: DshWorkspace, worktree: boolean) => void
  addBinding: (binding: Awaited<ReturnType<typeof createDesktopProject>>, workspace: DshWorkspace) => void
  historyReference?: (key?: string) => string
  setHistoryReference?: (key: string, reference: string) => void
  navigateToChat: () => void
}

export function useProjectCreation(options: ProjectCreationOptions) {
  let pendingHistoryReference = ''
  const createProjectOpen = ref(false)
  const createProjectBusy = ref(false)
  const createProjectSelecting = ref(false)
  const createProjectSelectionPhase = ref('')
  const createProjectSelectionError = ref('')
  const createProjectWorkspace = ref<DshWorkspace | null>(null)
  const createProjectWorktree = ref(false)
  const createProjectTargetKey = ref<string | null>(null)

  function openProjectCreate(targetKey: string | null): void {
    if (!options.canUseCode.value || !options.localWorkspacePicker) return
    pendingHistoryReference = ''
    createProjectTargetKey.value = targetKey
    createProjectWorkspace.value = null
    createProjectSelectionError.value = ''
    createProjectWorktree.value = false
    createProjectOpen.value = true
  }

  function addProjectToActiveConversation(): void {
    if (options.canUseCode.value && options.currentView.value === 'chat') openProjectCreate(options.activeChatKey.value)
  }

  function createProject(): void { openProjectCreate(null) }

  function createProjectFromHistory(key?: string): void {
    const reference = options.historyReference?.(key) || ''
    openProjectCreate(null)
    if (createProjectOpen.value) pendingHistoryReference = reference
  }

  function closeProjectCreate(): void {
    createProjectOpen.value = false
    createProjectTargetKey.value = null
    pendingHistoryReference = ''
  }

  async function chooseProjectFolder(): Promise<void> {
    if (createProjectSelecting.value) return
    const selectionToken = options.token.value
    const startedAt = performance.now()
    const trace = (stage: string) => console.info('[desktop-workspace-select-ui]', { stage, elapsedMs: Math.round(performance.now() - startedAt) })
    createProjectSelecting.value = true
    createProjectSelectionError.value = ''
    createProjectSelectionPhase.value = t('app.desktopChecking')
    try {
      trace('identity-sync-starting')
      const identityReady = await Promise.race([
        options.syncIdentity(options.token.value, options.profile.value?.userId),
        new Promise<false>((resolve) => setTimeout(() => resolve(false), 15000)),
      ])
      trace(identityReady ? 'identity-sync-ready' : 'identity-sync-failed')
      if (!identityReady) throw new Error(t('app.desktopLoginUnavailable'))
      createProjectSelectionPhase.value = t('app.chooseFolder')
      trace('workspace-select-invoking')
      const workspace = await selectDshWorkspace()
      trace(workspace ? 'workspace-select-completed' : 'workspace-select-cancelled')
      if (workspace) createProjectWorkspace.value = workspace
    } catch (error) {
      trace('workspace-select-failed')
      const message = error instanceof Error ? error.message : String(error)
      if (message.includes('[MOVO_AUTH_EXPIRED]') && options.token.value === selectionToken) options.onAuthExpired()
      createProjectSelectionError.value = message.replace('[MOVO_AUTH_EXPIRED]', '').trim()
    } finally {
      createProjectSelecting.value = false
      createProjectSelectionPhase.value = ''
    }
  }

  function workspaceFolderName(workspace: DshWorkspace): string {
    const normalizedPath = workspace.path.replace(/[\\/]+$/, '')
    return normalizedPath.split(/[\\/]/).pop() || workspace.title
  }

  async function commitProjectCreate(): Promise<void> {
    const workspace = createProjectWorkspace.value
    const title = workspace ? workspaceFolderName(workspace) : ''
    if (!workspace || !title || createProjectBusy.value) return
    createProjectBusy.value = true
    const token = options.token.value
    const identity = `${options.profile.value?.mainId}:${options.profile.value?.userId}`
    const assertIdentity = () => {
      if (token !== options.token.value || identity !== `${options.profile.value?.mainId}:${options.profile.value?.userId}`) {
        throw new Error(t('code.history.account_changed'))
      }
    }
    try {
      const renamed = workspace.title === title ? workspace : await renameDshWorkspace(workspace.workspace_id, title)
      assertIdentity()
      const binding = await createDesktopProject({
        workspace_id: renamed.workspace_id,
        title: renamed.title,
        worktree: createProjectWorktree.value,
      }, token || null)
      assertIdentity()
      const targetKey = createProjectTargetKey.value
      const pane = targetKey ? options.getPane(targetKey) : options.startLocalSession()
      if (!pane) throw new Error('the target conversation is no longer available')
      options.setDraftProject(pane.key, renamed, createProjectWorktree.value)
      options.setHistoryReference?.(pane.key, pendingHistoryReference)
      options.addBinding(binding, renamed)
      closeProjectCreate()
      options.navigateToChat()
    } finally { createProjectBusy.value = false }
  }

  return {
    createProjectOpen, createProjectBusy, createProjectSelecting,
    createProjectSelectionPhase, createProjectSelectionError,
    createProjectWorkspace, createProjectWorktree,
    addProjectToActiveConversation, createProject, createProjectFromHistory, openProjectCreate,
    closeProjectCreate, chooseProjectFolder, commitProjectCreate,
  }
}
