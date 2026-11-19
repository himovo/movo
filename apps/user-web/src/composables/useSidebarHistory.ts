import { computed, ref, watch, type Ref } from 'vue'
import type { UserProfile } from '../api/auth'
import type { SessionSummary } from '../api/sessions'
import type { DshWorkspace } from '../platform/types'
import { projectHistoryVisibility } from './code/projectHistoryVisibility'

const sidebarHistoryStateKey = 'askai.sidebar-history-state'

export function useSidebarHistory(options: {
  profile: Ref<UserProfile | null>
  sessions: Ref<SessionSummary[]>
  sharedSessions: Ref<SessionSummary[]>
  workspaces: Ref<DshWorkspace[]>
  workspaceTitles: Ref<Record<string, string>>
  canUseCode: Ref<boolean>
  supportsLocalCodeProjects: boolean
}) {
  const saved = (() => {
    try { return JSON.parse(localStorage.getItem(sidebarHistoryStateKey) || '{}') as Record<string, any> }
    catch { return {} }
  })()
  const normalHistoryExpanded = ref(saved.normal !== false)
  const sharedHistoryExpanded = ref(saved.shared !== false)
  const pinnedHistoryExpanded = ref(saved.pinnedExpanded !== false)
  const pinnedSessionIds = ref<string[]>([])
  const collapsedProjectHistory = ref<Record<string, boolean>>(saved.projects || {})
  const pinnedStorageKey = computed(() => {
    const userId = options.profile.value?.userId
    return userId == null ? '' : `askai.pinned-sessions.${String(options.profile.value?.mainId || 'default')}.${String(userId)}`
  })

  function isSessionPinned(id: string): boolean { return pinnedSessionIds.value.includes(id) }
  function toggleSessionPin(id: string): void {
    pinnedSessionIds.value = isSessionPinned(id)
      ? pinnedSessionIds.value.filter(item => item !== id)
      : [...pinnedSessionIds.value, id]
  }
  function projectHistoryExpanded(workspaceId: string): boolean {
    return !collapsedProjectHistory.value[workspaceId]
  }
  function toggleProjectHistory(workspaceId: string): void {
    collapsedProjectHistory.value = {
      ...collapsedProjectHistory.value,
      [workspaceId]: projectHistoryExpanded(workspaceId),
    }
  }

  const pinnedSessions = computed(() => pinnedSessionIds.value
    .map(id => options.sessions.value.find(session => session.id === id)
      || options.sharedSessions.value.find(session => session.id === id))
    .filter((session): session is SessionSummary => Boolean(session)))
  const visibleProjectHistory = computed(() => projectHistoryVisibility(
    options.sessions.value, options.workspaces.value, options.workspaceTitles.value,
  ))
  const historyItems = computed(() => visibleProjectHistory.value.ordinary)
  const projectHistoryGroups = computed(() => visibleProjectHistory.value.projects)
  function isUnavailableProjectHistory(sessionId: string): boolean {
    return options.supportsLocalCodeProjects && visibleProjectHistory.value.unavailableIds.has(sessionId)
  }

  watch([normalHistoryExpanded, sharedHistoryExpanded, pinnedHistoryExpanded, pinnedSessionIds, collapsedProjectHistory],
    ([normal, shared, pinnedExpanded, pinnedIds, projects]) => {
      localStorage.setItem(sidebarHistoryStateKey, JSON.stringify({ normal, shared, pinnedExpanded, projects }))
      if (pinnedStorageKey.value) localStorage.setItem(pinnedStorageKey.value, JSON.stringify(pinnedIds))
    }, { deep: true })
  watch(pinnedStorageKey, key => {
    try {
      const savedIds = key ? JSON.parse(localStorage.getItem(key) || '[]') : []
      pinnedSessionIds.value = Array.isArray(savedIds)
        ? savedIds.filter((id: unknown): id is string => typeof id === 'string') : []
    } catch { pinnedSessionIds.value = [] }
  }, { immediate: true })

  return {
    normalHistoryExpanded, sharedHistoryExpanded, pinnedHistoryExpanded,
    pinnedSessionIds, pinnedSessions, collapsedProjectHistory,
    isSessionPinned, toggleSessionPin, projectHistoryExpanded, toggleProjectHistory,
    historyItems, projectHistoryGroups, isUnavailableProjectHistory,
  }
}
