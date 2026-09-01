import { ref, type Ref } from 'vue'
import type { DesktopProject, SessionSummary } from '../../api/sessions'
import { listDesktopProjects } from '../../api/sessions'
import { listDshWorkspaces } from '../../platform'
import type { DshWorkspace } from '../../platform/types'
import { reconcileUserBoundProjects } from './projectAuthorization'

interface UserBoundProjectOptions {
  authToken: Ref<string>
  canUseCode: Ref<boolean>
  localWorkspacePicker: boolean
  identity: () => string
  sessions: Ref<SessionSummary[]>
  fallbackTitle: (workspaceId: string) => string
}

/** Owns the account boundary for desktop projects and rejects stale responses. */
export function useUserBoundProjects(options: UserBoundProjectOptions) {
  const bindings = ref<DesktopProject[]>([])
  const workspaces = ref<DshWorkspace[]>([])
  const titles = ref<Record<string, string>>({})
  const loading = ref(false)
  const loadedIdentity = ref('')
  let refreshEpoch = 0

  function clear(): void {
    refreshEpoch += 1
    loadedIdentity.value = ''
    bindings.value = []
    workspaces.value = []
    titles.value = {}
    loading.value = false
  }

  function add(binding: DesktopProject, workspace: DshWorkspace): void {
    bindings.value = [binding, ...bindings.value.filter(item => item.workspace_id !== binding.workspace_id)]
    workspaces.value = [workspace, ...workspaces.value.filter(item => item.workspace_id !== workspace.workspace_id)]
    titles.value = { ...titles.value, [workspace.workspace_id]: workspace.title }
  }

  async function refresh(): Promise<void> {
    if (!options.canUseCode.value || !options.localWorkspacePicker) return
    const identity = options.identity()
    const token = options.authToken.value
    if (!identity || !token) return
    refreshEpoch += 1
    if (loadedIdentity.value !== identity) clear()
    const activeEpoch = refreshEpoch
    loading.value = true
    try {
      const nextBindings = await listDesktopProjects(token)
      let localWorkspaces: DshWorkspace[] = []
      try { localWorkspaces = await listDshWorkspaces() }
      catch { /* Server-owned projects remain visible as unavailable on this device. */ }
      if (activeEpoch !== refreshEpoch || identity !== options.identity() || token !== options.authToken.value) return
      const nextWorkspaces = reconcileUserBoundProjects(
        nextBindings, localWorkspaces, options.sessions.value, options.fallbackTitle,
      )
      bindings.value = nextBindings
      workspaces.value = nextWorkspaces
      titles.value = Object.fromEntries(nextWorkspaces.map(workspace => [workspace.workspace_id, workspace.title]))
      loadedIdentity.value = identity
    } catch { /* Keep the last same-employee snapshot on a control-plane outage. */ }
    finally {
      if (activeEpoch === refreshEpoch) loading.value = false
    }
  }

  return { bindings, workspaces, titles, loading, identity: options.identity, clear, add, refresh }
}
