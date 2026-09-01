<script setup lang="ts">
import { darkTheme, NButton, NConfigProvider, NDialogProvider, NInput, NMessageProvider, NNotificationProvider, NSelect } from 'naive-ui'
import TokenInput from './components/TokenInput.vue'
import LoginModal from './components/LoginModal.vue'
import SettingsPanel from './components/SettingsPanel.vue'
import TokenUsagePage from './components/TokenUsagePage.vue'
import BillingModal from './components/BillingModal.vue'
import ProfileModal from './components/ProfileModal.vue'
import CreateOrganizationModal from './components/CreateOrganizationModal.vue'
import DesktopWindowChrome from './components/desktop/DesktopWindowChrome.vue'
import DesktopServerSetup from './components/desktop/DesktopServerSetup.vue'
import type { DesktopToolTabKind } from './components/desktop/desktopToolTabs'
import CreateProjectDialog from './components/code/CreateProjectDialog.vue'
import { fetchOrgBilling, fetchUserProfile, getAdminSSOToken, logoutWithToken, switchTenant, type TenantCandidate, type UserProfile } from './api/auth'
import { AUTH_EXPIRED_EVENT } from './api/authExpiry'
import { activateEmbeddedBrowserSession, capabilities, getDshWorkspaceSummary, getSettings, updateSettings, startAgent, getAgentStatus, openResource, selectEmbeddedBrowserSession, selectDshWorkspace, renameDshWorkspace } from './platform'
import type { DshTaskChangeSet, DshWorkspace, DshWorkspaceSummary } from './platform/types'
import {
  createDesktopProject,
  deleteSession,
  listSessionsPaged,
  searchSessions,
  updateSessionTitle,
  type SessionSearchResult,
  type SessionSummary,
} from './api/sessions'
import { deleteSkill, enrichSkillDraft, generateSkill, listSkills, updateSkill, uploadSkillSource } from './api/skills'
import { computed, defineAsyncComponent, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { setLocale as setAppLocale, t, useLocale, type Locale } from './composables/i18n'
import { getBrowserTimezone, setAppTimezone } from './composables/appTimezone'
import { buildAdminSsoUrl } from './utils/adminUrl'
import { sortSessionsByRecentActivity } from './utils/sessionOrdering'
import { formatExactTokenAmount, formatQuotaUsagePercent, formatTokenAmount, quotaUsagePercent } from './utils/tokenNumberFormat'
import { useChatRuntimeStore, type PendingRuntimeDocument } from './composables/useChatRuntimeStore'
import { useDshCodeRuntime } from './composables/code/useDshCodeRuntime'
import { useUserBoundProjects } from './composables/code/userBoundProjects'
import { availableUserProjects } from './composables/code/projectAuthorization'
import { useEnterpriseAccessPolicy } from './composables/useEnterpriseAccessPolicy'
import { useProfileRefreshOnResume } from './composables/useProfileRefreshOnResume'
import { useDesktopToolTabs } from './composables/desktop/useDesktopToolTabs'

const ChatWindow = defineAsyncComponent(() => import('./components/ChatWindow.vue'))
const SkillsPage = defineAsyncComponent(() => import('./components/MySkillsPage.vue'))
const ToolsPage = defineAsyncComponent(() => import('./components/MyToolsPage.vue'))
const SkillConfigPage = defineAsyncComponent(() => import('./components/MySkillConfigPage.vue'))
const CompositeSkillEditor = defineAsyncComponent(() => import('./components/CompositeSkillEditor.vue'))
const ScheduledTaskPage = defineAsyncComponent(() => import('./components/scheduled-tasks/ScheduledTaskPage.vue'))

const currentModel = ref('openAI GPT5.2')

const authTokenKey = 'auth_token'
const authAccountKey = 'auth_account'
const authUsersKey = 'auth_users'
const authUserProfileKey = 'auth_user_profile'

const loginOpen = ref(false)
const billingOpen = ref(false)
const profileOpen = ref(false)
const createOrganizationOpen = ref(false)
const authToken = ref('')
const currentAccount = ref('')
const savedUsers = ref<string[]>([])
const userProfile = ref<UserProfile | null>(null)
const userMenuOpen = ref(false)
const switchingTenant = ref(false)
const adminSsoStarting = ref(false)
const billingSummary = ref<any>(null)
const billingSummaryLoading = ref(false)
const billingSummaryLoaded = ref(false)
const settingsPanelOpen = ref(false)
const desktopServerState = ref<'checking' | 'required' | 'ready'>(capabilities.isDesktop ? 'checking' : 'ready')
const personalizationOpen = ref(false)
type ThemeMode = 'light' | 'dark' | 'system'
const themeModeKey = 'askai.theme-mode'
const storedThemeMode = localStorage.getItem(themeModeKey)
const themeMode = ref<ThemeMode>(
  storedThemeMode === 'light' || storedThemeMode === 'dark' || storedThemeMode === 'system'
    ? storedThemeMode
    : 'system',
)
const isDarkTheme = ref(false)
let systemThemeMedia: MediaQueryList | null = null
const themeOptions = [
  { value: 'light' as const, langKey: 'ui.theme.light', icon: 'sun' },
  { value: 'dark' as const, langKey: 'ui.theme.dark', icon: 'moon' },
  { value: 'system' as const, langKey: 'ui.theme.system', icon: 'system' },
]
const languageOptions = [
  { value: 'zh' as const, label: '中文' },
  { value: 'en' as const, label: 'English' },
]
const languageSaving = ref(false)
const timezoneSaving = ref(false)
const timezoneValue = ref(getBrowserTimezone())
const sessions = ref<SessionSummary[]>([])
const sessionsLoading = ref(false)
const sessionsLoadingMore = ref(false)
const sessionsHasMore = ref(false)
const sessionSearchOpen = ref(false)
const sessionSearchQuery = ref('')
const sessionSearchResults = ref<SessionSearchResult[]>([])
const sessionSearchLoading = ref(false)
const sessionSearchHasMore = ref(false)
const sessionSearchDidRun = ref(false)
const deletingSessionId = ref<string | null>(null)
const pendingDeleteSession = ref<SessionSummary | SessionSearchResult | null>(null)
const editingSessionId = ref<string | null>(null)
const editingSessionTitle = ref('')
const renamingSessionId = ref<string | null>(null)
const currentView = ref<'chat' | 'skills' | 'tools' | 'skill-config' | 'composite-editor' | 'token-usage' | 'scheduled-tasks'>('chat')
const scheduledTaskInitialPrompt = ref('')
const scheduledTaskInitialSessionId = ref<string | null>(null)
const scheduledTaskCreateRequestKey = ref(0)
const skills = ref<any[]>([])
const skillsLoading = ref(false)
const skillFormOpen = ref(false)
const skillName = ref('')
const skillSummary = ref('')
const skillCategory = ref('Analysis & Reports')
const skillType = ref('style')
const skillScenario = ref('')
const skillChannels = ref<string[]>(['generic'])
const skillForms = ref<string[]>(['article'])
const skillAudience = ref<string[]>(['general_public'])
const skillStyle = ref<string[]>(['professional'])
const skillRequired = ref<string[]>([])
const skillForbidden = ref<string[]>([])
const skillKnowledge = ref<any[]>([])
const skillTemplates = ref<any[]>([])
const skillTools = ref<any[]>([])
const skillCreating = ref(false)
const skillEnriching = ref(false)
const selectedSkill = ref<any | null>(null)
const sessionPageSize = 30
const sessionSearchPageSize = 20
let sessionSearchTimer: ReturnType<typeof setTimeout> | null = null
let sessionRefreshTimer: ReturnType<typeof setInterval> | null = null

const { locale } = useLocale()
const timezoneOptions = computed(() => [
  {
    label: locale.value === 'en'
      ? 'China Standard Time (GMT+8) - Asia/Shanghai'
      : '中国标准时间 (GMT+8) - Asia/Shanghai',
    value: 'Asia/Shanghai',
  },
  {
    label: locale.value === 'en'
      ? 'Japan Standard Time (GMT+9) - Asia/Tokyo'
      : '日本标准时间 (GMT+9) - Asia/Tokyo',
    value: 'Asia/Tokyo',
  },
  {
    label: locale.value === 'en'
      ? 'Coordinated Universal Time (UTC) - UTC'
      : '协调世界时 (UTC) - UTC',
    value: 'UTC',
  },
  {
    label: locale.value === 'en'
      ? 'Central European Time (GMT+1) - Europe/Berlin'
      : '欧洲中部时间 (GMT+1) - Europe/Berlin',
    value: 'Europe/Berlin',
  },
  {
    label: locale.value === 'en'
      ? 'Greenwich Mean Time (GMT) - Europe/London'
      : '格林威治标准时间 (GMT) - Europe/London',
    value: 'Europe/London',
  },
  {
    label: locale.value === 'en'
      ? 'Eastern Standard Time (GMT-5) - America/New_York'
      : '美国东部时间 (GMT-5) - America/New_York',
    value: 'America/New_York',
  },
  {
    label: locale.value === 'en'
      ? 'Central Standard Time (GMT-6) - America/Chicago'
      : '美国中部时间 (GMT-6) - America/Chicago',
    value: 'America/Chicago',
  },
  {
    label: locale.value === 'en'
      ? 'Pacific Standard Time (GMT-8) - America/Los_Angeles'
      : '太平洋时间 (GMT-8) - America/Los_Angeles',
    value: 'America/Los_Angeles',
  },
  {
    label: locale.value === 'en'
      ? 'Australian Eastern Standard Time (GMT+10) - Australia/Sydney'
      : '澳大利亚东部时间 (GMT+10) - Australia/Sydney',
    value: 'Australia/Sydney',
  },
])

const isLoggedIn = computed(() => Boolean(authToken.value))
const availableTenants = computed<TenantCandidate[]>(() => userProfile.value?.availableTenants || [])
const {
  canUseCode,
  canUseBrowser,
  canUseKnowledge,
  canUseSkills,
  canUseTools,
  canAccessAdmin,
  isEnterpriseSpace,
  canCreateOrganization,
  canUpgradePlan,
} = useEnterpriseAccessPolicy(userProfile)
const supportsLocalCodeProjects = capabilities.localDshRuntime && capabilities.localWorkspacePicker
const canSmartFillSkill = computed(() => Boolean(skillName.value.trim() && (skillSummary.value.trim() || skillScenario.value.trim())))
const trimmedSessionSearchQuery = computed(() => sessionSearchQuery.value.trim())
const userBoundProjects = useUserBoundProjects({
  authToken,
  canUseCode,
  localWorkspacePicker: capabilities.localWorkspacePicker,
  identity: () => {
    const userId = userProfile.value?.userId
    return userId === undefined || userId === null
      ? ''
      : `${String(userProfile.value?.mainId || 'default')}:${String(userId)}`
  },
  sessions,
  fallbackTitle: workspaceId => `${locale.value === 'en' ? 'Project' : '项目'} · ${workspaceId.slice(0, 8)}`,
})
const workspaceTitles = userBoundProjects.titles
const projectWorkspaces = userBoundProjects.workspaces
const projectWorkspacesLoading = userBoundProjects.loading
const sidebarHistoryStateKey = 'askai.sidebar-history-state'
const savedSidebarHistoryState = (() => {
  try { return JSON.parse(localStorage.getItem(sidebarHistoryStateKey) || '{}') as Record<string, any> } catch { return {} }
})()
const normalHistoryExpanded = ref(savedSidebarHistoryState.normal !== false)
const collapsedProjectHistory = ref<Record<string, boolean>>(savedSidebarHistoryState.projects || {})
function projectHistoryExpanded(workspaceId: string): boolean { return !collapsedProjectHistory.value[workspaceId] }
function toggleProjectHistory(workspaceId: string): void { collapsedProjectHistory.value = { ...collapsedProjectHistory.value, [workspaceId]: projectHistoryExpanded(workspaceId) } }
const historyItems = computed(() => sortSessionsByRecentActivity(
  sessions.value.filter((session) => !supportsLocalCodeProjects || !session.code_project?.workspace_id),
))
const projectHistoryGroups = computed(() => {
  if (!canUseCode.value || !supportsLocalCodeProjects) return []
  const sessionsByWorkspace = new Map<string, SessionSummary[]>()
  sessions.value.filter((session) => session.code_project?.workspace_id).forEach((session) => {
    const workspaceId = session.code_project!.workspace_id
    sessionsByWorkspace.set(workspaceId, [...(sessionsByWorkspace.get(workspaceId) || []), session])
  })
  const knownWorkspaces = new Map(projectWorkspaces.value.map((workspace) => [workspace.workspace_id, workspace]))
  for (const workspaceId of sessionsByWorkspace.keys()) {
    if (!knownWorkspaces.has(workspaceId)) {
      knownWorkspaces.set(workspaceId, {
        workspace_id: workspaceId,
        title: workspaceTitles.value[workspaceId] || `${locale.value === 'en' ? 'Project' : '项目'} · ${workspaceId.slice(0, 8)}`,
        path: '', status: 'missing-dir', session_ids: [], created_at: '', updated_at: '',
      })
    }
  }
  return [...knownWorkspaces.values()]
    .sort((left, right) => right.updated_at.localeCompare(left.updated_at))
    .map((workspace) => {
      const items = sortSessionsByRecentActivity(sessionsByWorkspace.get(workspace.workspace_id) || [])
      return {
        workspaceId: workspace.workspace_id,
        title: workspaceTitles.value[workspace.workspace_id] || workspace.title,
        items,
      }
    })
})
const chatRuntime = useChatRuntimeStore({
  onSessionResolved: (sessionId) => {
    if (!sessions.value.some((item) => item.id === sessionId)) {
      loadSessions(true).catch(() => {})
    }
  },
  onSessionUpdated: async () => {
    try {
      await loadSessions(true)
    } catch {
      // Keep UI responsive even if the sidebar refresh fails.
    }
  },
  onQuotaRefresh: () => loadBillingSummary(),
  onLoginRequired: () => openLogin(),
})
const visibleChatPanes = chatRuntime.panes
const codeRuntime = useDshCodeRuntime(chatRuntime)
const refreshWorkspaceTitles = userBoundProjects.refresh
const activeChatKey = chatRuntime.activeChatKey
const currentSessionId = chatRuntime.currentSessionId
const desktopWorkspaceRequest = ref(0)
const desktopBrowserRequest = ref(0)
const desktopCodeReviewPath = ref('')
const desktopCodeReviewChanges = ref<DshTaskChangeSet | null>(null)
const desktopCodeFilePath = ref('')
const desktopWorkspaceSummary = ref<DshWorkspaceSummary | null>(null)
const createProjectOpen = ref(false)
const createProjectBusy = ref(false)
const createProjectWorkspace = ref<DshWorkspace | null>(null)
const createProjectWorktree = ref(false)
const activeCodeState = computed(() => codeRuntime.stateFor(activeChatKey.value))
const activeChatHasMessages = computed(() => (
  visibleChatPanes.value.find((pane) => pane.key === activeChatKey.value)?.messages.length || 0
) > 0)
const desktopWindowTitle = computed(() => {
  if (currentView.value === 'chat') {
    const current = sessions.value.find((session) => session.id === currentSessionId.value)
    return current ? displaySessionTitle(current) : t('app.sidebar.new_chat')
  }
  if (currentView.value === 'tools') return t('app.sidebar.tools')
  if (currentView.value === 'scheduled-tasks') return locale.value === 'zh' ? '定时任务' : 'Scheduled tasks'
  if (currentView.value === 'token-usage') return t('app.account.usage')
  if (currentView.value === 'skill-config' || currentView.value === 'composite-editor') {
    return selectedSkill.value?.name || t('app.sidebar.marketplace')
  }
  return t('app.sidebar.marketplace')
})
function requestDesktopWorkspace(): void {
  if (canUseCode.value && currentView.value === 'chat') desktopWorkspaceRequest.value += 1
}

function createProject(): void {
  if (!canUseCode.value || !capabilities.localWorkspacePicker) return
  createProjectWorkspace.value = null
  createProjectWorktree.value = false
  createProjectOpen.value = true
}

async function chooseProjectFolder(): Promise<void> {
  const workspace = await selectDshWorkspace()
  if (!workspace) return
  createProjectWorkspace.value = workspace
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
  try {
    const renamed = workspace.title === title ? workspace : await renameDshWorkspace(workspace.workspace_id, title)
    const binding = await createDesktopProject({
      workspace_id: renamed.workspace_id,
      title: renamed.title,
      worktree: createProjectWorktree.value,
    }, authToken.value || null)
    const pane = chatRuntime.startLocalSession()
    codeRuntime.setDraftProject(pane.key, renamed, createProjectWorktree.value)
    userBoundProjects.add(binding, renamed)
    createProjectOpen.value = false
    navigateTo('chat')
  } finally { createProjectBusy.value = false }
}

function currentProjectIdentity(): string {
  return userBoundProjects.identity()
}

function clearUserBoundProjectState(resetCodeRuntime = false): void {
  userBoundProjects.clear()
  if (resetCodeRuntime) codeRuntime.reset()
}

function prepareProjectBoundary(nextProfile: UserProfile): boolean {
  const previousIdentity = currentProjectIdentity()
  const previousCodeAllowed = canUseCode.value
  const nextCodeAllowed = nextProfile.agentPolicy?.capabilities.code_generation !== false
  const nextIdentity = nextProfile.userId === undefined || nextProfile.userId === null
    ? ''
    : `${String(nextProfile.mainId || 'default')}:${String(nextProfile.userId)}`
  if (previousIdentity !== nextIdentity || previousCodeAllowed !== nextCodeAllowed) {
    clearUserBoundProjectState(previousIdentity !== nextIdentity || !nextCodeAllowed)
  }
  return nextCodeAllowed
}

function requestDesktopBrowser(): void {
  if (canUseBrowser.value && currentView.value === 'chat') {
    openDesktopTool('browser')
  }
}

const desktopAvailableTools = computed<DesktopToolTabKind[]>(() => {
  const tools: DesktopToolTabKind[] = []
  if (canUseBrowser.value && currentSessionId.value) tools.push('browser')
  if (activeCodeState.value.session && capabilities.codeInspector) {
    if (desktopWorkspaceSummary.value?.git_available === true) tools.push('changes')
    if (capabilities.workspaceFiles) tools.push('files')
    if (capabilities.projectTerminal) tools.push('terminal')
  }
  return tools
})

const {
  tabs: desktopToolTabs,
  active: desktopActiveTool,
  open: openDesktopTool,
  select: selectDesktopTool,
  close: closeDesktopTool,
  reset: resetDesktopTools,
} = useDesktopToolTabs({
  isAvailable: kind => currentView.value === 'chat' && desktopAvailableTools.value.includes(kind),
  onActivate: kind => {
    if (kind === 'browser') {
      desktopBrowserRequest.value += 1
      const sessionId = currentSessionId.value
      if (sessionId && capabilities.embeddedBrowser) {
        void selectEmbeddedBrowserSession(sessionId)
          .then(() => activateEmbeddedBrowserSession(sessionId))
          .catch(() => { /* Browser surface reports unavailable state in its own UI. */ })
      }
    }
  },
})

function toggleDesktopCodePanel(mode: 'changes' | 'files' | 'terminal'): void {
  if (desktopActiveTool.value === mode) {
    desktopActiveTool.value = null
    return
  }
  desktopCodeReviewPath.value = ''
  desktopCodeReviewChanges.value = null
  desktopCodeFilePath.value = ''
  openDesktopTool(mode)
}

function reviewCodeChanges(changes: DshTaskChangeSet, path?: string): void {
  if (!activeCodeState.value.session) return
  desktopCodeReviewChanges.value = changes
  desktopCodeReviewPath.value = path || ''
  desktopCodeFilePath.value = ''
  openDesktopTool('changes')
}
function openCodeFile(path: string): void {
  if (!activeCodeState.value.session) return
  desktopCodeReviewChanges.value = null
  desktopCodeReviewPath.value = ''
  desktopCodeFilePath.value = path
  openDesktopTool('files')
}
async function refreshDesktopWorkspaceSummary(): Promise<void> {
  const sessionId = activeCodeState.value.session?.kernel_session_id
  if (!sessionId || !capabilities.codeInspector) return
  try { desktopWorkspaceSummary.value = await getDshWorkspaceSummary(sessionId) } catch { /* keep last known summary */ }
}
let workspaceSummaryRequest = 0
watch(() => activeCodeState.value.session?.kernel_session_id, async sessionId => {
  const request = ++workspaceSummaryRequest
  resetDesktopTools()
  desktopCodeReviewPath.value = ''
  desktopCodeReviewChanges.value = null
  desktopCodeFilePath.value = ''
  desktopWorkspaceSummary.value = null
  if (!sessionId || !capabilities.codeInspector) return
  try {
    const summary = await getDshWorkspaceSummary(sessionId)
    if (request === workspaceSummaryRequest) desktopWorkspaceSummary.value = summary
  } catch { /* The unavailable capability stays hidden. */ }
}, { immediate: true })
watch(() => activeCodeState.value.events.length, async (length, previous) => {
  const sessionId = activeCodeState.value.session?.kernel_session_id
  if (!sessionId || length <= previous) return
  const latest = activeCodeState.value.events.at(-1)
  if (latest?.item_kind !== 'tool' || !['item.completed', 'item.failed'].includes(latest.type)) return
  try { desktopWorkspaceSummary.value = await getDshWorkspaceSummary(sessionId) } catch { /* keep last known summary */ }
})
watch(currentSessionId, (sessionId) => {
  resetDesktopTools()
  if (capabilities.embeddedBrowser && sessionId) void selectEmbeddedBrowserSession(sessionId)
}, { immediate: true })
const sessionSearchDisplayItems = computed(() =>
  trimmedSessionSearchQuery.value ? sessionSearchResults.value : sessions.value
)
const sidebarItems = computed(() => [
  { icon: 'plus', label: t('app.sidebar.new_chat') },
  { icon: 'clock', label: locale.value === 'zh' ? '定时任务' : 'Scheduled tasks' },
  { icon: 'search', label: t('app.sidebar.search_chats') },
])
const publishChannelSuggestions = [
  'wechat_official',
  'xiaohongshu',
  'zhihu',
  'website',
  'email',
  'knowledge_base',
  'docs',
  'social_post',
  'community_post',
  'generic',
]
const contentFormSuggestions = [
  'article',
  'report',
  'brief',
  'guide',
  'memo',
  'review',
  'faq',
  'presentation_outline',
]
const targetAudienceSuggestions = [
  'general_public',
  'beginners',
  'professionals',
  'developers',
  'entrepreneurs',
  'business_owners',
  'marketers',
  'students',
  'decision_makers',
  'product_users',
]
const preferredStyleSuggestions = [
  'formal',
  'professional',
  'casual',
  'conversational',
  'friendly',
  'authoritative',
  'analytical',
  'objective',
  'persuasive',
  'inspirational',
  'humorous',
  'storytelling',
  'concise',
  'detailed',
  'technical',
  'educational',
  'practical',
  'neutral',
  'critical',
  'optimistic',
]
const skillTypeOptions = computed(() => [
  { label: locale.value === 'zh' ? '风格' : 'Style', value: 'style' },
  { label: locale.value === 'zh' ? '执行' : 'Execution', value: 'execution' },
  { label: locale.value === 'zh' ? '渲染' : 'Renderer', value: 'renderer' },
])
const naiveThemeOverrides = {
  common: {
    primaryColor: '#2563eb',
    primaryColorHover: '#1d4ed8',
    primaryColorPressed: '#1e40af',
    primaryColorSuppl: '#2563eb',
    infoColor: '#2563eb',
    infoColorHover: '#1d4ed8',
    infoColorPressed: '#1e40af',
    borderRadius: '12px',
  },
  Input: {
    caretColor: '#2563eb',
    borderHover: '#93c5fd',
    borderFocus: '#2563eb',
    boxShadowFocus: '0 0 0 2px rgba(37, 99, 235, 0.15)',
  },
  Select: {
    peers: {
      InternalSelection: {
        borderHover: '#93c5fd',
        borderFocus: '#2563eb',
        boxShadowFocus: '0 0 0 2px rgba(37, 99, 235, 0.15)',
      },
    },
  },
  Switch: {
    railColorActive: '#2563eb',
    railColorActiveHover: '#1d4ed8',
    buttonColor: '#ffffff',
    boxShadowFocus: '0 0 0 2px rgba(37, 99, 235, 0.18)',
  },
}

function loadSavedUsers() {
  const raw = localStorage.getItem(authUsersKey)
  if (!raw) return
  try {
    const parsed = JSON.parse(raw)
    if (Array.isArray(parsed)) {
      savedUsers.value = parsed.filter((item) => typeof item === 'string')
    }
  } catch {
    savedUsers.value = []
  }
}

function persistSavedUsers(username: string) {
  const next = [username, ...savedUsers.value.filter((item) => item !== username)]
  savedUsers.value = next.slice(0, 5)
  localStorage.setItem(authUsersKey, JSON.stringify(savedUsers.value))
}

// Push the authenticated identity into desktop-persisted settings and
// restart the local agent sidecar so it reconnects with fresh credentials.
// The sidecar reads these values from env at spawn time — without this,
// an agent started before login has an empty user_id and never shows up in
// the backend registry, so browser tasks cannot start.
async function syncDesktopAgentIdentity(token: string, userId: string | number | null | undefined) {
  if (!capabilities.isDesktop) return
  const uid = userId !== undefined && userId !== null ? String(userId) : ''
  if (!uid || !token) return
  try {
    const [current, status] = await Promise.all([getSettings(), getAgentStatus()])
    const settingsMatch = current.user_id === uid && current.auth_token === token
    if (settingsMatch && status.running) return
    if (!settingsMatch) {
      await updateSettings({ ...current, user_id: uid, auth_token: token })
      if (!status.running) await startAgent()
      return
    }
    if (!status.running) await startAgent()
  } catch (err) {
    console.warn('[desktop] failed to sync agent identity', err)
  }
}

function handleLoginSuccess(payload: { token: string; username: string; profile?: UserProfile }) {
  clearUserBoundProjectState(true)
  if (typeof window !== 'undefined') {
    const url = new URL(window.location.href)
    if (url.searchParams.has('invite_code') || url.searchParams.has('inviteCode') || url.searchParams.has('register')) {
      url.searchParams.delete('invite_code')
      url.searchParams.delete('inviteCode')
      url.searchParams.delete('register')
      url.searchParams.delete('invite')
      url.searchParams.delete('username')
      url.searchParams.delete('loginName')
      window.history.replaceState({}, '', `${url.pathname}${url.search}${url.hash}`)
    }
  }
  localStorage.setItem(authTokenKey, payload.token)
  localStorage.setItem(authAccountKey, payload.username)
  authToken.value = payload.token
  currentAccount.value = payload.username
  billingSummary.value = null
  billingSummaryLoaded.value = false
  persistSavedUsers(payload.username)
  // Prefer profile that came back inline with the login response. Falling
  // back to the (sometimes-broken) SSO clientAuth call only when the login
  // didn't give us a userId.
  if (payload.profile && payload.profile.userId !== undefined && payload.profile.userId !== null) {
    userProfile.value = payload.profile
    localStorage.setItem(authUserProfileKey, JSON.stringify(payload.profile))
    loginOpen.value = false
    startLocalSession()
    loadSessions(true).catch(() => {})
    void syncDesktopAgentIdentity(payload.token, payload.profile.userId).then(() => {
      if (canUseCode.value) void refreshWorkspaceTitles()
    })
  } else {
    refreshUserProfile(payload.token, true)
  }
}

function handleBillingSuccess(payload: { token: string; username: string; profile: any }) {
  handleLoginSuccess(payload)
}

function handleOrganizationCreated(payload: { token: string; username: string; profile: UserProfile }) {
  handleLoginSuccess(payload)
}

function openLogin() {
  loginOpen.value = true
}

function openProfileEditor() {
  profileOpen.value = true
  closeUserMenu()
}

function openCreateOrganization() {
  if (!canCreateOrganization.value) return
  createOrganizationOpen.value = true
  closeUserMenu()
}

function openBilling() {
  if (!canUpgradePlan.value) return
  billingOpen.value = true
  closeUserMenu()
}

function openPersonalization() {
  personalizationOpen.value = true
  closeUserMenu()
}

function closePersonalization() {
  personalizationOpen.value = false
}

function applyThemeMode() {
  const systemDark = window.matchMedia('(prefers-color-scheme: dark)').matches
  isDarkTheme.value = themeMode.value === 'dark' || (themeMode.value === 'system' && systemDark)
  document.documentElement.classList.toggle('theme-dark', isDarkTheme.value)
  document.documentElement.style.colorScheme = isDarkTheme.value ? 'dark' : 'light'
}

function selectThemeMode(mode: ThemeMode) {
  themeMode.value = mode
}

async function selectLanguage(language: Locale) {
  if (languageSaving.value || locale.value === language) return
  const previous = locale.value
  setAppLocale(language)
  languageSaving.value = true
  try {
    const settings = await getSettings()
    await updateSettings({ ...settings, language })
  } catch (error) {
    setAppLocale(previous)
    console.warn('[settings] failed to persist language', error)
  } finally {
    languageSaving.value = false
  }
}

async function selectTimezone(timezone: string) {
  if (timezoneSaving.value || timezoneValue.value === timezone) return
  const previous = timezoneValue.value
  timezoneValue.value = setAppTimezone(timezone)
  timezoneSaving.value = true
  try {
    const settings = await getSettings()
    await updateSettings({ ...settings, timezone })
  } catch (error) {
    timezoneValue.value = setAppTimezone(previous)
    console.warn('[settings] failed to persist timezone', error)
  } finally {
    timezoneSaving.value = false
  }
}

function handleSystemThemeChange() {
  if (themeMode.value === 'system') applyThemeMode()
}

function handleProfileUpdated(profile: UserProfile) {
  prepareProjectBoundary(profile)
  userProfile.value = profile
  localStorage.setItem(authUserProfileKey, JSON.stringify(profile))
  if (profile.username) {
    currentAccount.value = profile.username
    localStorage.setItem(authAccountKey, profile.username)
  }
}

function clearAuthenticatedState() {
  clearUserBoundProjectState(true)
  localStorage.removeItem(authTokenKey)
  localStorage.removeItem(authAccountKey)
  localStorage.removeItem(authUserProfileKey)
  authToken.value = ''
  currentAccount.value = ''
  userProfile.value = null
  billingSummary.value = null
  billingSummaryLoaded.value = false
  userMenuOpen.value = false
  sessions.value = []
  sessionsHasMore.value = false
  sessionsLoading.value = false
  sessionsLoadingMore.value = false
  chatRuntime.reset()
  sessionSearchOpen.value = false
  sessionSearchQuery.value = ''
  sessionSearchResults.value = []
  sessionSearchHasMore.value = false
  sessionSearchLoading.value = false
  sessionSearchDidRun.value = false
}

function logout() {
  if (authToken.value) {
    void logoutWithToken(authToken.value)
  }
  clearAuthenticatedState()
}

function handleAuthExpired() {
  if (!authToken.value && !localStorage.getItem(authTokenKey)) return
  console.warn('[auth] session expired; clearing cached session and opening login dialog')
  clearAuthenticatedState()
  loginOpen.value = true
}

function toggleUserMenu() {
  if (!isLoggedIn.value) {
    openLogin()
    return
  }
  userMenuOpen.value = !userMenuOpen.value
  if (userMenuOpen.value) {
    void loadBillingSummary()
  }
}

function closeUserMenu() {
  userMenuOpen.value = false
}

function openSettingsPanel() {
  if (!capabilities.isDesktop) return
  settingsPanelOpen.value = true
  closeUserMenu()
}

function resolveViewFromPath(pathname: string) {
  const path = String(pathname || '/').replace(/\/+$/, '') || '/'
  if (path === '/usage' || path === '/token-usage') return 'token-usage'
  if (path === '/skills') return 'skills'
  if (path === '/tools') return 'tools'
  if (path === '/scheduled-tasks') return 'scheduled-tasks'
  return 'chat'
}

function routePathForView(view: typeof currentView.value) {
  if (view === 'token-usage') return '/usage'
  if (view === 'tools') return '/tools'
  if (view === 'scheduled-tasks') return '/scheduled-tasks'
  if (view === 'skills' || view === 'skill-config' || view === 'composite-editor') return '/skills'
  return '/'
}

function navigateTo(view: typeof currentView.value, replace = false) {
  currentView.value = view
  if (typeof window === 'undefined') return
  const nextPath = routePathForView(view)
  const currentPath = window.location.pathname || '/'
  if (currentPath === nextPath) return
  window.history[replace ? 'replaceState' : 'pushState']({}, '', nextPath)
}

function handlePopState() {
  currentView.value = resolveViewFromPath(window.location.pathname)
  if (currentView.value !== 'chat') {
    closeSessionSearch()
  }
}

function openTokenUsagePage() {
  navigateTo('token-usage')
  closeUserMenu()
}

function openScheduledTasks(options: { prompt?: string; sessionId?: string | null; create?: boolean } = {}) {
  if (!isLoggedIn.value) {
    openLogin()
    return
  }
  scheduledTaskInitialPrompt.value = options.prompt || ''
  scheduledTaskInitialSessionId.value = options.sessionId ?? currentSessionId.value
  if (options.create) scheduledTaskCreateRequestKey.value += 1
  navigateTo('scheduled-tasks')
  closeSessionSearch()
}

function handleSidebarAction(icon: string) {
  if (icon === 'plus') startLocalSession()
  else if (icon === 'clock') openScheduledTasks()
  else openSessionSearch()
}

async function handleSwitchTenant(mainId: string) {
  await switchToTenant(mainId)
}

async function switchToTenant(mainId: string): Promise<string | null> {
  const target = String(mainId || '').trim()
  if (!target || !authToken.value || switchingTenant.value) return null
  if (target === getMainId()) return authToken.value
  switchingTenant.value = true
  try {
    const result = await switchTenant(authToken.value, target)
    if (!result.ok || !result.token) return null
    clearUserBoundProjectState(true)
    localStorage.setItem(authTokenKey, result.token)
    authToken.value = result.token
    if (result.profile) {
      userProfile.value = result.profile
      localStorage.setItem(authUserProfileKey, JSON.stringify(result.profile))
      if (result.profile.username) {
        currentAccount.value = result.profile.username
        localStorage.setItem(authAccountKey, result.profile.username)
      }
    }
    billingSummary.value = null
    billingSummaryLoaded.value = false
    void loadBillingSummary()
    startLocalSession()
    await loadSessions(true)
    return result.token
  } finally {
    switchingTenant.value = false
  }
}

function closeTokenUsagePage() {
  navigateTo('chat')
}

function closeSettingsPanel() {
  settingsPanelOpen.value = false
}

function applyLanguage(language?: string | null) {
  setAppLocale((language === 'en' ? 'en' : 'zh') as Locale)
}

function handleDocumentClick(event: MouseEvent) {
  const target = event.target as HTMLElement | null
  if (!target?.closest('[data-user-menu]')) {
    closeUserMenu()
  }
}

async function loadSkills() {
  if (!getUserId()) return
  skillsLoading.value = true
  try {
    skills.value = await listSkills(getUserId(), getMainId())
  } catch {
    skills.value = []
  } finally {
    skillsLoading.value = false
  }
}

function openSkillsPage() {
  navigateTo('skills')
  loadSkills()
}

function closeSkillsPage() {
  navigateTo('chat')
}

function openToolsPage() {
  navigateTo('tools')
}

function closeToolsPage() {
  navigateTo('chat')
}

function openSkillConfig(skill: any) {
  selectedSkill.value = skill
  // Composite-task skills have their own editor: step list + site picker,
  // completely different shape from the style / execution / renderer editor.
  const kind = String(skill?.skill_type || skill?.role || '').toLowerCase()
  if (kind === 'composite_task') {
    navigateTo('composite-editor')
  } else {
    navigateTo('skill-config')
  }
}

function openNewCompositeSkill() {
  selectedSkill.value = null
  navigateTo('composite-editor')
}

function closeSkillConfig() {
  navigateTo('skills')
}

function handleCompositeSaved(savedSkill: any) {
  selectedSkill.value = savedSkill || selectedSkill.value
  loadSkills().catch(() => {})
  navigateTo('skills')
}

function closeSkillForm() {
  skillFormOpen.value = false
}

function openSkillForm() {
  skillFormOpen.value = true
}

async function handleSkillFileUpload(event: Event, kind: 'knowledge' | 'templates' | 'tools') {
  if (!getUserId()) return
  const input = event.target as HTMLInputElement
  if (!input.files || input.files.length === 0) return
  const files = Array.from(input.files)
  for (const file of files) {
    const uploaded = await uploadSkillSource(getUserId(), file)
    if (uploaded?.object_path) {
      if (kind === 'knowledge') skillKnowledge.value.push(uploaded)
      if (kind === 'templates') skillTemplates.value.push(uploaded)
      if (kind === 'tools') skillTools.value.push(uploaded)
    }
  }
  input.value = ''
}

async function handleSkillResourceUpload(event: Event, kind: 'knowledge' | 'templates' | 'tools') {
  if (!getUserId() || !selectedSkill.value) return
  const input = event.target as HTMLInputElement
  if (!input.files || input.files.length === 0) return
  const files = Array.from(input.files)
  for (const file of files) {
    const uploaded = await uploadSkillSource(getUserId(), file)
    if (uploaded?.object_path) {
      const updated = { ...selectedSkill.value }
      const resources = { ...(updated.resources || {}) }
      const list = [...(resources[kind] || []), uploaded]
      resources[kind] = list
      updated.resources = resources
      selectedSkill.value = updated
    }
  }
  input.value = ''
}

async function enrichDraftFromForm() {
  if (!getUserId() || !skillName.value.trim()) return
  skillEnriching.value = true
  try {
    const inputProfile = {
      skill_type: skillType.value,
      name: skillName.value.trim(),
      summary: skillSummary.value.trim(),
      applicable_scenarios: skillScenario.value.trim(),
      publish_channel: skillChannels.value,
      content_form: skillForms.value,
      target_audience: skillAudience.value,
      preferred_style: skillStyle.value,
      required_elements: skillRequired.value,
      forbidden_elements: skillForbidden.value,
      reference_materials: [
        ...skillKnowledge.value.map((item: any) => item.filename || item.object_path),
        ...skillTemplates.value.map((item: any) => item.filename || item.object_path),
      ],
    }
    const enriched = await enrichSkillDraft({
      user_id: getUserId(),
      name: skillName.value.trim(),
      description: skillSummary.value.trim(),
      skill_type: skillType.value,
      input_profile: inputProfile,
    })
    const contract = enriched?.contract_json || {}
    skillSummary.value = contract.summary || skillSummary.value
    skillScenario.value = contract.applicable_scenarios || skillScenario.value
    skillChannels.value = contract.publish_channel || skillChannels.value
    skillForms.value = contract.content_form || skillForms.value
    skillAudience.value = contract.target_audience || skillAudience.value
    skillStyle.value = contract.preferred_style || skillStyle.value
    skillRequired.value = contract.required_elements || skillRequired.value
    skillForbidden.value = contract.forbidden_elements || skillForbidden.value
  } finally {
    skillEnriching.value = false
  }
}

async function createSkill() {
  if (!getUserId()) return
  if (!skillName.value.trim()) return
  skillCreating.value = true
  try {
    const contractJson = {
      skill_type: skillType.value,
      name: skillName.value.trim(),
      summary: skillSummary.value.trim(),
      applicable_scenarios: skillScenario.value.trim(),
      publish_channel: skillChannels.value,
      content_form: skillForms.value,
      target_audience: skillAudience.value,
      preferred_style: skillStyle.value,
      required_elements: skillRequired.value,
      forbidden_elements: skillForbidden.value,
      reference_materials: [
        ...skillKnowledge.value.map((item: any) => item.filename || item.object_path),
        ...skillTemplates.value.map((item: any) => item.filename || item.object_path),
      ],
    }
    const created = await generateSkill({
      user_id: getUserId(),
      name: skillName.value.trim(),
      description: skillSummary.value.trim(),
      summary: skillSummary.value.trim(),
      category: skillCategory.value,
      role: skillType.value,
      skill_type: skillType.value,
      tags: [],
      visibility: 'private',
      formats: ['markdown'],
      sources: [],
      resources: {
        knowledge: skillKnowledge.value,
        templates: skillTemplates.value,
        tools: skillTools.value,
      },
      input_profile: contractJson,
      contract_json: contractJson,
      skill_markdown: '',
      advanced: {},
      is_active: false,
    })
    if (created) {
      handleSkillCreate(created)
      currentView.value = 'skill-config'
      skillName.value = ''
      skillSummary.value = ''
      skillCategory.value = 'Analysis & Reports'
      skillType.value = 'style'
      skillScenario.value = ''
      skillChannels.value = ['generic']
      skillForms.value = ['article']
      skillAudience.value = ['general_public']
      skillStyle.value = ['professional']
      skillRequired.value = []
      skillForbidden.value = []
      skillKnowledge.value = []
      skillTemplates.value = []
      skillTools.value = []
      skillFormOpen.value = false
    }
  } finally {
    skillCreating.value = false
  }
}

function handleSkillCreate(skillOrEvent: any) {
  // If it's a DOM event or empty, open the form
  if (!skillOrEvent || skillOrEvent instanceof Event || !skillOrEvent.id) {
    openSkillForm()
    return
  }
  
  // If it's a skill object, add to list and select
  skills.value = [skillOrEvent, ...skills.value]
  selectedSkill.value = skillOrEvent
  // Note: View switching is handled by separate 'configure' event or createSkill flow
}

async function saveSkillConfig(payload: any) {
  if (!getUserId() || !payload?.id) return
  const updated = await updateSkill(payload.id, {
    user_id: getUserId(),
    name: payload.name,
    description: payload.description,
    category: payload.category,
    skill_type: payload.skill_type,
    is_active: payload.is_active,
    input_profile: payload.input_profile,
    contract_json: payload.contract_json,
    skill_markdown: payload.skill_markdown,
    resources: payload.resources,
    advanced: payload.advanced,
  })
  if (updated) {
    skills.value = skills.value.map((s) => (s.id === updated.id ? updated : s))
    selectedSkill.value = updated
  }
}

async function toggleSkillActive(skill: any, isActive: boolean) {
  if (!getUserId() || !skill?.id) return
  const updated = await updateSkill(skill.id, {
    user_id: getUserId(),
    name: skill.name,
    description: skill.description,
    category: skill.category,
    skill_type: skill.skill_type || 'style',
    is_active: isActive,
    input_profile: skill.input_profile || skill.contract_json || {},
    contract_json: skill.contract_json || skill.input_profile || {},
    skill_markdown: skill.skill_markdown || '',
    resources: skill.resources || {},
    advanced: skill.advanced || {},
  })
  if (updated) {
    skills.value = skills.value.map((item) => (item.id === updated.id ? updated : item))
    if (selectedSkill.value?.id === updated.id) {
      selectedSkill.value = updated
    }
  }
}

async function removeSkill(skill: any) {
  if (!getUserId() || !skill?.id) return
  await deleteSkill(skill.id, getUserId())
  skills.value = skills.value.filter((s) => s.id !== skill.id)
  if (selectedSkill.value?.id === skill.id) {
    selectedSkill.value = null
    currentView.value = 'skills'
  }
}

async function refreshUserProfile(token: string, createDefaultSession = false, preserveSessionOnFailure = false) {
  if (createDefaultSession) {
    startLocalSession()
  }
  const result = await fetchUserProfile(token)
  if (result.ok && result.data) {
    prepareProjectBoundary(result.data)
    userProfile.value = result.data
    localStorage.setItem(authUserProfileKey, JSON.stringify(result.data))
    await loadSessions(true).catch(() => {})
    loginOpen.value = false
    void syncDesktopAgentIdentity(token, result.data.userId)
    return
  }
  if (preserveSessionOnFailure) {
    sessionsLoading.value = false
    console.warn('[auth] fetchUserProfile failed; keeping cached session and retrying later')
    await loadSessions(true).catch(() => {})
    return
  }
  // SSO failed (e.g. token already consumed, or running inside an embedded WebView
  // where the SSO endpoint refuses requests). Stop showing a stale state and
  // ask the user to log in fresh — the new login flow extracts profile from
  // the login response itself, so it won't hit this code path again.
  sessionsLoading.value = false
  console.warn('[auth] fetchUserProfile failed; opening login dialog for fresh sign-in')
  localStorage.removeItem(authTokenKey)
  localStorage.removeItem(authUserProfileKey)
  authToken.value = ''
  userProfile.value = null
  loginOpen.value = true
}

async function refreshEnterprisePolicy(token: string): Promise<void> {
  const result = await fetchUserProfile(token)
  if (!result.ok || !result.data || authToken.value !== token) return
  const nextCodeAllowed = prepareProjectBoundary(result.data)
  userProfile.value = result.data
  localStorage.setItem(authUserProfileKey, JSON.stringify(result.data))
  if (nextCodeAllowed) await refreshWorkspaceTitles()
  if (currentView.value === 'skills') await loadSkills().catch(() => {})
}

useProfileRefreshOnResume({ token: authToken, refresh: refreshEnterprisePolicy })

function loadUserProfile() {
  const raw = localStorage.getItem(authUserProfileKey)
  console.log('[auth] loadUserProfile raw:', raw)
  if (!raw) return
  try {
    const parsed = JSON.parse(raw)
    console.log('[auth] loadUserProfile parsed:', parsed)
    if (parsed && typeof parsed === 'object') {
      userProfile.value = parsed
    }
  } catch (err) {
    console.warn('[auth] loadUserProfile parse failed:', err)
    userProfile.value = null
  }
}

function normalizedPhone() {
  const value = String(userProfile.value?.phone || userProfile.value?.username || currentAccount.value || '').replace(/\D/g, '')
  return /^1[3-9]\d{9}$/.test(value) ? value : ''
}

function maskedPhone() {
  const phone = normalizedPhone()
  return phone ? `${phone.slice(0, 3)}****${phone.slice(-4)}` : ''
}

function displayName() {
  const profileName = String(userProfile.value?.name || '').trim()
  const phone = normalizedPhone()
  if (profileName && profileName !== phone && !/^1[3-9]\d{9}$/.test(profileName)) {
    return profileName
  }
  if (phone) {
    return locale.value === 'zh' ? `用户 ${phone.slice(-4)}` : `User ${phone.slice(-4)}`
  }
  return currentAccount.value || t('app.sidebar.login_register')
}

function displayAvatar() {
  const avatar = userProfile.value?.avatar || ''
  if (avatar && avatar !== 'null') return avatar
  return ''
}

function handleAvatarError(event: Event) {
  const image = event.currentTarget as HTMLImageElement
  const retryCount = Number(image.dataset.retryCount || 0)
  if (retryCount >= 5 || !authToken.value) {
    image.style.display = 'none'
    return
  }
  image.dataset.retryCount = String(retryCount + 1)
  const retryDelay = [1000, 2000, 4000, 8000, 15000][retryCount] || 15000
  window.setTimeout(async () => {
    const result = await fetchUserProfile(authToken.value)
    if (!result.ok || !result.data?.avatar) return
    userProfile.value = result.data
    localStorage.setItem(authUserProfileKey, JSON.stringify(result.data))
    const avatar = result.data.avatar
    image.src = avatar.startsWith('/')
      ? `${avatar}${avatar.includes('?') ? '&' : '?'}retry=${Date.now()}`
      : avatar
  }, retryDelay)
}

function displayAvatarText() {
  return normalizedPhone() ? (locale.value === 'zh' ? '用' : 'U') : displayName().slice(0, 1)
}

const accountTierLabel = computed(() => {
  if (userProfile.value?.edition === 'community' || billingSummary.value?.edition === 'community') {
    return t('ui.community_edition')
  }
  if (isEnterpriseSpace.value) {
    return userProfile.value?.canAccessAdmin
      ? t('ui.enterprise_admin')
      : t('ui.enterprise_member')
  }
  const tier = billingSummary.value?.tier || userProfile.value?.tier
  if (tier === 'plus') return locale.value === 'zh' ? 'Plus 个人版' : 'Plus Personal'
  if (tier === 'pro') return locale.value === 'zh' ? '专业团队版' : 'Pro Team'
  if (tier === 'enterprise') return locale.value === 'zh' ? '企业定制版' : 'Enterprise Custom'
  return locale.value === 'zh' ? '免费版' : 'Free'
})

const quotaTotal = computed(() => Number(billingSummary.value?.totalPoints || 0))
const quotaUsed = computed(() => Number(billingSummary.value?.usedPoints || 0))
const quotaRemaining = computed(() => Math.max(0, Number(billingSummary.value?.remainingPoints ?? quotaTotal.value - quotaUsed.value)))
const quotaUsedPercent = computed(() => {
  return quotaUsagePercent(quotaUsed.value, quotaTotal.value)
})
const quotaUsedPercentLabel = computed(() => formatQuotaUsagePercent(quotaUsed.value, quotaTotal.value))
const quotaTotalLabel = computed(() => billingSummary.value?.quotaSource === 'enterprise_allocation' ? '企业分派' : t('ui.quota_gift'))
function formatTokenCount(value: number) {
  return formatTokenAmount(value, locale.value)
}

async function loadBillingSummary() {
  if (!authToken.value || billingSummaryLoading.value) return
  billingSummaryLoading.value = true
  try {
    const result = await fetchOrgBilling(authToken.value)
    if (result.ok) billingSummary.value = result.data
  } finally {
    billingSummaryLoading.value = false
    billingSummaryLoaded.value = true
  }
}

function getUserId() {
  const id = userProfile.value?.userId
  if (id === undefined || id === null) return null
  return String(id)
}

function getMainId() {
  return String(userProfile.value?.mainId || 'default')
}

function isEnterpriseTenant(tenant: Pick<TenantCandidate, 'spaceType' | 'orgName'>) {
  if (tenant.spaceType) return tenant.spaceType === 'enterprise'
  return String(tenant.orgName || '').trim() !== '个人空间'
}

async function openAdminConsole(mainId = getMainId()) {
  if (!authToken.value || adminSsoStarting.value) return
  const target = availableTenants.value.find((tenant) => tenant.mainId === mainId)
  if (target && !canAccessAdmin(target)) return
  if (target && !isEnterpriseTenant(target)) return
  if (!target && userProfile.value?.canAccessAdmin !== true) return
  if (!target && !isEnterpriseSpace.value) return

  const adminWindow = capabilities.embeddedBrowser ? null : window.open('', '_blank')
  adminSsoStarting.value = true
  try {
    const token = await switchToTenant(mainId)
    if (!token) {
      adminWindow?.close()
      return
    }
    const result = await getAdminSSOToken(token)
    if (!result.ok || !result.ssoToken) {
      adminWindow?.close()
      window.alert(result.message || t('api.auth.auth_failed'))
      return
    }
    const adminUrl = buildAdminSsoUrl(result.ssoToken)
    if (capabilities.embeddedBrowser) {
      await openResource(adminUrl, 'internal')
    } else if (adminWindow) {
      adminWindow.location.href = adminUrl
    } else {
      window.open(adminUrl, '_blank')
    }
    closeUserMenu()
  } catch (error: any) {
    adminWindow?.close()
    window.alert(error?.message || t('api.auth.auth_failed'))
  } finally {
    adminSsoStarting.value = false
  }
}

function mergeSessionPages(existing: SessionSummary[], incoming: SessionSummary[]) {
  const merged = [...existing]
  const seen = new Set(existing.map((item) => item.id))
  for (const item of incoming) {
    if (seen.has(item.id)) continue
    merged.push(item)
    seen.add(item.id)
  }
  return merged
}

function sessionIsRunning(sessionId: string) {
  const serverRunning = sessions.value.some((item) => item.id === sessionId && item.active_run?.status === 'running')
  return serverRunning || chatRuntime.sessionIsRunning(sessionId)
}

function sessionScheduledIsRunning(sessionId: string) {
  return sessions.value.some(
    (item) => item.id === sessionId && item.active_run?.source === 'scheduled' && item.active_run?.status === 'running',
  )
}

function sessionNeedsHumanAssistance(sessionId: string) {
  const serverNeedsHelp = sessions.value.some(
    (item) => item.id === sessionId
      && (item.active_run?.status === 'suspended' || Number(item.pending_approval_count || 0) > 0),
  )
  return serverNeedsHelp || codeRuntime.needsAssistance(sessionId) || visibleChatPanes.value.some(
    (pane) => pane.sessionId === sessionId && Boolean(pane.activeIntervention),
  )
}

function sessionIsUnread(sessionId: string) {
  return sessions.value.some((item) => item.id === sessionId && item.scheduled_unread) || chatRuntime.sessionIsUnread(sessionId)
}

function displaySessionTitle(session: Pick<SessionSummary, 'title'>) {
  return session.title || t('app.sidebar.new_chat')
}

/** Keep navigation labels compact without mutating the user-visible saved title. */
function compactSessionTitle(session: Pick<SessionSummary, 'title'>, limit = 28) {
  const title = displaySessionTitle(session).trim()
  return title.length > limit ? `${title.slice(0, limit).trimEnd()}…` : title
}

function updateSessionTitleInLists(updated: SessionSummary) {
  sessions.value = sessions.value.map((item) => (item.id === updated.id ? { ...item, ...updated } : item))
  sessionSearchResults.value = sessionSearchResults.value.map((item) => (
    item.id === updated.id ? { ...item, ...updated } : item
  ))
}

function focusSessionTitleInput(sessionId: string) {
  nextTick(() => {
    const root = document.querySelector(`[data-session-title-input="${sessionId}"]`)
    const input = root?.querySelector('input') as HTMLInputElement | null
    input?.focus()
    input?.select()
  })
}

function startEditSessionTitle(session: SessionSummary | SessionSearchResult) {
  if (renamingSessionId.value) return
  editingSessionId.value = session.id
  editingSessionTitle.value = displaySessionTitle(session)
  focusSessionTitleInput(session.id)
}

function cancelSessionTitleEdit() {
  editingSessionId.value = null
  editingSessionTitle.value = ''
}

async function commitSessionTitleEdit(session: SessionSummary | SessionSearchResult) {
  const userId = getUserId()
  if (!userId || renamingSessionId.value === session.id) return
  const title = editingSessionTitle.value.trim()
  const previousTitle = displaySessionTitle(session)
  if (!title || title === previousTitle) {
    cancelSessionTitleEdit()
    return
  }
  renamingSessionId.value = session.id
  try {
    const updated = await updateSessionTitle(session.id, userId, getMainId(), title, authToken.value || null)
    updateSessionTitleInLists(updated)
    cancelSessionTitleEdit()
  } catch (error) {
    console.warn('[sessions] update title failed:', error)
    focusSessionTitleInput(session.id)
  } finally {
    renamingSessionId.value = null
  }
}

async function handleDeleteSession(sessionId: string) {
  const userId = getUserId()
  if (!userId || deletingSessionId.value === sessionId) return
  if (editingSessionId.value === sessionId) {
    cancelSessionTitleEdit()
  }
  const target =
    sessions.value.find((item) => item.id === sessionId) ||
    sessionSearchResults.value.find((item) => item.id === sessionId) ||
    null
  pendingDeleteSession.value = target
}

function cancelDeleteSession() {
  pendingDeleteSession.value = null
}

async function confirmDeleteSession() {
  const userId = getUserId()
  const sessionId = pendingDeleteSession.value?.id
  if (!userId || !sessionId || deletingSessionId.value === sessionId) return
  deletingSessionId.value = sessionId
  try {
    await deleteSession(sessionId, userId, getMainId(), authToken.value || null)
    sessions.value = sessions.value.filter((item) => item.id !== sessionId)
    sessionSearchResults.value = sessionSearchResults.value.filter((item) => item.id !== sessionId)
    chatRuntime.removeSession(sessionId)
  } finally {
    pendingDeleteSession.value = null
    deletingSessionId.value = null
  }
}

async function loadSessions(reset = true) {
  const userId = getUserId()
  if (!userId) return
  if (reset) {
    sessionsLoading.value = true
    sessionsHasMore.value = false
  } else {
    sessionsLoadingMore.value = true
  }
  try {
    const page = await listSessionsPaged(userId, getMainId(), {
      limit: sessionPageSize,
      offset: reset ? 0 : sessions.value.length,
    }, authToken.value || null)
    sessions.value = reset ? page.items : mergeSessionPages(sessions.value, page.items)
    sessionsHasMore.value = page.has_more
    if (canUseCode.value) void refreshWorkspaceTitles()
  } catch (error) {
    throw error
  } finally {
    if (reset) {
      sessionsLoading.value = false
    } else {
      sessionsLoadingMore.value = false
    }
  }
}

async function refreshSessionSummaries() {
  const userId = getUserId()
  if (!userId || document.visibilityState === 'hidden') return
  try {
    const page = await listSessionsPaged(userId, getMainId(), { limit: sessionPageSize, offset: 0 }, authToken.value || null)
    sessions.value = mergeSessionPages(page.items, sessions.value).slice(0, Math.max(sessionPageSize, sessions.value.length))
    sessionsHasMore.value = page.has_more
  } catch {
    // Best-effort visibility refresh; explicit navigation still retries.
  }
}

function openSessionSearch() {
  if (!isLoggedIn.value) {
    openLogin()
    return
  }
  navigateTo('chat')
  sessionSearchOpen.value = true
}

function closeSessionSearch() {
  sessionSearchOpen.value = false
  sessionSearchQuery.value = ''
  sessionSearchResults.value = []
  sessionSearchHasMore.value = false
  sessionSearchLoading.value = false
  sessionSearchDidRun.value = false
}

async function runSessionSearch(reset = true) {
  const userId = getUserId()
  const queryText = trimmedSessionSearchQuery.value
  if (!userId || !queryText) {
    sessionSearchResults.value = []
    sessionSearchHasMore.value = false
    sessionSearchDidRun.value = false
    sessionSearchLoading.value = false
    return
  }
  sessionSearchLoading.value = true
  try {
    const page = await searchSessions(userId, getMainId(), queryText, {
      limit: sessionSearchPageSize,
      offset: reset ? 0 : sessionSearchResults.value.length,
    }, authToken.value || null)
    sessionSearchResults.value = reset ? page.items : [...sessionSearchResults.value, ...page.items]
    sessionSearchHasMore.value = page.has_more
    sessionSearchDidRun.value = true
  } finally {
    sessionSearchLoading.value = false
  }
}

function scheduleSessionSearch() {
  if (sessionSearchTimer) {
    clearTimeout(sessionSearchTimer)
    sessionSearchTimer = null
  }
  const queryText = trimmedSessionSearchQuery.value
  if (!queryText) {
    sessionSearchResults.value = []
    sessionSearchHasMore.value = false
    sessionSearchDidRun.value = false
    sessionSearchLoading.value = false
    return
  }
  sessionSearchTimer = setTimeout(() => {
    runSessionSearch(true).catch(() => {
      sessionSearchLoading.value = false
    })
  }, 250)
}

function startLocalSession(shouldNavigate = true) {
  const pane = chatRuntime.startLocalSession()
  if (canUseCode.value) codeRuntime.recommend(pane.key, availableUserProjects(projectWorkspaces.value))
  if (shouldNavigate) {
    navigateTo('chat')
  }
  closeSessionSearch()
}

async function selectSession(sessionId: string) {
  const userId = getUserId()
  if (!userId) return
  navigateTo('chat')
  if (currentSessionId.value === sessionId) return
  const pane = await chatRuntime.selectSession(sessionId, userId, getMainId(), authToken.value || null)
  if (canUseCode.value) await codeRuntime.attach(pane.key, sessionId)
  closeSessionSearch()
}

async function handlePaneSend(
  key: string,
  payload: {
    text: string
    images: File[]
    documents: PendingRuntimeDocument[]
    knowledgeQaEnabled: boolean
    selectedSkillId?: string
    modelId?: string
  },
) {
  const codeState = codeRuntime.stateFor(key)
  if (canUseCode.value && (codeState.workspace || codeState.session)) {
    if (payload.images.length || payload.documents.length) {
      codeState.error = locale.value === 'en'
        ? 'Attach project files inside the selected Workspace before sending a Code task.'
        : 'Code 项目任务请先把附件放入所选 Workspace，再发送任务。'
      return
    }
    const existingPane = visibleChatPanes.value.find((pane) => pane.key === key)
    let targetKey = key
    if (existingPane?.sessionId && !codeState.session) {
      const derived = chatRuntime.startLocalSession()
      codeRuntime.transferDraft(key, derived.key)
      targetKey = derived.key
    }
    try { await codeRuntime.send(targetKey, payload.text, payload.modelId) } catch { /* visible in Code context */ }
    return
  }
  chatRuntime.sendMessage(key, {
    ...payload,
    authToken: authToken.value || null,
    userId: getUserId(),
    mainId: getMainId(),
    locale: locale.value === 'en' ? 'en' : 'zh',
    timezone: timezoneValue.value,
  })
}

function handlePaneStop(key: string) {
  const codeState = codeRuntime.stateFor(key)
  if (codeState.session) void codeRuntime.stop(key)
  else chatRuntime.stopGeneration(key)
}

watch(sessionSearchQuery, () => {
  scheduleSessionSearch()
})

watch(locale, (value) => {
  document.documentElement.lang = value === 'en' ? 'en' : 'zh-CN'
}, { immediate: true })

watch([normalHistoryExpanded, collapsedProjectHistory], ([normal, projects]) => {
  localStorage.setItem(sidebarHistoryStateKey, JSON.stringify({ normal, projects }))
}, { deep: true })

watch(themeMode, (value) => {
  localStorage.setItem(themeModeKey, value)
  applyThemeMode()
})

function handleDesktopServerConnected() {
  for (const key of [authTokenKey, authAccountKey, authUsersKey, authUserProfileKey]) {
    localStorage.removeItem(key)
  }
  window.location.reload()
}

onMounted(async () => {
  window.addEventListener(AUTH_EXPIRED_EVENT, handleAuthExpired)
  applyThemeMode()
  systemThemeMedia = window.matchMedia('(prefers-color-scheme: dark)')
  systemThemeMedia.addEventListener('change', handleSystemThemeChange)
  currentView.value = resolveViewFromPath(window.location.pathname)
  let serverConfigured = !capabilities.isDesktop
  try {
    const storedSettings = await getSettings()
    serverConfigured = storedSettings.server_configured
    applyLanguage(storedSettings.language)
    timezoneValue.value = setAppTimezone(storedSettings.timezone || getBrowserTimezone())
  } catch {
    applyLanguage('zh')
    timezoneValue.value = setAppTimezone(getBrowserTimezone())
  }
  if (capabilities.isDesktop && !serverConfigured) {
    desktopServerState.value = 'required'
    return
  }
  desktopServerState.value = 'ready'
  currentAccount.value = localStorage.getItem(authAccountKey) || ''
  authToken.value = localStorage.getItem(authTokenKey) || ''
  loadSavedUsers()
  loadUserProfile()
  if (authToken.value && !userProfile.value) {
    startLocalSession(currentView.value === 'chat')
    sessionsLoading.value = true
    refreshUserProfile(authToken.value).catch(() => {
      sessionsLoading.value = false
    })
  } else if (authToken.value && userProfile.value) {
    startLocalSession(currentView.value === 'chat')
    refreshUserProfile(authToken.value, false, true).catch(() => {
      loadSessions(true).catch(() => {})
    })
  } else if (!authToken.value) {
    loginOpen.value = true
    startLocalSession(currentView.value === 'chat')
  }
  // Self-heal the desktop agent on boot: if we have a stored session,
  // make sure the Electron settings + sidecar reflect it (no-op on web).
  if (authToken.value && userProfile.value?.userId !== undefined) {
    void syncDesktopAgentIdentity(authToken.value, userProfile.value.userId)
  }
  document.addEventListener('click', handleDocumentClick)
  window.addEventListener('popstate', handlePopState)
  sessionRefreshTimer = setInterval(() => { void refreshSessionSummaries() }, 5000)
})

onBeforeUnmount(() => {
  if (sessionSearchTimer) {
    clearTimeout(sessionSearchTimer)
    sessionSearchTimer = null
  }
  if (sessionRefreshTimer) {
    clearInterval(sessionRefreshTimer)
    sessionRefreshTimer = null
  }
  document.removeEventListener('click', handleDocumentClick)
  window.removeEventListener('popstate', handlePopState)
  window.removeEventListener(AUTH_EXPIRED_EVENT, handleAuthExpired)
  systemThemeMedia?.removeEventListener('change', handleSystemThemeChange)
})
</script>

<template>
  <n-config-provider :theme="isDarkTheme ? darkTheme : null" :theme-overrides="naiveThemeOverrides">
  <n-message-provider>
  <n-notification-provider>
  <n-dialog-provider>
  <div
    v-if="capabilities.isDesktop && desktopServerState === 'checking'"
    class="flex h-screen items-center justify-center bg-slate-50"
    aria-label="Loading MOVO"
  >
    <div class="flex h-14 w-16 items-center justify-center rounded-2xl bg-white shadow-lg" aria-hidden="true">
      <img src="/movo-logo.png" alt="" class="h-10 w-12 object-contain" />
    </div>
  </div>
  <DesktopServerSetup
    v-else-if="capabilities.isDesktop && desktopServerState === 'required'"
    @connected="handleDesktopServerConnected"
  />
  <div
    v-else
    class="app-shell relative flex h-screen bg-white text-gray-800 font-sans"
    :class="{ 'app-shell--desktop': capabilities.isDesktop }"
  >
    <CreateProjectDialog
      v-if="canUseCode"
      :show="createProjectOpen"
      :workspace="createProjectWorkspace"
      :worktree="createProjectWorktree"
      :busy="createProjectBusy"
      :locale="locale === 'en' ? 'en' : 'zh'"
      @update:worktree="(value) => createProjectWorktree = value"
      @choose-folder="chooseProjectFolder"
      @create="commitProjectCreate"
      @close="createProjectOpen = false"
    />
    <DesktopWindowChrome
      v-if="capabilities.isDesktop"
      :title="desktopWindowTitle"
      :chat-actions="currentView === 'chat'"
      :session-id="currentSessionId || undefined"
      :workspace="activeCodeState.workspace"
      :show-workspace-context="activeChatHasMessages"
      :workspace-branch="desktopWorkspaceSummary?.branch || activeCodeState.session?.git_branch || activeCodeState.workspace?.git_branch || ''"
      :workspace-source-ref="activeCodeState.sourceRef"
      :workspace-detached="activeCodeState.session?.detached_head"
      :code-session-active="Boolean(activeCodeState.session)"
      :workspace-busy="activeCodeState.busy"
      :worktree="activeCodeState.worktree"
      :locale="locale === 'en' ? 'en' : 'zh'"
      :active-tool="desktopActiveTool"
      :git-available="desktopWorkspaceSummary?.git_available === true"
      :change-count="desktopWorkspaceSummary?.changes.length || 0"
      :files-available="capabilities.workspaceFiles"
      :terminal-available="capabilities.projectTerminal"
      :code-available="canUseCode"
      :browser-available="canUseBrowser"
      @choose-workspace="requestDesktopWorkspace"
      @clear-workspace="codeRuntime.clear(activeChatKey)"
      @worktree="(enabled) => codeRuntime.setWorktree(activeChatKey, enabled)"
      @source-ref="(fullRef) => codeRuntime.setSourceRef(activeChatKey, fullRef)"
      @branch-updated="(branch) => codeRuntime.setWorkspaceBranch(activeChatKey, branch)"
      @open-browser="requestDesktopBrowser"
      @toggle-code-panel="toggleDesktopCodePanel"
    />
    <!-- SIDEBAR -->
    <aside class="app-sidebar w-[260px] bg-[#f8fafc] flex flex-col border-r border-gray-200 shadow-[1px_0_0_rgba(0,0,0,0.02)]">
      <div v-if="!capabilities.isDesktop" class="flex h-14 items-center gap-2.5 px-5" aria-label="MOVO">
        <img src="/movo-logo.png" alt="" class="h-8 w-10 object-contain" />
        <span class="text-[15px] font-extrabold tracking-[0.14em] text-slate-800">MOVO</span>
      </div>
      <!-- Top Actions -->
      <div class="space-y-0.5 px-3 pb-1 pt-3">
        <button
          v-for="item in sidebarItems"
          :key="item.label"
          class="group flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left text-sm font-medium transition-all active:scale-95"
          :class="item.icon === 'search' && sessionSearchOpen
            ? 'bg-white text-blue-700 shadow-sm border border-gray-200'
            : 'text-gray-700 hover:bg-gray-200/60'"
          @click="handleSidebarAction(item.icon)"
        >
          <span class="text-gray-500 group-hover:text-gray-900 transition-colors">
            <svg v-if="item.icon === 'plus'" xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14m-7-7v14"/></svg>
            <svg v-else-if="item.icon === 'clock'" xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>
            <svg v-else-if="item.icon === 'search'" xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
          </span>
          <span>{{ item.label }}</span>
        </button>
      </div>

      <!-- Scripts Section -->
      <button
        type="button"
        class="group mt-2 flex w-full items-center gap-1 px-5 pb-1 text-left text-[10px] font-bold uppercase tracking-[0.1em] text-gray-400"
        :aria-expanded="normalHistoryExpanded"
        @click="normalHistoryExpanded = !normalHistoryExpanded"
      >
        <span>{{ locale === 'en' ? 'Conversations' : '普通对话' }}</span>
        <svg class="h-3.5 w-3.5 opacity-100 transition-transform duration-150" :class="normalHistoryExpanded ? 'rotate-90' : ''" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="m5 3 5 5-5 5"/></svg>
      </button>
      <div class="flex-1 overflow-y-auto px-3 space-y-1 custom-scrollbar history-scrollbar">
        <div
          v-if="sessionsLoading"
          class="px-3 py-4 text-xs text-gray-400 animate-pulse italic text-center"
        >
          {{ t('app.sidebar.loading_history') }}
        </div>
        <div
          v-for="session in normalHistoryExpanded ? historyItems : []"
          :key="session.id"
          class="group w-full text-left px-2.5 py-1.5 rounded-lg transition-all border border-transparent"
          :class="session.id === currentSessionId && currentView === 'chat' 
            ? 'bg-white text-blue-700 shadow-sm border-gray-200 font-semibold' 
            : 'text-gray-600 hover:bg-gray-200/50 hover:text-gray-900'"
          @click="editingSessionId !== session.id && selectSession(session.id)"
          @keydown.enter.prevent="editingSessionId !== session.id && selectSession(session.id)"
          @keydown.space.prevent="editingSessionId !== session.id && selectSession(session.id)"
          role="button"
          tabindex="0"
        >
          <div class="flex min-w-0 items-center gap-2">
            <n-input
              v-if="editingSessionId === session.id"
              v-model:value="editingSessionTitle"
              size="small"
              class="min-w-0 flex-1"
              :data-session-title-input="session.id"
              :disabled="renamingSessionId === session.id"
              @click.stop
              @dblclick.stop
              @blur="commitSessionTitleEdit(session)"
              @keydown.enter.prevent="commitSessionTitleEdit(session)"
              @keydown.esc.prevent="cancelSessionTitleEdit"
            />
            <div
              v-else
              class="min-w-0 flex-1 text-[13px] truncate"
              :title="displaySessionTitle(session)"
              @dblclick.stop="startEditSessionTitle(session)"
            >
              {{ compactSessionTitle(session) }}
            </div>
            <span
              v-if="sessionNeedsHumanAssistance(session.id)"
              class="shrink-0 rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold text-amber-700"
              :aria-label="t('app.sidebar.session_needs_assistance')"
              :title="t('app.sidebar.session_needs_assistance')"
            >
              {{ t('app.sidebar.session_needs_assistance_short') }}
            </span>
            <div
              v-else-if="sessionScheduledIsRunning(session.id)"
              class="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-blue-50 text-blue-600"
              aria-label="定时任务正在运行"
              title="定时任务正在运行"
            >
              <svg viewBox="0 0 24 24" class="h-3.5 w-3.5 animate-pulse" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>
            </div>
            <div
              v-else-if="sessionIsRunning(session.id)"
              class="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-blue-50"
              :aria-label="t('app.sidebar.session_running')"
              :title="t('app.sidebar.session_running')"
            >
              <span class="h-1.5 w-1.5 rounded-full bg-blue-500 animate-pulse"></span>
            </div>
            <span
              v-else-if="sessionIsUnread(session.id)"
              class="h-2 w-2 shrink-0 rounded-full bg-blue-500"
              :aria-label="t('app.sidebar.session_unread')"
              :title="t('app.sidebar.session_unread')"
            ></span>
            <button
              type="button"
              class="shrink-0 overflow-hidden rounded-md p-0 text-gray-400 opacity-0 transition-all hover:bg-gray-200 hover:text-red-500 group-hover:w-6 group-hover:p-1 group-hover:opacity-100"
              :class="deletingSessionId === session.id ? 'w-6 !p-1 !opacity-100 text-red-500' : 'w-0'"
              :disabled="deletingSessionId === session.id"
              @click.stop="handleDeleteSession(session.id)"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/></svg>
            </button>
          </div>
        </div>
        <div v-if="canUseCode && supportsLocalCodeProjects && projectWorkspacesLoading" class="mt-5 flex items-center gap-2 px-3 py-2 text-xs text-slate-400">
          <span class="h-1.5 w-1.5 animate-pulse rounded-full bg-blue-500"></span>
          <span>{{ locale === 'en' ? 'Loading projects' : '正在加载项目' }}</span>
        </div>
        <section v-else-if="canUseCode && supportsLocalCodeProjects && projectHistoryGroups.length" class="mt-5 space-y-3" aria-label="项目对话">
          <div class="group flex items-center justify-between px-2 text-[10px] font-bold uppercase tracking-[0.1em] text-gray-400">
            <span>{{ locale === 'en' ? 'Projects' : '项目' }}</span>
            <button v-if="canUseCode && capabilities.localWorkspacePicker" type="button" class="flex h-4 w-4 items-center justify-center rounded text-blue-600 opacity-0 transition-opacity hover:bg-blue-50 group-hover:opacity-100" :aria-label="locale === 'en' ? 'Create project' : '创建项目'" :title="locale === 'en' ? 'Create project' : '创建项目'" @click="createProject"><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M8 3v10M3 8h10"/></svg></button>
          </div>
          <section v-for="group in projectHistoryGroups" :key="group.workspaceId" class="space-y-0.5">
            <button type="button" class="group flex w-full min-w-0 items-center gap-1.5 px-2 py-1 text-left text-xs font-semibold text-slate-500" :aria-expanded="projectHistoryExpanded(group.workspaceId)" :title="group.title" @click="toggleProjectHistory(group.workspaceId)">
              <svg v-if="projectHistoryExpanded(group.workspaceId)" class="h-4 w-4 shrink-0 text-slate-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M3 7.5h6l2 2h10v9.5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7.5Z"/></svg>
              <svg v-else class="h-4 w-4 shrink-0 text-slate-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M3 7.5h6l2 2h10v9.5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7.5Z"/><path d="M3 7.5V6a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v1.5"/></svg>
              <span class="truncate">{{ group.title }}</span>
            </button>
            <button
              v-for="session in projectHistoryExpanded(group.workspaceId) ? group.items : []"
              :key="session.id"
              type="button"
              class="flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-[13px] transition-all"
              :class="session.id === currentSessionId && currentView === 'chat' ? 'bg-white font-semibold text-blue-700 shadow-sm ring-1 ring-gray-200' : 'text-gray-600 hover:bg-gray-200/50 hover:text-gray-900'"
              :title="displaySessionTitle(session)"
              @click="selectSession(session.id)"
            >
              <span class="min-w-0 flex-1 truncate">{{ compactSessionTitle(session) }}</span>
              <span v-if="sessionIsRunning(session.id)" class="h-1.5 w-1.5 shrink-0 rounded-full bg-blue-500 animate-pulse"></span>
              <span v-else-if="sessionIsUnread(session.id)" class="h-2 w-2 shrink-0 rounded-full bg-blue-500"></span>
            </button>
          </section>
        </section>
        <button v-else-if="canUseCode && supportsLocalCodeProjects" type="button" class="mt-5 flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-sm text-slate-500 hover:bg-gray-200/50 hover:text-slate-700" @click="createProject">
          <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M3 7.5h6l2 2h10v9.5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7.5Z"/><path d="M12 11v6m-3-3h6"/></svg>
          <span>{{ locale === 'en' ? 'Create project' : '创建项目' }}</span>
        </button>
        <button
          v-if="!trimmedSessionSearchQuery && !sessionsLoading && sessionsHasMore && historyItems.length >= sessionPageSize"
          class="w-full text-left px-2.5 py-1 text-[11px] text-gray-400 hover:text-gray-600 disabled:opacity-60 disabled:cursor-not-allowed"
          :disabled="sessionsLoadingMore"
          @click="loadSessions(false)"
        >
          {{ sessionsLoadingMore ? t('ui.loading') : t('app.sidebar.load_more') }}
        </button>
      </div>

      <div v-if="canUseSkills || canUseTools" class="mt-2 px-5 pb-1 text-[10px] font-bold text-gray-400 uppercase tracking-[0.1em]">{{ t('app.sidebar.skills') }}</div>
      <div v-if="canUseSkills || canUseTools" class="mb-2 space-y-0.5 px-3">
        <button
          v-if="canUseSkills"
          class="flex w-full items-center gap-3 rounded-xl border border-transparent px-3 py-2 text-left text-sm transition-all active:scale-95"
          :class="currentView === 'skills' 
            ? 'bg-white text-blue-700 shadow-sm border-gray-200 font-semibold' 
            : 'text-gray-700 hover:bg-gray-200/50'"
          @click="openSkillsPage"
        >
          <span class="text-gray-500">
            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M20 7l.94-2.06L23 4l-2.06-.94L20 1l-.94 2.06L17 4l2.06.94zM8.5 7l.94-2.06L11.5 4l-2.06-.94L8.5 1l-.94 2.06L5.5 4l2.06.94zM20 12.5l-.94 2.06l-2.06.94l2.06.94l.94 2.06l.94-2.06L23 15.5l-2.06-.94zm-2.29-3.38l-2.83-2.83c-.2-.19-.45-.29-.71-.29c-.26 0-.51.1-.71.29L2.29 17.46a.996.996 0 0 0 0 1.41l2.83 2.83c.2.2.45.3.71.3s.51-.1.71-.29l11.17-11.17c.39-.39.39-1.03 0-1.42zm-3.54-.7l1.41 1.41L14.41 11L13 9.59l1.17-1.17zM5.83 19.59l-1.41-1.41L11.59 11L13 12.41l-7.17 7.18z"/></svg>
          </span>
          <span>{{ t('app.sidebar.marketplace') }}</span>
        </button>
        <button
          v-if="canUseTools"
          class="flex w-full items-center gap-3 rounded-xl border border-transparent px-3 py-2 text-left text-sm transition-all active:scale-95"
          :class="currentView === 'tools' 
            ? 'bg-white text-blue-700 shadow-sm border-gray-200 font-semibold' 
            : 'text-gray-700 hover:bg-gray-200/50'"
          @click="openToolsPage"
        >
          <span class="text-gray-500">
            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path opacity=".3" d="M3 10.5c-.55 0-1-.45-1-1s.45-1 1-1s1 .45 1 1s-.45 1-1 1zM6 21c-.55 0-1-.45-1-1s.45-1 1-1s1 .45 1 1s-.45 1-1 1zm5-18c0-.55.45-1 1-1s1 .45 1 1s-.45 1-1 1s-1-.45-1-1zm1 12a2.5 2.5 0 0 1 0-5a2.5 2.5 0 0 1 0 5zm6 4c.55 0 1 .45 1 1s-.45 1-1 1s-1-.45-1-1s.45-1 1-1zm3-8.5c-.55 0-1-.45-1-1s.45-1 1-1s1 .45 1 1s-.45 1-1 1z" /><path d="M21 6.5a2.996 2.996 0 0 0-2.99 3.21l-2.03.68a4.468 4.468 0 0 0-3.22-2.32V5.91A3.018 3.018 0 0 0 15 3c0-1.66-1.34-3-3-3S9 1.34 9 3c0 1.4.96 2.57 2.25 2.91v2.16c-1.4.23-2.58 1.11-3.22 2.32l-2.04-.68C6 9.64 6 9.57 6 9.5c0-1.66-1.34-3-3-3s-3 1.34-3 3s1.34 3 3 3c1.06 0 1.98-.55 2.52-1.37l2.03.68c-.2 1.29.17 2.66 1.09 3.69l-1.41 1.77C6.85 17.09 6.44 17 6 17c-1.66 0-3 1.34-3 3s1.34 3 3 3s3-1.34 3-3c0-.68-.22-1.3-.6-1.8l1.41-1.77c1.36.76 3.02.75 4.37 0l1.41 1.77c-.37.5-.59 1.12-.59 1.8c0 1.66 1.34 3 3 3s3-1.34 3-3s-1.34-3-3-3c-.44 0-.85.09-1.23.26l-1.41-1.77a4.49 4.49 0 0 0 1.09-3.69l2.03-.68c.53.82 1.46 1.37 2.52 1.37c1.66 0 3-1.34 3-3S22.66 6.5 21 6.5zm-18 4c-.55 0-1-.45-1-1s.45-1 1-1s1 .45 1 1s-.45 1-1 1zM6 21c-.55 0-1-.45-1-1s.45-1 1-1s1 .45 1 1s-.45 1-1 1zm5-18c0-.55.45-1 1-1s1 .45 1 1s-.45 1-1 1s-1-.45-1-1zm1 12a2.5 2.5 0 0 1 0-5a2.5 2.5 0 0 1 0 5zm6 4c.55 0 1 .45 1 1s-.45 1-1 1s-1-.45-1-1s.45-1 1-1zm3-8.5c-.55 0-1-.45-1-1s.45-1 1-1s1 .45 1 1s-.45 1-1 1z" /></svg>
          </span>
          <span>{{ t('app.sidebar.tools') }}</span>
        </button>
      </div>

      <!-- User Profile (Bottom) -->
      <div class="p-4 border-t border-gray-200 bg-white/50" data-user-menu>
        <div
          v-if="isLoggedIn"
          class="flex items-center gap-3 p-2 rounded-xl hover:bg-gray-200/70 cursor-pointer transition-colors"
          @click.stop="toggleUserMenu"
        >
          <div class="w-9 h-9 rounded-xl overflow-hidden bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center text-white font-bold shadow-sm">
            <img v-if="displayAvatar()" :src="displayAvatar()" alt="" class="w-full h-full object-cover" @error="handleAvatarError" />
            <span v-else>{{ displayAvatarText() }}</span>
          </div>
          <div class="flex-1 min-w-0">
            <div class="text-xs font-semibold text-gray-900 truncate">{{ displayName() }}</div>
            <div class="text-[10px] text-gray-400 font-medium">
              {{ accountTierLabel }}
            </div>
          </div>
          <svg class="w-3 h-3 text-gray-400 shrink-0" xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg>
        </div>
        <div v-else class="flex items-center gap-3 p-2 rounded-xl hover:bg-gray-200/70 cursor-pointer transition-colors" @click="openLogin">
          <div class="w-9 h-9 rounded-xl bg-gray-200 flex items-center justify-center text-gray-400 font-bold border border-gray-300 border-dashed">
            ?
          </div>
          <div class="text-sm font-semibold text-gray-700">{{ t('app.sidebar.login_register') }}</div>
        </div>
        
        <!-- User Menu Popup -->
        <div
          v-if="userMenuOpen && isLoggedIn"
          class="fixed bottom-20 left-4 z-[80] w-[360px] max-w-[calc(100vw-2rem)] rounded-2xl border border-gray-200 bg-white shadow-[0_18px_56px_rgba(15,23,42,0.14)] p-3 text-sm text-gray-700 animate-in fade-in slide-in-from-bottom-2 duration-200"
        >
          <div class="flex items-center gap-3 px-2 pb-3 pt-1">
            <div class="flex h-10 w-10 shrink-0 items-center justify-center overflow-hidden rounded-xl bg-blue-600 font-bold text-white">
              <img v-if="displayAvatar()" :src="displayAvatar()" alt="" class="h-full w-full object-cover" @error="handleAvatarError" />
              <span v-else>{{ displayAvatarText() }}</span>
            </div>
            <div class="min-w-0 flex-1">
              <div class="truncate font-semibold text-gray-900">{{ displayName() }}</div>
              <div class="mt-0.5 text-xs text-gray-500">
                {{ maskedPhone() || accountTierLabel }}
                <span v-if="maskedPhone()" class="mx-1 text-gray-300">·</span>
                <span v-if="maskedPhone()">{{ accountTierLabel }}</span>
              </div>
            </div>
            <button
               type="button"
               class="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-700"
               :aria-label="t('ui.edit_profile')"
               :title="t('ui.edit_profile')"
               @click.stop="openProfileEditor"
             >
               <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
                 <path d="M12 20h9"/>
                 <path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z"/>
               </svg>
             </button>
           </div>

           <div class="mb-3 rounded-xl bg-slate-50 px-3 py-3">
             <div class="flex items-start justify-between gap-3">
               <div>
                 <div class="text-[11px] font-medium text-slate-500">{{ t('ui.quota_remaining') }}</div>
                 <div v-if="billingSummary" class="mt-1 text-xl font-bold text-slate-900" :title="`${formatExactTokenAmount(quotaRemaining, locale)} Token`">
                   {{ formatTokenCount(quotaRemaining) }}
                 </div>
                 <div v-else-if="billingSummaryLoading || !billingSummaryLoaded" class="mt-2 h-6 w-20 animate-pulse rounded bg-slate-200"></div>
                 <div v-else class="mt-1 text-sm font-medium text-slate-500">{{ t('ui.quota_unavailable') }}</div>
               </div>
               <div v-if="billingSummary" class="text-right text-[11px] leading-5 text-slate-500">
                 <div :title="`${formatExactTokenAmount(quotaTotal, locale)} Token`">{{ quotaTotalLabel }} {{ formatTokenCount(quotaTotal) }}</div>
                 <div>{{ t('ui.quota_used') }} {{ quotaUsedPercentLabel }}%</div>
               </div>
             </div>
             <div class="mt-3 h-1.5 overflow-hidden rounded-full bg-slate-200" :aria-label="t('ui.quota_usage_progress')">
               <div
                 class="h-full rounded-full bg-blue-600 transition-all duration-300"
                 :style="{ width: `${quotaUsedPercent}%` }"
               ></div>
             </div>
             <button
               type="button"
               class="mt-2 flex min-h-[32px] w-full items-center justify-between text-xs font-medium text-slate-600 transition-colors hover:text-slate-900"
               @click="openTokenUsagePage"
             >
               <span>{{ t('ui.view_usage_history') }}</span>
               <svg class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
                 <path d="m9 18 6-6-6-6"/>
               </svg>
             </button>
           </div>

           <div class="px-1 py-1">
             <div class="mb-1 text-[10px] font-bold text-gray-400 uppercase tracking-widest">{{ locale === 'zh' ? '组织' : 'Organization' }}</div>
             <div v-if="availableTenants.length" class="space-y-1 max-h-40 overflow-auto pr-1">
               <div
                 v-for="tenant in availableTenants"
                 :key="tenant.mainId"
                 class="flex min-h-[48px] w-full items-center gap-1 rounded-xl px-2 transition-colors"
                 :class="tenant.mainId === getMainId() ? 'bg-blue-50 text-blue-700' : 'hover:bg-gray-50 text-gray-700'"
               >
                 <button
                   type="button"
                   class="min-w-0 flex-1 px-1 py-2 text-left leading-5 disabled:cursor-wait disabled:opacity-60"
                   :disabled="switchingTenant || adminSsoStarting"
                   @click="handleSwitchTenant(tenant.mainId)"
                 >
                   <span class="block whitespace-normal break-words font-medium">{{ tenant.orgName || tenant.mainId }}</span>
                   <span v-if="isEnterpriseTenant(tenant)" class="mt-0.5 block text-[11px] font-normal text-slate-400">
                     {{ t('ui.enterprise_space') }}
                   </span>
                 </button>
                 <button
                   v-if="canAccessAdmin(tenant)"
                   type="button"
                   class="flex min-h-9 shrink-0 items-center gap-1 rounded-lg px-2 text-xs font-medium text-slate-500 transition-colors hover:bg-white hover:text-blue-600 disabled:cursor-wait disabled:opacity-50"
                   :aria-label="t('ui.enter_tenant_admin', { org: tenant.orgName || tenant.mainId })"
                   :title="t('ui.enter_tenant_admin', { org: tenant.orgName || tenant.mainId })"
                   :disabled="switchingTenant || adminSsoStarting"
                   @click.stop="openAdminConsole(tenant.mainId)"
                 >
                   <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
                     <rect x="3" y="4" width="18" height="14" rx="2"/>
                     <path d="M8 21h8M12 18v3M7 9h4M7 13h7"/>
                   </svg>
                   <span>{{ t('ui.admin_short') }}</span>
                 </button>
               </div>
             </div>
             <div v-else class="rounded-xl bg-blue-50 px-3 py-2.5 font-medium text-blue-700">
               {{ userProfile?.orgName || t('ui.personal_space') }}
             </div>
             <button
               v-if="canCreateOrganization"
               type="button"
               class="mt-1 flex min-h-[40px] w-full items-center gap-2 rounded-xl px-3 text-left font-medium text-blue-600 transition-colors hover:bg-blue-50"
               @click="openCreateOrganization"
             >
               <svg class="h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
                 <path d="M12 5v14M5 12h14"/>
               </svg>
               {{ t('ui.create_enterprise') }}
             </button>
           </div>
           <button v-if="canUpgradePlan" @click="openBilling" class="mt-1 flex w-full items-center gap-2 rounded-xl px-3 py-2.5 text-left transition-colors hover:bg-gray-50">
             <svg class="h-4 w-4 shrink-0 text-gray-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect width="20" height="14" x="2" y="5" rx="2"/><line x1="2" x2="22" y1="10" y2="10"/></svg>
             {{ t('app.account.upgrade') }}
           </button>
           <button class="flex w-full items-center gap-2 rounded-xl px-3 py-2.5 text-left transition-colors hover:bg-gray-50" @click="openProfileEditor">
             <svg class="h-4 w-4 shrink-0 text-gray-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
               <path d="M20 21a8 8 0 0 0-16 0"/>
               <circle cx="12" cy="7" r="4"/>
             </svg>
             {{ t('ui.edit_profile') }}
           </button>
          <button class="flex w-full items-center gap-2 rounded-xl px-3 py-2.5 text-left transition-colors hover:bg-gray-50" @click="openPersonalization">
            <svg class="h-4 w-4 shrink-0 text-gray-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
              <circle cx="13.5" cy="6.5" r=".5" fill="currentColor"/>
              <circle cx="17.5" cy="10.5" r=".5" fill="currentColor"/>
              <circle cx="8.5" cy="7.5" r=".5" fill="currentColor"/>
              <circle cx="6.5" cy="12.5" r=".5" fill="currentColor"/>
              <path d="M12 22a10 10 0 1 1 10-10c0 2.2-1.8 4-4 4h-1.8a1.8 1.8 0 0 0-1.4 3l.2.3A1.7 1.7 0 0 1 13.6 22Z"/>
            </svg>
            {{ t('app.account.personalization') }}
          </button>
          <button
            v-if="capabilities.isDesktop"
            class="flex w-full items-center gap-2 rounded-xl px-3 py-2.5 text-left transition-colors hover:bg-gray-50"
            @click="openSettingsPanel"
          >
            <svg class="h-4 w-4 shrink-0 text-gray-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
              <circle cx="12" cy="12" r="3"/>
              <path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.83 2.83-.06-.06A1.7 1.7 0 0 0 15 19.4a1.7 1.7 0 0 0-1 .6 1.7 1.7 0 0 0-.4 1.1V21h-4v-.09A1.7 1.7 0 0 0 8.6 19.4a1.7 1.7 0 0 0-1.88.34l-.06.06-2.83-2.83.06-.06A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-.6-1 1.7 1.7 0 0 0-1.1-.4H3v-4h.09A1.7 1.7 0 0 0 4.6 8.6a1.7 1.7 0 0 0-.34-1.88l-.06-.06 2.83-2.83.06.06A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-.6 1.7 1.7 0 0 0 .4-1.1V3h4v.09A1.7 1.7 0 0 0 15.4 4.6a1.7 1.7 0 0 0 1.88-.34l.06-.06 2.83 2.83-.06.06A1.7 1.7 0 0 0 19.4 9c.18.37.39.7.6 1 .26.35.4.77.4 1.2v1.6c0 .43-.14.85-.4 1.2-.21.3-.42.63-.6 1Z"/>
            </svg>
            {{ t('app.account.settings') }}
          </button>
          <div class="h-px bg-gray-100 my-2"></div>
          <button class="w-full rounded-xl px-3 py-2.5 text-left font-medium text-red-600 transition-colors hover:bg-red-50" @click="logout">
            {{ t('app.account.logout') }}
          </button>
        </div>
      </div>
    </aside>

    <!-- MAIN CONTENT -->
    <main class="app-main flex-1 flex flex-col min-w-0 min-h-0 bg-white">

      <!-- Main Area -->
      <div class="flex-1 flex min-w-0 min-h-0 overflow-hidden">
        <div v-if="currentView === 'skills'" class="flex-1 min-w-0 min-h-0 overflow-hidden">
          <SkillsPage
            :userId="getUserId()"
            :mainId="getMainId()"
            @back="closeSkillsPage"
            @configure="openSkillConfig"
          />
        </div>
        <div v-else-if="currentView === 'tools'" class="flex-1 min-w-0 min-h-0 overflow-hidden">
          <ToolsPage
            :userId="getUserId()"
            :mainId="getMainId()"
            @back="closeToolsPage"
          />
        </div>
        <div v-else-if="currentView === 'skill-config'" class="flex-1 min-w-0 min-h-0 overflow-hidden">
          <SkillConfigPage
            :skill="selectedSkill"
            :userId="getUserId()"
            :mainId="getMainId()"
            @back="closeSkillConfig"
            @saved="handleCompositeSaved"
          />
        </div>
        <div v-else-if="currentView === 'composite-editor'" class="flex-1 min-w-0 min-h-0 overflow-hidden">
          <CompositeSkillEditor
            :skill="selectedSkill"
            :userId="getUserId()"
            @back="closeSkillConfig"
            @saved="handleCompositeSaved"
            @remove="removeSkill"
          />
        </div>
        <div v-else-if="currentView === 'scheduled-tasks'" class="flex-1 min-w-0 min-h-0 overflow-hidden">
          <ScheduledTaskPage
            :token="authToken"
            :sessions="sessions"
            :current-session-id="scheduledTaskInitialSessionId || currentSessionId"
            :timezone="timezoneValue"
            :initial-prompt="scheduledTaskInitialPrompt"
            :create-request-key="scheduledTaskCreateRequestKey"
            @back="navigateTo('chat')"
            @open-session="selectSession"
          />
        </div>
        <div v-else-if="currentView === 'token-usage'" class="flex-1 min-w-0 min-h-0 overflow-hidden">
          <TokenUsagePage
            :user-id="getUserId()"
            :main-id="getMainId()"
            :token="authToken"
            @back="closeTokenUsagePage"
          />
        </div>
        <template v-else>
          <div class="flex-1 relative overflow-hidden min-h-0">
            <div
              v-if="sessionSearchOpen"
              class="absolute inset-0 z-20 flex items-start justify-center bg-white/45 backdrop-blur-[2px] px-6 pt-20"
              @click.self="closeSessionSearch"
            >
              <div class="w-full max-w-[720px] overflow-hidden rounded-[28px] border border-gray-200 bg-white shadow-[0_24px_80px_rgba(15,23,42,0.12)]">
                <div class="flex items-center gap-3 border-b border-gray-100 px-6 py-5">
                  <n-input
                    v-model:value="sessionSearchQuery"
                    clearable
                    :placeholder="t('app.search.placeholder')"
                    size="large"
                    class="flex-1"
                  />
                  <button
                    class="shrink-0 rounded-full p-2 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-700"
                    @click="closeSessionSearch"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
                  </button>
                </div>
                <div class="max-h-[60vh] overflow-y-auto px-3 py-3 custom-scrollbar">
                  <button
                    class="mb-3 flex w-full items-center gap-3 rounded-2xl bg-gray-50 px-5 py-4 text-left text-gray-700 transition-colors hover:bg-gray-100"
                    @click="() => startLocalSession()"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14"/><path d="M5 12h14"/></svg>
                    <span class="text-base font-medium">{{ t('app.sidebar.new_chat') }}</span>
                  </button>

                  <div v-if="!trimmedSessionSearchQuery" class="px-4 py-2 text-xs font-semibold uppercase tracking-[0.12em] text-gray-400">
                    {{ t('app.search.recent') }}
                  </div>
                  <div
                    v-else-if="sessionSearchLoading && !sessionSearchResults.length"
                    class="px-4 py-8 text-center text-sm italic text-gray-400"
                  >
                    {{ t('app.search.searching') }}
                  </div>
                  <div
                    v-else-if="sessionSearchDidRun && !sessionSearchResults.length"
                    class="px-4 py-8 text-center text-sm italic text-gray-400"
                  >
                    {{ t('app.search.no_results') }}
                  </div>

                  <div
                    v-for="session in sessionSearchDisplayItems"
                    :key="session.id"
                    class="group flex w-full items-center gap-3 rounded-2xl px-4 py-3 text-left transition-colors"
                    :class="session.id === currentSessionId
                      ? 'bg-gray-100 text-gray-900'
                      : 'text-gray-700 hover:bg-gray-50'"
                    @click="editingSessionId !== session.id && selectSession(session.id)"
                    @keydown.enter.prevent="editingSessionId !== session.id && selectSession(session.id)"
                    @keydown.space.prevent="editingSessionId !== session.id && selectSession(session.id)"
                    role="button"
                    tabindex="0"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="shrink-0 text-gray-400"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
                    <n-input
                      v-if="editingSessionId === session.id"
                      v-model:value="editingSessionTitle"
                      size="small"
                      class="min-w-0 flex-1"
                      :data-session-title-input="session.id"
                      :disabled="renamingSessionId === session.id"
                      @click.stop
                      @dblclick.stop
                      @blur="commitSessionTitleEdit(session)"
                      @keydown.enter.prevent="commitSessionTitleEdit(session)"
                      @keydown.esc.prevent="cancelSessionTitleEdit"
                    />
                    <span
                      v-else
                      class="min-w-0 flex-1 truncate text-base"
                      :title="displaySessionTitle(session)"
                      @dblclick.stop="startEditSessionTitle(session)"
                    >
                      {{ compactSessionTitle(session, 44) }}
                    </span>
                    <span
                      v-if="sessionNeedsHumanAssistance(session.id)"
                      class="shrink-0 rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold text-amber-700"
                      :aria-label="t('app.sidebar.session_needs_assistance')"
                      :title="t('app.sidebar.session_needs_assistance')"
                    >
                      {{ t('app.sidebar.session_needs_assistance_short') }}
                    </span>
                    <span
                      v-else-if="sessionScheduledIsRunning(session.id)"
                      class="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-blue-50 text-blue-600"
                      aria-label="定时任务正在运行"
                      title="定时任务正在运行"
                    >
                      <svg viewBox="0 0 24 24" class="h-3.5 w-3.5 animate-pulse" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>
                    </span>
                    <span
                      v-else-if="sessionIsRunning(session.id)"
                      class="h-2 w-2 shrink-0 rounded-full bg-blue-500 animate-pulse"
                      :aria-label="t('app.sidebar.session_running')"
                      :title="t('app.sidebar.session_running')"
                    ></span>
                    <span
                      v-else-if="sessionIsUnread(session.id)"
                      class="h-2 w-2 shrink-0 rounded-full bg-blue-500"
                      :aria-label="t('app.sidebar.session_unread')"
                      :title="t('app.sidebar.session_unread')"
                    ></span>
                    <button
                      type="button"
                      class="shrink-0 overflow-hidden rounded-md p-0 text-gray-400 opacity-0 transition-all hover:bg-gray-100 hover:text-red-500 group-hover:w-6 group-hover:p-1 group-hover:opacity-100"
                      :class="deletingSessionId === session.id ? 'w-6 !p-1 !opacity-100 text-red-500' : 'w-0'"
                      :disabled="deletingSessionId === session.id"
                      @click.stop="handleDeleteSession(session.id)"
                    >
                      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/></svg>
                    </button>
                  </div>

                  <button
                    v-if="trimmedSessionSearchQuery && sessionSearchDidRun && sessionSearchHasMore"
                    class="mt-3 w-full rounded-xl border border-gray-200 px-3 py-2 text-sm text-gray-600 transition-colors hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-60"
                    :disabled="sessionSearchLoading"
                    @click="runSessionSearch(false)"
                  >
                    {{ sessionSearchLoading ? t('app.search.searching') : t('app.search.load_more_results') }}
                  </button>
                </div>
              </div>
            </div>
          <div
            v-for="pane in visibleChatPanes"
            v-show="pane.key === activeChatKey"
            :key="pane.key"
            class="h-full w-full"
          >
            <ChatWindow
              :initial-messages="pane.messages"
              :session-id="pane.sessionId || undefined"
              :active="pane.key === activeChatKey"
              :user-id="getUserId() || undefined"
              :main-id="getMainId()"
              :auth-token="authToken"
              :running="pane.running"
              :active-intervention="pane.activeIntervention"
              :code-workspace="codeRuntime.stateFor(pane.key).workspace"
              :code-session="codeRuntime.stateFor(pane.key).session"
              :code-events="codeRuntime.stateFor(pane.key).events"
              :code-approvals="codeRuntime.stateFor(pane.key).approvals"
              :code-approval-busy="codeRuntime.stateFor(pane.key).approvalBusy"
              :code-error="codeRuntime.stateFor(pane.key).error"
              :code-workspace-busy="codeRuntime.stateFor(pane.key).busy"
              :code-worktree="codeRuntime.stateFor(pane.key).worktree"
              :code-source-ref="codeRuntime.stateFor(pane.key).sourceRef"
              :code-history-read-only="pane.executionLocation !== 'server' && !codeRuntime.stateFor(pane.key).session"
              :code-history-location="pane.executionLocation === 'server' ? undefined : pane.executionLocation"
              :code-history-project="pane.codeProject"
              :desktop-workspace-request="desktopWorkspaceRequest"
              :desktop-browser-request="desktopBrowserRequest"
              :desktop-tool-tabs="pane.key === activeChatKey ? desktopToolTabs : []"
              :desktop-active-tool="pane.key === activeChatKey ? desktopActiveTool : null"
              :desktop-available-tools="pane.key === activeChatKey ? desktopAvailableTools : []"
              :desktop-code-review-path="pane.key === activeChatKey ? desktopCodeReviewPath : ''"
              :desktop-code-review-changes="pane.key === activeChatKey ? desktopCodeReviewChanges : null"
              :desktop-code-file-path="pane.key === activeChatKey ? desktopCodeFilePath : ''"
              :agent-policy="userProfile?.agentPolicy"
              @send="(payload) => handlePaneSend(pane.key, payload)"
              @stop="handlePaneStop(pane.key)"
              @open-skills="openSkillsPage"
              @open-tools="openToolsPage"
              @schedule-message="({ prompt, sessionId }) => openScheduledTasks({ prompt, sessionId, create: true })"
              @clear-intervention="chatRuntime.clearPaneIntervention(pane.key)"
              @approval-decided="refreshSessionSummaries"
              @choose-code-workspace="(modelId) => codeRuntime.choose(pane.key, modelId)"
              @clear-code-workspace="codeRuntime.clear(pane.key)"
              @code-worktree="(enabled) => codeRuntime.setWorktree(pane.key, enabled)"
              @code-source-ref="(fullRef) => codeRuntime.setSourceRef(pane.key, fullRef)"
              @code-branch-updated="(branch) => codeRuntime.setWorkspaceBranch(pane.key, branch)"
              @code-approval="(approvalId, decision, scope) => codeRuntime.decide(pane.key, approvalId, decision, scope)"
              @close-code-panel="desktopActiveTool = null"
              @select-desktop-tool="selectDesktopTool"
              @close-desktop-tool="closeDesktopTool"
              @open-desktop-tool="openDesktopTool"
              @code-workspace-change="refreshDesktopWorkspaceSummary"
              @review-code-changes="reviewCodeChanges"
              @open-code-file="openCodeFile"
            />
          </div>
          </div>
        </template>
      </div>
    </main>
    <LoginModal
      :open="loginOpen"
      :saved-users="savedUsers"
      @close="loginOpen = false"
      @login-success="handleLoginSuccess"
    />
    <BillingModal
      :open="billingOpen"
      :token="authToken"
      :can-access-admin="isEnterpriseSpace && userProfile?.canAccessAdmin === true"
      @close="billingOpen = false"
      @upgrade-success="handleBillingSuccess"
    />
    <ProfileModal
      :open="profileOpen"
      :token="authToken"
      :profile="userProfile"
      @close="profileOpen = false"
      @updated="handleProfileUpdated"
    />
    <CreateOrganizationModal
      :open="createOrganizationOpen"
      :token="authToken"
      @close="createOrganizationOpen = false"
      @created="handleOrganizationCreated"
    />

    <div
      v-if="pendingDeleteSession"
      class="fixed inset-0 z-[70] flex items-center justify-center bg-slate-900/22 px-4 backdrop-blur-[2px]"
      @click.self="cancelDeleteSession"
    >
      <div class="w-full max-w-md rounded-[24px] border border-gray-200 bg-white p-6 shadow-[0_24px_80px_rgba(15,23,42,0.18)]">
        <div class="text-lg font-semibold text-gray-900">{{ t('app.delete_chat.title') }}</div>
        <div class="mt-3 text-sm leading-6 text-gray-500">
          {{ t('app.delete_chat.body', { title: pendingDeleteSession.title || t('app.sidebar.new_chat') }) }}
        </div>
        <div class="mt-6 flex items-center justify-end gap-3">
          <button
            type="button"
            class="rounded-xl px-4 py-2.5 text-sm font-medium text-gray-500 transition-colors hover:bg-gray-100 hover:text-gray-700"
            @click="cancelDeleteSession"
          >
            {{ t('ui.cancel') }}
          </button>
          <button
            type="button"
            class="rounded-xl bg-red-500 px-4 py-2.5 text-sm font-medium text-white shadow-sm transition-colors hover:bg-red-600 disabled:cursor-not-allowed disabled:opacity-60"
            :disabled="deletingSessionId === pendingDeleteSession.id"
            @click="confirmDeleteSession"
          >
            {{ deletingSessionId === pendingDeleteSession.id ? t('app.delete_chat.deleting') : t('ui.delete') }}
          </button>
        </div>
      </div>
    </div>
  </div>

  <div v-if="skillFormOpen" class="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
    <div class="w-[820px] max-h-[88vh] overflow-y-auto rounded-3xl bg-white shadow-xl border border-gray-200 p-6 custom-scrollbar">
      <div class="flex items-center justify-between mb-3">
        <div>
          <div class="text-lg font-semibold text-gray-900">{{ t('app.skill_form.title') }}</div>
          <div class="text-xs text-gray-500 mt-1">{{ t('app.skill_form.subtitle') }}</div>
        </div>
        <n-button text size="small" class="!text-gray-400 hover:!text-gray-600" @click="closeSkillForm">{{ t('ui.close') }}</n-button>
      </div>
      <div class="space-y-5">
        <section class="rounded-2xl border border-gray-200 bg-gray-50/60 p-4">
          <div class="flex items-center justify-between mb-4">
            <div>
              <div class="text-sm font-semibold text-gray-900">{{ t('app.skill_form.basics') }}</div>
              <div class="text-xs text-gray-500 mt-1">{{ t('app.skill_form.basics_hint') }}</div>
            </div>
            <n-button
              size="small"
              secondary
              :class="canSmartFillSkill ? 'border border-amber-200 bg-gradient-to-r from-amber-50 to-orange-50 text-amber-700 shadow-sm hover:from-amber-100 hover:to-orange-100' : 'border border-gray-200 text-gray-400 bg-white'"
              :disabled="skillEnriching || !canSmartFillSkill"
              @click="enrichDraftFromForm"
            >
              {{ skillEnriching ? t('app.skill_form.smart_fill_loading') : t('app.skill_form.smart_fill') }}
            </n-button>
          </div>
          <div class="grid grid-cols-2 gap-4">
            <div class="col-span-2">
              <label class="block text-xs font-semibold text-gray-700 mb-1">{{ t('app.skill_form.skill_name') }}</label>
              <n-input
                v-model:value="skillName"
                :placeholder="t('app.skill_form.skill_name_placeholder')"
              />
            </div>
            <div class="col-span-2">
              <label class="block text-xs font-semibold text-gray-700 mb-1">{{ t('app.skill_form.short_summary') }}</label>
              <n-input
                v-model:value="skillSummary"
                :placeholder="t('app.skill_form.short_summary_placeholder')"
              />
            </div>
            <div>
              <label class="block text-xs font-semibold text-gray-700 mb-1">{{ t('app.skill_form.skill_type') }}</label>
              <n-select v-model:value="skillType" :options="skillTypeOptions" />
            </div>
            <div>
              <label class="block text-xs font-semibold text-gray-700 mb-1">{{ t('app.skill_form.applicable_scenarios') }}</label>
              <n-input
                v-model:value="skillScenario"
                type="textarea"
                :autosize="{ minRows: 3, maxRows: 5 }"
                :placeholder="t('app.skill_form.scenario_placeholder')"
              />
            </div>
          </div>
        </section>

        <section class="rounded-2xl border border-gray-200 bg-white p-4">
          <div class="text-sm font-semibold text-gray-900 mb-1">{{ t('app.skill_form.positioning') }}</div>
          <div class="text-xs text-gray-500 mb-4">{{ t('app.skill_form.positioning_hint') }}</div>
          <div class="grid grid-cols-2 gap-4">
            <div class="flex min-h-[220px] flex-col">
              <label class="block text-xs font-semibold text-gray-700 mb-1">{{ t('app.skill_form.publish_channels') }}</label>
              <TokenInput v-model="skillChannels" :suggestions="publishChannelSuggestions" :placeholder="t('skill_config.add_channels')" />
            </div>
            <div class="flex min-h-[220px] flex-col">
              <label class="block text-xs font-semibold text-gray-700 mb-1">{{ t('app.skill_form.content_forms') }}</label>
              <TokenInput v-model="skillForms" :suggestions="contentFormSuggestions" :placeholder="t('skill_config.add_content_forms')" />
            </div>
            <div class="flex min-h-[220px] flex-col">
              <label class="block text-xs font-semibold text-gray-700 mb-1">{{ t('app.skill_form.target_audience') }}</label>
              <TokenInput v-model="skillAudience" :suggestions="targetAudienceSuggestions" :placeholder="t('skill_config.add_audiences')" />
            </div>
            <div class="flex min-h-[220px] flex-col">
              <label class="block text-xs font-semibold text-gray-700 mb-1">{{ t('app.skill_form.preferred_style') }}</label>
              <TokenInput v-model="skillStyle" :suggestions="preferredStyleSuggestions" :placeholder="t('skill_config.add_styles')" />
            </div>
          </div>
        </section>

        <section class="rounded-2xl border border-gray-200 bg-white p-4">
          <div class="text-sm font-semibold text-gray-900 mb-1">{{ t('app.skill_form.constraints') }}</div>
          <div class="text-xs text-gray-500 mb-4">{{ t('app.skill_form.constraints_hint') }}</div>
          <div class="grid grid-cols-2 gap-4">
            <div class="min-w-0">
              <label class="block text-xs font-semibold text-gray-700 mb-1">{{ t('app.skill_form.must_include') }}</label>
              <TokenInput v-model="skillRequired" :placeholder="t('skill_config.add_required')" />
            </div>
            <div class="min-w-0">
              <label class="block text-xs font-semibold text-gray-700 mb-1">{{ t('app.skill_form.must_avoid') }}</label>
              <TokenInput v-model="skillForbidden" :placeholder="t('skill_config.add_forbidden')" />
            </div>
          </div>
        </section>

        <div class="flex justify-end gap-2 pt-1">
          <n-button size="small" @click="closeSkillForm">
            {{ t('ui.cancel') }}
          </n-button>
          <n-button
            size="small"
            type="primary"
            :disabled="skillCreating || !skillName.trim()"
            @click="createSkill"
          >
            {{ skillCreating ? t('app.skill_form.generating') : t('ui.generate') }}
          </n-button>
        </div>
      </div>
    </div>
  </div>
  <div
    v-if="personalizationOpen"
    class="fixed inset-0 z-[90] flex items-center justify-center bg-slate-900/30 px-4 backdrop-blur-[2px]"
    @click.self="closePersonalization"
  >
    <div class="w-full max-w-md rounded-2xl border border-gray-200 bg-white p-5 shadow-[0_24px_80px_rgba(15,23,42,0.18)]">
      <div class="mb-5 flex items-start justify-between gap-4">
        <div>
          <div class="text-lg font-semibold text-gray-900">{{ t('app.account.personalization') }}</div>
          <div class="mt-1 text-sm text-gray-500">{{ t('ui.personalization_desc') }}</div>
        </div>
        <button
          type="button"
          class="flex h-9 w-9 items-center justify-center rounded-lg text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-700"
          :aria-label="t('ui.close')"
          @click="closePersonalization"
        >
          <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <path d="M18 6 6 18M6 6l12 12"/>
          </svg>
        </button>
      </div>

      <div class="mb-5">
        <div class="mb-2 text-sm font-medium text-gray-700">{{ t('settings.language') }}</div>
        <div class="grid grid-cols-2 gap-3">
          <button
            v-for="option in languageOptions"
            :key="option.value"
            type="button"
            class="min-h-[44px] rounded-xl border px-4 text-sm font-medium transition-colors disabled:cursor-wait disabled:opacity-60"
            :class="locale === option.value
              ? 'border-blue-500 bg-blue-50 text-blue-700 ring-2 ring-blue-100'
              : 'border-gray-200 bg-white text-gray-600 hover:border-gray-300 hover:bg-gray-50'"
            :aria-pressed="locale === option.value"
            :disabled="languageSaving"
            @click="selectLanguage(option.value)"
          >
            {{ option.label }}
          </button>
        </div>
      </div>

      <div class="mb-5">
        <div class="mb-2 text-sm font-medium text-gray-700">{{ t('settings.timezone') }}</div>
        <n-select
          :value="timezoneValue"
          :options="timezoneOptions"
          filterable
          :disabled="timezoneSaving"
          @update:value="selectTimezone"
        />
      </div>

      <div class="mb-2 text-sm font-medium text-gray-700">{{ t('ui.appearance') }}</div>
      <div class="grid grid-cols-3 gap-3">
        <button
          v-for="option in themeOptions"
          :key="option.value"
          type="button"
          class="flex min-h-[116px] flex-col items-center justify-center gap-3 rounded-xl border px-2 text-sm font-medium transition-colors"
          :class="themeMode === option.value
            ? 'border-blue-500 bg-blue-50 text-blue-700 ring-2 ring-blue-100'
            : 'border-gray-200 bg-white text-gray-600 hover:border-gray-300 hover:bg-gray-50'"
          :aria-pressed="themeMode === option.value"
          @click="selectThemeMode(option.value)"
        >
          <span class="flex h-10 w-10 items-center justify-center rounded-full bg-current/10">
            <svg v-if="option.icon === 'sun'" class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
              <circle cx="12" cy="12" r="4"/>
              <path d="M12 2v2M12 20v2M4.93 4.93l1.42 1.42M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.42-1.42M17.66 6.34l1.41-1.41"/>
            </svg>
            <svg v-else-if="option.icon === 'moon'" class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
              <path d="M21 12.8A9 9 0 1 1 11.2 3 7 7 0 0 0 21 12.8Z"/>
            </svg>
            <svg v-else class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
              <rect x="3" y="4" width="18" height="13" rx="2"/>
              <path d="M8 21h8M12 17v4"/>
            </svg>
          </span>
          <span>{{ t(option.langKey) }}</span>
        </button>
      </div>
    </div>
  </div>
  <div
    v-if="capabilities.isDesktop && settingsPanelOpen"
    class="fixed inset-0 z-[80] flex items-center justify-center bg-slate-900/30 px-4 backdrop-blur-[2px]"
    @click.self="closeSettingsPanel"
  >
    <div class="w-full max-w-2xl rounded-[28px] border border-gray-200 bg-white shadow-[0_24px_80px_rgba(15,23,42,0.18)]">
      <div class="flex items-center justify-between border-b border-gray-100 px-6 py-4">
        <div class="text-lg font-semibold text-gray-900">{{ t('settings.modal.title') }}</div>
        <button class="text-sm text-gray-400 hover:text-gray-700" @click="closeSettingsPanel">{{ t('ui.close') }}</button>
      </div>
      <SettingsPanel />
    </div>
  </div>
  </n-dialog-provider>
  </n-notification-provider>
  </n-message-provider>
  </n-config-provider>
</template>

<style>
.app-shell--desktop > .app-sidebar,
.app-shell--desktop > .app-main {
  padding-top: 48px;
}

@media (max-width: 1100px) {
  .app-shell--desktop > .app-sidebar {
    width: 220px;
  }
}

.custom-scrollbar::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}
.custom-scrollbar::-webkit-scrollbar-track {
  background: transparent;
}
.custom-scrollbar::-webkit-scrollbar-thumb {
  background-color: rgba(0, 0, 0, 0.1);
  border-radius: 10px;
}
.custom-scrollbar::-webkit-scrollbar-thumb:hover {
  background-color: rgba(0, 0, 0, 0.2);
}

.history-scrollbar::-webkit-scrollbar {
  width: 8px;
}
.history-scrollbar::-webkit-scrollbar-track {
  background: rgba(0, 0, 0, 0.04);
  border-radius: 999px;
}
.history-scrollbar::-webkit-scrollbar-thumb {
  background-color: rgba(0, 0, 0, 0.18);
  border-radius: 999px;
  border: 2px solid rgba(0, 0, 0, 0.04);
}
.history-scrollbar::-webkit-scrollbar-thumb:hover {
  background-color: rgba(0, 0, 0, 0.28);
}

</style>
