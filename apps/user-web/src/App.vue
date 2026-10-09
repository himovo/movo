<script setup lang="ts">
import { createDiscreteApi, darkTheme, NButton, NConfigProvider, NDialogProvider, NInput, NMessageProvider, NNotificationProvider, NSelect } from 'naive-ui'
import TokenInput from './components/TokenInput.vue'
import SettingsPanel from './components/SettingsPanel.vue'
import ShortcutPreferencesPanel from './components/settings/ShortcutPreferencesPanel.vue'
import TokenUsagePage from './components/TokenUsagePage.vue'
import ProfileModal from './components/ProfileModal.vue'
import productUiExtension from '@movo-product-extension'
import DesktopWindowChrome from './components/desktop/DesktopWindowChrome.vue'
import DesktopPrimaryNavigation, { type DesktopPrimarySection } from './components/desktop/DesktopPrimaryNavigation.vue'
import WindowsTitleBar from './components/desktop/WindowsTitleBar.vue'
import ChatSessionHeader from './components/chat/ChatSessionHeader.vue'
import DesktopServerSetup from './components/desktop/DesktopServerSetup.vue'
import type { DesktopToolLauncherKind } from './components/desktop/desktopToolTabs'
import CreateProjectDialog from './components/code/CreateProjectDialog.vue'
import { fetchOrgBilling, fetchUserProfile, getAdminSSOToken, logoutWithToken, switchTenant, type TenantCandidate, type UserProfile } from './api/auth'
import { AUTH_EXPIRED_EVENT } from './api/authExpiry'
import { activateEmbeddedBrowserSession, capabilities, getDshWorkspaceSummary, getSettings, updateSettings, startAgent, stopAgent, getAgentStatus, openResource, selectEmbeddedBrowserSession, selectDshWorkspace, renameDshWorkspace } from './platform'
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
import { joinSessionShare, type SessionShareError } from './api/sessionSharing'
import { computed, defineAsyncComponent, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import ChatWindowLoadError from './components/ChatWindowLoadError.vue'
import { registerProductMessages, setLocale as setAppLocale, t, useLocale, type Locale } from './composables/i18n'
import { themeOverridesForPlatform } from './composables/naiveThemeOverrides'
import { getBrowserTimezone, setAppTimezone } from './composables/appTimezone'
import { buildAdminSsoUrl } from './utils/adminUrl'
import { sortSessionsByRecentActivity } from './utils/sessionOrdering'
import { formatExactTokenAmount, formatQuotaUsagePercent, formatTokenAmount, quotaUsagePercent } from './utils/tokenNumberFormat'
import { useChatRuntimeStore, type PendingRuntimeDocument } from './composables/useChatRuntimeStore'
import type { SessionLiveAccessRevokedReason } from './composables/useSessionLiveStream'
import { useDshCodeRuntime } from './composables/code/useDshCodeRuntime'
import { useUserBoundProjects } from './composables/code/userBoundProjects'
import { boundProjectWorktree } from './composables/code/projectAuthorization'
import { projectHistoryVisibility } from './composables/code/projectHistoryVisibility'
import { useEnterpriseAccessPolicy } from './composables/useEnterpriseAccessPolicy'
import { useProfileRefreshOnResume } from './composables/useProfileRefreshOnResume'
import { useSkillShareInboxBadge } from './composables/useSkillShareInboxBadge'
import { usePersonalKnowledgeBadge } from './composables/usePersonalKnowledgeBadge'
import { useDesktopToolTabs } from './composables/desktop/useDesktopToolTabs'
import { clearDesktopAuthSession, restoreDesktopAuthToken } from './composables/desktop/desktopAuthSession'
import { AppsOutline, SettingsOutline } from '@vicons/ionicons5'

const ChatWindow = defineAsyncComponent({
  loader: () => import('./components/ChatWindow.vue'),
  errorComponent: ChatWindowLoadError,
  onError(_error, retry, fail, attempts) {
    if (attempts < 2) window.setTimeout(retry, 750)
    else fail()
  },
})
const SkillsPage = defineAsyncComponent(() => import('./components/MySkillsPage.vue'))
const PluginsPage = defineAsyncComponent(() => import('./components/MyPluginsPage.vue'))
const ToolsPage = defineAsyncComponent(() => import('./components/MyToolsPage.vue'))
const KnowledgePage = defineAsyncComponent(() => import('./components/MyKnowledgePage.vue'))
const SkillConfigPage = defineAsyncComponent(() => import('./components/MySkillConfigPage.vue'))
const CompositeSkillEditor = defineAsyncComponent(() => import('./components/CompositeSkillEditor.vue'))
const ScheduledTaskPage = defineAsyncComponent(() => import('./components/scheduled-tasks/ScheduledTaskPage.vue'))
const ProductLoginModal = productUiExtension.loginModal
const ProductBillingModal = productUiExtension.billingModal
const ProductCreateOrganizationModal = productUiExtension.createOrganizationModal
registerProductMessages(productUiExtension.messages)

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
const personalizationSection = ref<'general' | 'shortcuts'>('general')
type ThemeMode = 'light' | 'dark' | 'system'
const themeModeKey = 'askai.theme-mode'
const storedThemeMode = localStorage.getItem(themeModeKey)
const themeMode = ref<ThemeMode>(
  storedThemeMode === 'light' || storedThemeMode === 'dark' || storedThemeMode === 'system'
    ? storedThemeMode
    : 'system',
)
const isDarkTheme = ref(false)
document.documentElement.classList.toggle('platform-desktop', capabilities.isDesktop)
const isWindowsDesktop = capabilities.isDesktop && document.documentElement.classList.contains('platform-windows')
const desktopSidebarCollapsed = ref(false)
const platformThemeOverrides = computed(() => themeOverridesForPlatform(
  isDarkTheme.value && capabilities.isDesktop,
))
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
// T26: "Shared with me" section — separate list/state from the owner-scope
// `sessions` so the two sections poll independently and keep their own pagination.
const sharedSessions = ref<SessionSummary[]>([])
const sharedSessionsLoading = ref(false)
const sharedSessionsLoadingMore = ref(false)
const sharedSessionsHasMore = ref(false)
// T27: share-link landing — the token captured from ?session-share= at startup,
// stripped from the URL immediately (never left in history) and stashed until a
// confirmed login consumes it. A 401 on the join keeps the stash so the
// auth-expired re-login retries; a definitive share-token failure clears it.
const pendingSessionShareToken = ref<string | null>(null)
// T27: App.vue hosts the message providers, so useMessage() is unavailable in
// its own setup — the discrete API is the documented way to toast from here,
// themed to match the app's provider.
const shareToastConfigProviderProps = computed(() => ({
  theme: isDarkTheme.value ? darkTheme : null,
  themeOverrides: platformThemeOverrides.value,
}))
const { message: shareToast } = createDiscreteApi(['message'], { configProviderProps: shareToastConfigProviderProps })
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
const currentView = ref<'chat' | 'skills' | 'plugins' | 'tools' | 'knowledge' | 'skill-config' | 'composite-editor' | 'token-usage' | 'scheduled-tasks'>('chat')
const desktopPrimarySection = computed<DesktopPrimarySection>(() => {
  if (currentView.value === 'scheduled-tasks') return 'scheduled'
  if (currentView.value === 'skills' || currentView.value === 'skill-config' || currentView.value === 'composite-editor') return 'skills'
  if (currentView.value === 'plugins') return 'plugins'
  if (currentView.value === 'tools') return 'tools'
  if (currentView.value === 'knowledge') return 'knowledge'
  return 'home'
})
const desktopSecondaryNavigationVisible = computed(() =>
  capabilities.isDesktop && desktopPrimarySection.value === 'home' && !desktopSidebarCollapsed.value,
)
const desktopNavigationWidth = computed(() => capabilities.isDesktop
  ? 52 + (desktopSecondaryNavigationVisible.value ? 260 : 0)
  : 260)
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
      ? 'Central European Time - Europe/Berlin'
      : '欧洲中部时间 - Europe/Berlin',
    value: 'Europe/Berlin',
  },
  {
    label: locale.value === 'en'
      ? 'United Kingdom Time - Europe/London'
      : '英国时间 - Europe/London',
    value: 'Europe/London',
  },
  {
    label: locale.value === 'en'
      ? 'US Eastern Time - America/New_York'
      : '美国东部时间 - America/New_York',
    value: 'America/New_York',
  },
  {
    label: locale.value === 'en'
      ? 'US Central Time - America/Chicago'
      : '美国中部时间 - America/Chicago',
    value: 'America/Chicago',
  },
  {
    label: locale.value === 'en'
      ? 'US Pacific Time - America/Los_Angeles'
      : '美国太平洋时间 - America/Los_Angeles',
    value: 'America/Los_Angeles',
  },
  {
    label: locale.value === 'en'
      ? 'Australian Eastern Time - Australia/Sydney'
      : '澳大利亚东部时间 - Australia/Sydney',
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
const skillShareInboxScope = computed(() => ({
  token: authToken.value,
  mainId: String(userProfile.value?.mainId || ''),
  userId: String(userProfile.value?.userId || ''),
  enabled: canUseSkills.value,
}))
const {
  pendingCount: pendingSkillShareCount,
  actionCount: pendingSkillShareActionCount,
  feedbackCount: pendingSkillFeedbackCount,
  refresh: refreshSkillShareCount,
} = useSkillShareInboxBadge({ scope: skillShareInboxScope })
const knowledgeBadgeScope = computed(() => ({
  token: authToken.value,
  mainId: String(userProfile.value?.mainId || ''),
  userId: String(userProfile.value?.userId || ''),
  enabled: canUseTools.value,
}))
const {
  unreadCount: personalKnowledgeUnreadCount,
  shareCount: personalKnowledgeShareCount,
  refresh: refreshPersonalKnowledgeCount,
} = usePersonalKnowledgeBadge(knowledgeBadgeScope)
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
const sharedHistoryExpanded = ref(savedSidebarHistoryState.shared !== false)
const pinnedHistoryExpanded = ref(savedSidebarHistoryState.pinnedExpanded !== false)
const pinnedSessionIds = ref<string[]>([])
const pinnedStorageKey = computed(() => {
  const userId = userProfile.value?.userId
  return userId == null ? '' : `askai.pinned-sessions.${String(userProfile.value?.mainId || 'default')}.${String(userId)}`
})
function isSessionPinned(id: string): boolean { return pinnedSessionIds.value.includes(id) }
function toggleSessionPin(id: string): void {
  pinnedSessionIds.value = isSessionPinned(id)
    ? pinnedSessionIds.value.filter((item) => item !== id)
    : [...pinnedSessionIds.value, id]
}
const pinnedSessions = computed(() => pinnedSessionIds.value
  .map((id) => sessions.value.find((session) => session.id === id) || sharedSessions.value.find((session) => session.id === id))
  .filter((session): session is SessionSummary => Boolean(session)))
const collapsedProjectHistory = ref<Record<string, boolean>>(savedSidebarHistoryState.projects || {})
function projectHistoryExpanded(workspaceId: string): boolean { return !collapsedProjectHistory.value[workspaceId] }
function toggleProjectHistory(workspaceId: string): void { collapsedProjectHistory.value = { ...collapsedProjectHistory.value, [workspaceId]: projectHistoryExpanded(workspaceId) } }
const visibleProjectHistory = computed(() => projectHistoryVisibility(sessions.value, projectWorkspaces.value, workspaceTitles.value))
const historyItems = computed(() => supportsLocalCodeProjects && canUseCode.value ? visibleProjectHistory.value.ordinary : sortSessionsByRecentActivity(sessions.value))
const projectHistoryGroups = computed(() => canUseCode.value && supportsLocalCodeProjects ? visibleProjectHistory.value.projects : [])
function isUnavailableProjectHistory(sessionId: string): boolean {
  return supportsLocalCodeProjects && visibleProjectHistory.value.unavailableIds.has(sessionId)
}
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
  onSessionBusy: () => shareToast.info(t('app.sidebar.session_running')),
})
const visibleChatPanes = chatRuntime.panes
const codeRuntime = useDshCodeRuntime(chatRuntime)
const refreshWorkspaceTitles = userBoundProjects.refresh
const activeChatKey = chatRuntime.activeChatKey
const currentSessionId = chatRuntime.currentSessionId
const desktopBrowserRequest = ref(0)
const desktopCodeReviewPath = ref('')
const desktopCodeReviewChanges = ref<DshTaskChangeSet | null>(null)
const desktopCodeFilePath = ref('')
const desktopWorkspaceSummary = ref<DshWorkspaceSummary | null>(null)
const createProjectOpen = ref(false)
const createProjectBusy = ref(false)
const createProjectSelecting = ref(false)
const createProjectSelectionPhase = ref('')
const createProjectSelectionError = ref('')
const createProjectWorkspace = ref<DshWorkspace | null>(null)
const createProjectWorktree = ref(false)
const createProjectTargetKey = ref<string | null>(null)
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
  if (currentView.value === 'knowledge') return t('knowledge.sidebar')
  if (currentView.value === 'scheduled-tasks') return locale.value === 'zh' ? '定时任务' : 'Scheduled tasks'
  if (currentView.value === 'token-usage') return t('app.account.usage')
  if (currentView.value === 'skill-config' || currentView.value === 'composite-editor') {
    return selectedSkill.value?.name || t('app.sidebar.marketplace')
  }
  return t('app.sidebar.marketplace')
})
// Web chat top bar's title fallback: same source as the desktop chrome's chat title.
// T26: a shared session is not in the owner-scope `sessions` list — the shared list
// (scope=shared) carries the owner's title, and the header's own session-detail fetch
// fills the real title when neither list has the row yet.
const chatHeaderTitle = computed(() => {
  if (currentView.value !== 'chat') return ''
  const current = sessions.value.find((session) => session.id === currentSessionId.value)
    || sharedSessions.value.find((session) => session.id === currentSessionId.value)
  return current ? displaySessionTitle(current) : ''
})
function addProjectToActiveConversation(): void {
  if (canUseCode.value && currentView.value === 'chat') openProjectCreate(activeChatKey.value)
}

function createProject(): void {
  openProjectCreate(null)
}

function openProjectCreate(targetKey: string | null): void {
  if (!canUseCode.value || !capabilities.localWorkspacePicker) return
  createProjectTargetKey.value = targetKey
  createProjectWorkspace.value = null
  createProjectSelectionError.value = ''
  createProjectWorktree.value = false
  createProjectOpen.value = true
}

function closeProjectCreate(): void {
  createProjectOpen.value = false
  createProjectTargetKey.value = null
}

function selectBoundProject(key: string, workspace: DshWorkspace): void {
  if (workspace.status !== 'ok') return
  codeRuntime.setDraftProject(key, workspace, boundProjectWorktree(userBoundProjects.bindings.value, workspace.workspace_id))
}

async function chooseProjectFolder(): Promise<void> {
  if (createProjectSelecting.value) return
  const selectionToken = authToken.value
  const startedAt = performance.now()
  const trace = (stage: string) => console.info('[desktop-workspace-select-ui]', { stage, elapsedMs: Math.round(performance.now() - startedAt) })
  createProjectSelecting.value = true
  createProjectSelectionError.value = ''
  createProjectSelectionPhase.value = locale.value === 'en' ? 'Checking desktop sign-in…' : '正在检查桌面登录状态…'
  try {
    trace('identity-sync-starting')
    const identityReady = await Promise.race([
      syncDesktopAgentIdentity(authToken.value, userProfile.value?.userId),
      new Promise<false>((resolve) => setTimeout(() => resolve(false), 15000)),
    ])
    trace(identityReady ? 'identity-sync-ready' : 'identity-sync-failed')
    if (!identityReady) throw new Error(locale.value === 'en' ? 'Desktop login is not ready. Sign in again and retry.' : '桌面登录状态尚未同步，请重新登录后重试。')
    createProjectSelectionPhase.value = locale.value === 'en' ? 'Choose a folder; MOVO will then register it with DSH…' : '请选择文件夹，随后 MOVO 会将其注册到 DSH…'
    trace('workspace-select-invoking')
    const workspace = await selectDshWorkspace()
    trace(workspace ? 'workspace-select-completed' : 'workspace-select-cancelled')
    if (!workspace) return
    createProjectWorkspace.value = workspace
  } catch (error) {
    trace('workspace-select-failed')
    const message = error instanceof Error ? error.message : String(error)
    if (message.includes('[MOVO_AUTH_EXPIRED]') && authToken.value === selectionToken) {
      handleAuthExpired()
    }
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
  try {
    const renamed = workspace.title === title ? workspace : await renameDshWorkspace(workspace.workspace_id, title)
    const binding = await createDesktopProject({
      workspace_id: renamed.workspace_id,
      title: renamed.title,
      worktree: createProjectWorktree.value,
    }, authToken.value || null)
    const targetKey = createProjectTargetKey.value
    const pane = targetKey ? visibleChatPanes.value.find(item => item.key === targetKey) : chatRuntime.startLocalSession()
    if (!pane) throw new Error('the target conversation is no longer available')
    codeRuntime.setDraftProject(pane.key, renamed, createProjectWorktree.value)
    userBoundProjects.add(binding, renamed)
    closeProjectCreate()
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

const desktopAvailableTools = computed<DesktopToolLauncherKind[]>(() => {
  const tools: DesktopToolLauncherKind[] = []
  if (canUseBrowser.value && activeChatKey.value) tools.push('browser')
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
  activeKind: desktopActiveToolKind,
  tabsFor: desktopToolTabsFor,
  activeFor: desktopActiveToolFor,
  open: openDesktopTool,
  reveal: revealDesktopTool,
  openFile: openDesktopFileTab,
  openDiff: openDesktopDiffTab,
  select: selectDesktopTool,
  close: closeDesktopTool,
  hide: hideDesktopTools,
} = useDesktopToolTabs({
  getScopeKey: () => activeChatKey.value,
  getLocale: () => locale.value === 'en' ? 'en' : 'zh',
  isAvailable: kind => currentView.value === 'chat' && desktopAvailableTools.value.includes(kind),
  onActivate: tab => {
    if (tab.kind === 'browser') {
      desktopBrowserRequest.value += 1
      const sessionId = currentSessionId.value || activeChatKey.value
      if (sessionId && capabilities.embeddedBrowser) {
        void selectEmbeddedBrowserSession(sessionId)
          .then(() => activateEmbeddedBrowserSession(sessionId))
          .catch(() => { /* Browser surface reports unavailable state in its own UI. */ })
      }
    }
  },
})

function toggleDesktopCodePanel(mode: 'changes' | 'files' | 'terminal'): void {
  if (desktopActiveToolKind.value === mode) {
    hideDesktopTools()
    return
  }
  desktopCodeReviewPath.value = ''
  desktopCodeReviewChanges.value = null
  desktopCodeFilePath.value = ''
  revealDesktopTool(mode)
}

function reviewCodeChanges(changes: DshTaskChangeSet, path?: string): void {
  if (!activeCodeState.value.session) return
  desktopCodeReviewChanges.value = changes
  desktopCodeReviewPath.value = path || ''
  desktopCodeFilePath.value = ''
  if (path) openDesktopDiffTab(path, changes)
  else revealDesktopTool('changes')
}
function openCodeFile(path: string): void {
  if (!activeCodeState.value.session) return
  desktopCodeReviewChanges.value = null
  desktopCodeReviewPath.value = ''
  desktopCodeFilePath.value = path
  openDesktopFileTab(path)
}
async function refreshDesktopWorkspaceSummary(): Promise<void> {
  const sessionId = activeCodeState.value.session?.kernel_session_id
  if (!sessionId || !capabilities.codeInspector) return
  try { desktopWorkspaceSummary.value = await getDshWorkspaceSummary(sessionId) } catch { /* keep last known summary */ }
}
let workspaceSummaryRequest = 0
watch(() => activeCodeState.value.session?.kernel_session_id, async sessionId => {
  const request = ++workspaceSummaryRequest
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
  if (capabilities.embeddedBrowser && sessionId) void selectEmbeddedBrowserSession(sessionId)
}, { immediate: true })
const sessionSearchDisplayItems = computed(() =>
  trimmedSessionSearchQuery.value ? sessionSearchResults.value : sessions.value
)
const sidebarItems = computed(() => [
  { icon: 'plus', label: t('app.sidebar.new_chat') },
  ...(capabilities.isDesktop ? [] : [{ icon: 'clock', label: locale.value === 'zh' ? '定时任务' : 'Scheduled tasks' }]),
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
  if (!capabilities.isDesktop) return true
  const uid = userId !== undefined && userId !== null ? String(userId) : ''
  if (!uid || !token) return false
  try {
    const [current, status] = await Promise.all([getSettings(), getAgentStatus()])
    const settingsMatch = current.user_id === uid && current.auth_token === token
    if (settingsMatch && status.running) return true
    if (!settingsMatch) {
      await updateSettings({ ...current, user_id: uid, auth_token: token })
      if (!status.running) await startAgent()
      return true
    }
    if (!status.running) await startAgent()
    return true
  } catch (err) {
    console.warn('[desktop] failed to sync agent identity', err)
    return false
  }
}

function handleLoginSuccess(payload: { token: string; username: string; profile?: UserProfile }) {
  // Authentication is complete once a token is returned. Close the dialog
  // before running optional cleanup and persistence so those follow-up tasks
  // can never leave an authenticated user stuck on the verifying state.
  sessions.value = []
  sharedSessions.value = []
  sessionsHasMore.value = false
  sharedSessionsHasMore.value = false
  chatRuntime.reset()
  userProfile.value = null
  localStorage.removeItem(authUserProfileKey)
  authToken.value = payload.token
  currentAccount.value = payload.username
  loginOpen.value = false
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
  try {
    localStorage.setItem(authTokenKey, payload.token)
    localStorage.setItem(authAccountKey, payload.username)
  } catch (error) {
    console.warn('[auth] failed to persist login credentials', error)
  }
  billingSummary.value = null
  billingSummaryLoaded.value = false
  try {
    persistSavedUsers(payload.username)
  } catch (error) {
    console.warn('[auth] failed to persist login history', error)
  }
  // Prefer profile that came back inline with the login response. Falling
  // back to the (sometimes-broken) SSO clientAuth call only when the login
  // didn't give us a userId.
  if (payload.profile && payload.profile.userId !== undefined && payload.profile.userId !== null) {
    userProfile.value = payload.profile
    try {
      localStorage.setItem(authUserProfileKey, JSON.stringify(payload.profile))
    } catch (error) {
      console.warn('[auth] failed to persist user profile', error)
    }
    startLocalSession()
    loadSessions(true).catch(() => {})
    void loadSharedSessions(true).catch(() => {})
    // T27: the token login confirmed — consume the stashed share link (joins
    // once, opens the joined session, replaces the blank pane).
    void joinPendingSharedSession().catch(() => {})
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
  personalizationSection.value = 'general'
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
  sharedSessions.value = []
  sessionsHasMore.value = false
  sharedSessionsHasMore.value = false
  sessionsLoading.value = false
  sessionsLoadingMore.value = false
  sharedSessionsLoading.value = false
  sharedSessionsLoadingMore.value = false
  chatRuntime.reset()
  sessionSearchOpen.value = false
  sessionSearchQuery.value = ''
  sessionSearchResults.value = []
  sessionSearchHasMore.value = false
  sessionSearchLoading.value = false
  sessionSearchDidRun.value = false
  if (capabilities.isDesktop) {
    void clearDesktopAuthSession({ getSettings, updateSettings, getAgentStatus, stopAgent }).catch((error) => {
      console.warn('[desktop] failed to clear persisted authentication', error)
    })
  }
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
  createProjectOpen.value = false
  createProjectSelectionError.value = ''
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
  if (path === '/plugins') return 'plugins'
  if (path === '/tools') return 'tools'
  if (path === '/knowledge') return 'knowledge'
  if (path === '/scheduled-tasks') return 'scheduled-tasks'
  return 'chat'
}

function routePathForView(view: typeof currentView.value) {
  if (view === 'token-usage') return '/usage'
  if (view === 'tools') return '/tools'
  if (view === 'knowledge') return '/knowledge'
  if (view === 'scheduled-tasks') return '/scheduled-tasks'
  if (view === 'skills' || view === 'skill-config' || view === 'composite-editor') return '/skills'
  if (view === 'plugins') return '/plugins'
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
  if (icon === 'plus') startLocalSession({ inheritCurrentProject: true })
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
    // T26: the tenant changed — the old tenant's shared rows are stale until the
    // next poll; refresh both scopes here for parity with the owner list.
    void loadSharedSessions(true).catch(() => {})
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
  void refreshSkillShareCount()
}

function closeSkillsPage() {
  navigateTo('chat')
}

function openToolsPage() {
  navigateTo('tools')
}

function openKnowledgePage() {
  navigateTo('knowledge')
  void refreshPersonalKnowledgeCount()
}

function openDesktopPrimarySection(section: DesktopPrimarySection) {
  if (section === 'home') navigateTo('chat')
  else if (section === 'scheduled') openScheduledTasks()
  else if (section === 'skills') openSkillsPage()
  else if (section === 'plugins') navigateTo('plugins')
  else if (section === 'tools') openToolsPage()
  else openKnowledgePage()
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

function handleSkillConfigSaved(savedSkill: any) {
  selectedSkill.value = savedSkill || selectedSkill.value
  loadSkills().catch(() => {})
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
  if (authToken.value !== token) return
  if (result.status === 401) {
    if (authToken.value === token) handleAuthExpired()
    return
  }
  if (result.ok && result.data) {
    prepareProjectBoundary(result.data)
    userProfile.value = result.data
    localStorage.setItem(authUserProfileKey, JSON.stringify(result.data))
    await loadSessions(true).catch(() => {})
    void loadSharedSessions(true).catch(() => {})
    loginOpen.value = false
    // T27: the login/profile resolution confirmed (token login via the SSO
    // client path, page refresh with a stored token, already-logged-in
    // startup) — consume the stashed share link.
    void joinPendingSharedSession().catch(() => {})
    void syncDesktopAgentIdentity(token, result.data.userId)
    return
  }
  if (preserveSessionOnFailure) {
    sessionsLoading.value = false
    console.warn('[auth] fetchUserProfile failed; keeping cached session and retrying later')
    await loadSessions(true).catch(() => {})
    void loadSharedSessions(true).catch(() => {})
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
  if (result.status === 401) {
    if (authToken.value === token) handleAuthExpired()
    return
  }
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
      if (activeChatKey.value) navigateTo('chat')
      else startLocalSession()
      revealDesktopTool('browser')
      const browserSessionId = currentSessionId.value || activeChatKey.value
      if (browserSessionId) {
        await selectEmbeddedBrowserSession(browserSessionId)
        await activateEmbeddedBrowserSession(browserSessionId)
      }
      await nextTick()
      await new Promise<void>((resolve) => window.requestAnimationFrame(() => resolve()))
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
  const mainId = getMainId()
  const token = authToken.value
  if (reset) {
    sessionsLoading.value = true
    sessionsHasMore.value = false
  } else {
    sessionsLoadingMore.value = true
  }
  try {
    const page = await listSessionsPaged(userId, mainId, {
      limit: sessionPageSize,
      offset: reset ? 0 : sessions.value.length,
    }, token || null)
    if (token !== authToken.value || userId !== getUserId() || mainId !== getMainId()) return
    sessions.value = reset ? page.items : mergeSessionPages(sessions.value, page.items)
    sessionsHasMore.value = page.has_more
    if (canUseCode.value) void refreshWorkspaceTitles()
  } catch (error) {
    throw error
  } finally {
    if (token === authToken.value && userId === getUserId() && mainId === getMainId()) {
      if (reset) sessionsLoading.value = false
      else sessionsLoadingMore.value = false
    }
  }
}

async function refreshSessionSummaries() {
  const userId = getUserId()
  if (!userId || document.visibilityState === 'hidden') return
  const mainId = getMainId()
  const token = authToken.value
  try {
    const page = await listSessionsPaged(userId, mainId, {
      limit: Math.max(sessionPageSize, sessions.value.length), offset: 0,
    }, token || null)
    if (token !== authToken.value || userId !== getUserId() || mainId !== getMainId()) return
    sessions.value = mergeSessionPages(page.items, sessions.value).slice(0, Math.max(sessionPageSize, sessions.value.length))
    sessionsHasMore.value = page.has_more
    chatRuntime.syncActiveRuns(page.items, userId)
  } catch {
    // Best-effort visibility refresh; explicit navigation still retries.
  }
}

// T26: "Shared with me" fetch — scope=shared via the client's scope param.
// RESET-STYLE replace (NOT mergeSessionPages, which would retain a row the
// viewer left); the window covers everything currently loaded so the section's
// own pagination survives the poll. The server pins the activity order (todo 8)
// — the response replaces the list as-is, no client re-sort by join order.
async function loadSharedSessions(reset = true) {
  const userId = getUserId()
  if (!userId) return
  const mainId = getMainId()
  const token = authToken.value
  if (reset) {
    sharedSessionsLoading.value = true
    sharedSessionsHasMore.value = false
  } else {
    sharedSessionsLoadingMore.value = true
  }
  try {
    const page = await listSessionsPaged(userId, mainId, {
      limit: sessionPageSize,
      offset: reset ? 0 : sharedSessions.value.length,
      scope: 'shared',
    }, token || null)
    if (token !== authToken.value || userId !== getUserId() || mainId !== getMainId()) return
    sharedSessions.value = reset ? page.items : [...sharedSessions.value, ...page.items]
    sharedSessionsHasMore.value = page.has_more
  } catch (error) {
    if (reset) throw error
  } finally {
    if (token === authToken.value && userId === getUserId() && mainId === getMainId()) {
      if (reset) sharedSessionsLoading.value = false
      else sharedSessionsLoadingMore.value = false
    }
  }
}

async function refreshSharedSummaries() {
  const userId = getUserId()
  if (!userId || document.visibilityState === 'hidden') return
  const mainId = getMainId()
  const token = authToken.value
  try {
    const page = await listSessionsPaged(userId, mainId, {
      limit: Math.max(sessionPageSize, sharedSessions.value.length),
      offset: 0,
      scope: 'shared',
    }, token || null)
    if (token !== authToken.value || userId !== getUserId() || mainId !== getMainId()) return
    sharedSessions.value = page.items
    sharedSessionsHasMore.value = page.has_more
    chatRuntime.syncActiveRuns(page.items, userId)
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

function startLocalSession(options: { shouldNavigate?: boolean; inheritCurrentProject?: boolean } = {}) {
  const sourceKey = options.inheritCurrentProject ? activeChatKey.value : ''
  const pane = chatRuntime.startLocalSession()
  if (canUseCode.value && sourceKey) codeRuntime.inheritDraftProject(sourceKey, pane.key)
  if (options.shouldNavigate !== false) {
    navigateTo('chat')
  }
  closeSessionSearch()
}

async function selectSession(sessionId: string) {
  const userId = getUserId()
  if (!userId) return
  navigateTo('chat')
  if (currentSessionId.value === sessionId) return
  // T30: a shared row's dot clears the moment the participant opens the
  // session. The same select fires the participant GET whose server-side
  // read-cursor advance (todo 19) makes the next shared-list poll return
  // shared_unread false, so this local map only makes the clear instant.
  // Only shared rows carry shared_unread (T25) — owned rows' unread
  // affordances read sessionIsUnread/scheduled_unread and never match here,
  // and the local in-memory unread set must never render a second dot on
  // shared rows (they read shared_unread only, in the separate ref).
  if (sharedSessions.value.some((session) => session.id === sessionId && session.shared_unread)) {
    sharedSessions.value = sharedSessions.value.map((session) => (
      session.id === sessionId ? { ...session, shared_unread: false } : session
    ))
  }
  const pane = await chatRuntime.selectSession(sessionId, userId, getMainId(), authToken.value || null)
  if (canUseCode.value && pane.codeProject?.workspace_id && !codeRuntime.stateFor(pane.key).session) {
    codeRuntime.beginRestore(pane.key)
    try {
      const identityReady = await syncDesktopAgentIdentity(authToken.value, userId)
      if (identityReady) await codeRuntime.attach(pane.key, sessionId)
    } finally {
      codeRuntime.finishRestore(pane.key)
    }
  }
  closeSessionSearch()
}

async function refreshOpenSession(sessionId: string) {
  const userId = getUserId()
  if (!userId) return
  try {
    await chatRuntime.refreshSession(sessionId, userId, getMainId(), authToken.value || null)
    await Promise.all([refreshSessionSummaries(), refreshSharedSummaries()])
  } catch {
    shareToast.error(t('session.run.refresh_failed'))
  }
}

// T24: a participant leaving via the share dialog clears the leaved session per the
// delete convention (removeSession starts a blank pane when it was current) and
// refreshes the sessions list. T26: the shared-list (scope=shared) refresh uses the
// same reset-style fetch so the leaved row disappears from "Shared with me" too.
function handleSessionLeft(sessionId: string) {
  chatRuntime.removeSession(sessionId)
  void loadSessions(true).catch(() => {})
  void loadSharedSessions(true).catch(() => {})
}

// T10: read-only consumption of T7's access-loss latch. Both loss paths — T8's
// typed POST ChatStreamAccessRevokedEvent and T7's session-SSE onAccessLost
// binding — already converge on the single markAccessLost writer, which aborts
// the live stream, the local POST handle, and the recovery controller exactly
// once. This never tears anything down itself; it only reacts to the settled
// flag: clear the pane per the T24 delete convention (removeSession starts a
// blank pane when it was current), drop the row from "Shared with me", and show
// one non-sensitive notice. Each pane key is handled at most once, and handled
// keys are pruned with their pane so an access-restored session can be handled
// again — a repeated read can never re-clear or toast-loop.
const accessLostHandledPanes = new Set<string>()

watch(
  () => visibleChatPanes.value.filter((pane) => pane.accessLost).map((pane) => pane.key),
  (lostPaneKeys) => {
    const livePaneKeys = new Set(visibleChatPanes.value.map((pane) => pane.key))
    for (const handledKey of accessLostHandledPanes) {
      if (!livePaneKeys.has(handledKey)) accessLostHandledPanes.delete(handledKey)
    }
    for (const paneKey of lostPaneKeys) {
      if (accessLostHandledPanes.has(paneKey)) continue
      accessLostHandledPanes.add(paneKey)
      handlePaneAccessLost(paneKey)
    }
  },
)

// Non-sensitive wording only: never names the actor or the transport that
// reported the loss. participant_left reuses the existing share notice the
// leave dialog already owns; a removal (or a latch with no typed reason) gets
// the generic access-lost copy.
function accessLostNoticeMessage(reason: SessionLiveAccessRevokedReason | null): string {
  const generic = locale.value === 'zh' ? '你已无法访问该会话。' : 'You no longer have access to this session.'
  switch (reason) {
    case 'participant_left':
      return t('session.share.left')
    case 'participant_removed':
    case null:
      return generic
    default: {
      const _exhaustive: never = reason
      void _exhaustive
      return generic
    }
  }
}

function handlePaneAccessLost(paneKey: string) {
  const pane = visibleChatPanes.value.find((item) => item.key === paneKey)
  if (!pane?.sessionId) return
  const { sessionId, accessLostReason } = pane
  chatRuntime.removeSession(sessionId)
  sharedSessions.value = sharedSessions.value.filter((session) => session.id !== sessionId)
  shareToast.warning(accessLostNoticeMessage(accessLostReason))
}

// T27: the share-link landing flow. captureSessionShareToken runs at the top of
// onMounted — BEFORE any navigateTo (navigateTo pushes only the path, and the
// parameter must never survive in history) — strips ?session-share= from the URL
// and stashes it. joinPendingSharedSession consumes the stash after a confirmed
// login (token login, SSO/refresh login, auth-expired re-login) or on an
// already-logged-in startup: joins once, selects the joined session (selectSession
// prunes the blank pane the login flow started — the reverse of T24's removeSession
// pattern), and refreshes the shared list so the section appears under
// "Shared with me" (T26's post-join hook).
function captureSessionShareToken() {
  if (typeof window === 'undefined') return
  const url = new URL(window.location.href)
  const token = url.searchParams.get('session-share')
  if (!token) return
  pendingSessionShareToken.value = token
  url.searchParams.delete('session-share')
  window.history.replaceState({}, '', `${url.pathname}${url.search}${url.hash}`)
}

function shareSessionErrorToastMessage(error: SessionShareError): string {
  switch (error.code) {
    case 'session_not_found':
    case 'session_share_not_found':
      return t('session.share.error_join_not_found')
    case 'session_share_owner_required':
    case 'session_share_participant_required':
    case 'session_share_no_binding':
    case 'session_share_not_server':
      return t('session.share.error_generic')
    case 'session_share_inactive':
      return t('session.share.error_inactive')
    case 'session_share_token_required':
      return t('session.share.error_token_required')
    case 'http_error':
      return t('session.share.error_generic')
    default: {
      const _exhaustive: never = error.code
      void _exhaustive
      return t('session.share.error_generic')
    }
  }
}

async function joinPendingSharedSession() {
  const token = pendingSessionShareToken.value
  if (!token) return
  const result = await joinSessionShare(token)
  if (result.ok === false) {
    if (result.error.status === 401) {
      // The auth-expired interceptor has dispatched its event and opened the
      // login modal; keep the stash so the re-login retries the join.
      return
    }
    pendingSessionShareToken.value = null
    shareToast.error(shareSessionErrorToastMessage(result.error))
    return
  }
  pendingSessionShareToken.value = null
  const userId = getUserId()
  if (!userId) return
  void loadSharedSessions(true).catch(() => {})
  await selectSession(result.data.session_id).catch(() => {})
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
    onRejected?: () => void
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
    try {
      await codeRuntime.send(targetKey, payload.text, payload.modelId)
    } catch {
      // The Runtime owns the visible error; the composer still owns the draft.
      // Restore it so a rejected desktop send never looks like a lost message.
      payload.onRejected?.()
    }
    return
  }
  chatRuntime.sendMessage(key, {
    ...payload,
    authToken: authToken.value || null,
    userId: getUserId(),
    mainId: getMainId(),
    viewerAuthor: userProfile.value
      ? {
          user_id: String(userProfile.value.userId ?? getUserId() ?? ''),
          display_name: userProfile.value.name || userProfile.value.username || null,
          avatar_url: userProfile.value.avatar || null,
        }
      : null,
    locale: locale.value === 'en' ? 'en' : 'zh',
    timezone: timezoneValue.value,
  })
}

function handlePaneStop(key: string) {
  const codeState = codeRuntime.stateFor(key)
  if (codeState.session) void codeRuntime.stop(key).catch(() => undefined)
  else chatRuntime.stopGeneration(key)
}

watch(sessionSearchQuery, () => {
  scheduleSessionSearch()
})

watch(locale, (value) => {
  document.documentElement.lang = value === 'en' ? 'en' : 'zh-CN'
}, { immediate: true })

watch([normalHistoryExpanded, sharedHistoryExpanded, pinnedHistoryExpanded, pinnedSessionIds, collapsedProjectHistory], ([normal, shared, pinnedExpanded, pinnedIds, projects]) => {
  localStorage.setItem(sidebarHistoryStateKey, JSON.stringify({ normal, shared, pinnedExpanded, projects }))
  if (pinnedStorageKey.value) localStorage.setItem(pinnedStorageKey.value, JSON.stringify(pinnedIds))
}, { deep: true })

watch(pinnedStorageKey, (key) => {
  try {
    const saved = key ? JSON.parse(localStorage.getItem(key) || '[]') : []
    pinnedSessionIds.value = Array.isArray(saved) ? saved.filter((id: unknown): id is string => typeof id === 'string') : []
  } catch { pinnedSessionIds.value = [] }
}, { immediate: true })

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
  // T27: capture ?session-share= BEFORE any navigateTo (navigateTo pushes only
  // the path, dropping query params) — the capture strips it from history and
  // stashes it for the post-login join.
  captureSessionShareToken()
  window.addEventListener(AUTH_EXPIRED_EVENT, handleAuthExpired)
  applyThemeMode()
  systemThemeMedia = window.matchMedia('(prefers-color-scheme: dark)')
  systemThemeMedia.addEventListener('change', handleSystemThemeChange)
  currentView.value = resolveViewFromPath(window.location.pathname)
  let serverConfigured = !capabilities.isDesktop
  let storedSettings = null
  try {
    storedSettings = await getSettings()
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
  authToken.value = capabilities.isDesktop && storedSettings
    ? restoreDesktopAuthToken(storedSettings, localStorage, authTokenKey)
    : localStorage.getItem(authTokenKey) || ''
  loadSavedUsers()
  loadUserProfile()
  if (authToken.value && !userProfile.value) {
    startLocalSession({ shouldNavigate: currentView.value === 'chat' })
    sessionsLoading.value = true
    refreshUserProfile(authToken.value).catch(() => {
      sessionsLoading.value = false
    })
  } else if (authToken.value && userProfile.value) {
    startLocalSession({ shouldNavigate: currentView.value === 'chat' })
    refreshUserProfile(authToken.value, false, true).catch(() => {
      loadSessions(true).catch(() => {})
    })
  } else if (!authToken.value) {
    loginOpen.value = true
    startLocalSession({ shouldNavigate: currentView.value === 'chat' })
  }
  // Self-heal the desktop agent on boot: if we have a stored session,
  // make sure the Electron settings + sidecar reflect it (no-op on web).
  if (authToken.value && userProfile.value?.userId !== undefined) {
    void syncDesktopAgentIdentity(authToken.value, userProfile.value.userId)
  }
  document.addEventListener('click', handleDocumentClick)
  window.addEventListener('popstate', handlePopState)
  sessionRefreshTimer = setInterval(() => {
    void refreshSessionSummaries()
    // T26: the two sections poll independently — one timer tick drives both
    // scopes; each keeps its own pagination state and fetch cycle.
    void refreshSharedSummaries()
  }, 5000)
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
  <n-config-provider :theme="isDarkTheme ? darkTheme : null" :theme-overrides="platformThemeOverrides">
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
    :class="{ 'app-shell--desktop': capabilities.isDesktop, 'app-shell--windows-desktop': isWindowsDesktop, 'app-shell--windows-sidebar-collapsed': isWindowsDesktop && desktopSidebarCollapsed }"
  >
    <CreateProjectDialog
      v-if="canUseCode"
      :show="createProjectOpen"
      :workspace="createProjectWorkspace"
      :worktree="createProjectWorktree"
      :busy="createProjectBusy"
      :selecting="createProjectSelecting"
      :selection-phase="createProjectSelectionPhase"
      :selection-error="createProjectSelectionError"
      :locale="locale === 'en' ? 'en' : 'zh'"
      @update:worktree="(value) => createProjectWorktree = value"
      @choose-folder="chooseProjectFolder"
      @create="commitProjectCreate"
      @close="closeProjectCreate"
    />
    <WindowsTitleBar
      v-if="isWindowsDesktop"
      :collapsed="desktopSidebarCollapsed"
      :dark="isDarkTheme"
      :locale="locale === 'en' ? 'en' : 'zh'"
      @toggle-sidebar="desktopSidebarCollapsed = !desktopSidebarCollapsed"
      @new-chat="handleSidebarAction('plus')"
      @add-project="createProject"
    />
    <DesktopWindowChrome
      v-if="capabilities.isDesktop"
      :navigation-width="desktopNavigationWidth"
      :windows-title-bar="isWindowsDesktop"
      :sidebar-collapsed="desktopSidebarCollapsed"
      :secondary-navigation-available="desktopPrimarySection === 'home'"
      :title="desktopWindowTitle"
      :show-back="currentView === 'skills'"
      :back-label="t('skills.back_to_chat')"
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
      :active-tool="desktopActiveToolKind"
      :git-available="desktopWorkspaceSummary?.git_available === true"
      :change-count="desktopWorkspaceSummary?.changes.length || 0"
      :files-available="capabilities.workspaceFiles"
      :terminal-available="capabilities.projectTerminal"
      :code-available="canUseCode"
      :browser-available="canUseBrowser"
      :workspaces="projectWorkspaces"
      :workspaces-loading="projectWorkspacesLoading"
      @choose-workspace="addProjectToActiveConversation"
      @select-workspace="(workspace) => selectBoundProject(activeChatKey, workspace)"
      @clear-workspace="codeRuntime.clear(activeChatKey)"
      @worktree="(enabled) => codeRuntime.setWorktree(activeChatKey, enabled)"
      @source-ref="(fullRef) => codeRuntime.setSourceRef(activeChatKey, fullRef)"
      @branch-updated="(branch) => codeRuntime.setWorkspaceBranch(activeChatKey, branch)"
      @open-browser="requestDesktopBrowser"
      @toggle-code-panel="toggleDesktopCodePanel"
      @back="closeSkillsPage"
      @toggle-sidebar="desktopSidebarCollapsed = !desktopSidebarCollapsed"
    />
    <DesktopPrimaryNavigation
      v-if="capabilities.isDesktop"
      :active="desktopPrimarySection"
      :locale="locale === 'en' ? 'en' : 'zh'"
      :skills-available="canUseSkills"
      :tools-available="canUseTools"
      :knowledge-available="canUseKnowledge"
      :skill-badge="pendingSkillShareCount"
      :knowledge-badge="personalKnowledgeUnreadCount"
      :logged-in="isLoggedIn"
      :avatar-url="displayAvatar()"
      :avatar-text="displayAvatarText()"
      :account-label="isLoggedIn ? displayName() : t('app.sidebar.login_register')"
      @navigate="openDesktopPrimarySection"
      @account="toggleUserMenu"
      @avatar-error="handleAvatarError"
    />
    <!-- SIDEBAR -->
    <aside v-show="!capabilities.isDesktop || desktopSecondaryNavigationVisible" class="app-sidebar w-[260px] bg-[#f8fafc] flex flex-col border-r border-gray-200 shadow-[1px_0_0_rgba(0,0,0,0.02)]">
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

      <section class="px-3 pt-2">
        <button type="button" class="flex w-full items-center gap-1 px-2 pb-1 text-left text-[10px] font-bold uppercase tracking-[0.1em] text-gray-400" :aria-expanded="pinnedHistoryExpanded" @click="pinnedHistoryExpanded = !pinnedHistoryExpanded">
          <span>{{ locale === 'en' ? 'Pinned' : '置顶' }}</span>
          <svg class="h-3.5 w-3.5 transition-transform duration-150" :class="pinnedHistoryExpanded ? 'rotate-90' : ''" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="m5 3 5 5-5 5"/></svg>
        </button>
        <div v-if="pinnedHistoryExpanded" class="max-h-40 overflow-y-auto">
          <div v-for="session in pinnedSessions" :key="session.id" class="group flex items-center gap-1 rounded-lg px-2 py-1 text-sm text-gray-600 hover:bg-gray-200/50">
            <button type="button" class="min-w-0 flex-1 truncate text-left" :title="displaySessionTitle(session)" @click="selectSession(session.id)">{{ compactSessionTitle(session) }}</button>
            <button type="button" class="shrink-0 text-blue-500 opacity-0 group-hover:opacity-100 focus:opacity-100" :aria-label="locale === 'en' ? 'Unpin' : '取消置顶'" :title="locale === 'en' ? 'Unpin' : '取消置顶'" @click="toggleSessionPin(session.id)"><svg viewBox="0 0 24 24" class="h-3.5 w-3.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 3h6l-1 6 3 3v2H7v-2l3-3-1-6Z"/><path d="M12 14v7"/></svg></button>
          </div>
        </div>
      </section>
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
          v-if="normalHistoryExpanded && sessionsLoading"
          class="px-3 py-4 text-xs text-gray-400 animate-pulse italic text-center"
        >
          {{ t('app.sidebar.loading_history') }}
        </div>
        <div
          v-for="session in normalHistoryExpanded ? historyItems.filter((item) => !isSessionPinned(item.id)) : []"
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
            <span v-if="isUnavailableProjectHistory(session.id)" class="shrink-0 rounded bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-500" :title="t('app.sidebar.project_folder_unavailable')">{{ t('app.sidebar.project_history_only') }}</span>
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
            <button v-if="editingSessionId !== session.id" type="button" class="shrink-0 text-gray-400 opacity-0 group-hover:opacity-100 focus:opacity-100 hover:text-blue-600" :aria-label="locale === 'en' ? 'Pin' : '置顶'" :title="locale === 'en' ? 'Pin' : '置顶'" @click.stop="toggleSessionPin(session.id)"><svg viewBox="0 0 24 24" class="h-3.5 w-3.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 3h6l-1 6 3 3v2H7v-2l3-3-1-6Z"/><path d="M12 14v7"/></svg></button>
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
        <button
          v-if="normalHistoryExpanded && !trimmedSessionSearchQuery && !sessionsLoading && sessionsHasMore && historyItems.length >= sessionPageSize"
          class="w-full text-left px-2.5 py-1 text-[11px] text-gray-400 hover:text-gray-600 disabled:opacity-60 disabled:cursor-not-allowed"
          :disabled="sessionsLoadingMore"
          @click="loadSessions(false)"
        >
          {{ sessionsLoadingMore ? t('ui.loading') : t('app.sidebar.load_more') }}
        </button>
        <!-- Shared conversations follow ordinary conversations. -->
        <template v-if="sharedSessions.length">
          <button type="button" class="group mt-2 flex w-full items-center gap-1 px-2 pb-1 text-left text-[10px] font-bold uppercase tracking-[0.1em] text-gray-400" :aria-expanded="sharedHistoryExpanded" @click="sharedHistoryExpanded = !sharedHistoryExpanded">
            <span>{{ t('session.sharedWithMe.title') }}</span>
            <svg class="h-3.5 w-3.5 transition-transform duration-150" :class="sharedHistoryExpanded ? 'rotate-90' : ''" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="m5 3 5 5-5 5"/></svg>
          </button>
          <div
            v-for="session in sharedHistoryExpanded ? sharedSessions.filter((item) => !isSessionPinned(item.id)) : []"
            :key="session.id"
            class="group w-full text-left px-2.5 py-1.5 rounded-lg transition-all border border-transparent"
            :class="session.id === currentSessionId && currentView === 'chat'
              ? 'bg-white text-blue-700 shadow-sm border-gray-200 font-semibold'
              : 'text-gray-600 hover:bg-gray-200/50 hover:text-gray-900'"
            @click="selectSession(session.id)"
            @keydown.enter.prevent="selectSession(session.id)"
            @keydown.space.prevent="selectSession(session.id)"
            role="button"
            tabindex="0"
          >
            <div class="flex min-w-0 items-center gap-2">
              <div class="min-w-0 flex-1 text-[13px] truncate" :title="displaySessionTitle(session)">
                {{ compactSessionTitle(session) }}
              </div>
              <span
                class="shrink-0 rounded-full bg-blue-50 px-2 py-0.5 text-[10px] font-medium text-blue-600"
                :aria-label="t('session.sharedWithMe.badge')"
                :title="t('session.sharedWithMe.badge')"
              >
                {{ t('session.sharedWithMe.badge') }}
              </span>
              <button type="button" class="shrink-0 text-gray-400 opacity-0 group-hover:opacity-100 focus:opacity-100 hover:text-blue-600" :aria-label="locale === 'en' ? 'Pin' : '置顶'" :title="locale === 'en' ? 'Pin' : '置顶'" @click.stop="toggleSessionPin(session.id)"><svg viewBox="0 0 24 24" class="h-3.5 w-3.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 3h6l-1 6 3 3v2H7v-2l3-3-1-6Z"/><path d="M12 14v7"/></svg></button>
              <span
                v-if="session.shared_unread"
                class="h-2 w-2 shrink-0 rounded-full bg-blue-500"
                :aria-label="t('session.sharedWithMe.unread')"
                :title="t('session.sharedWithMe.unread')"
              ></span>
            </div>
          </div>
          <button
            v-if="sharedHistoryExpanded && !sharedSessionsLoading && sharedSessionsHasMore && sharedSessions.length >= sessionPageSize"
            class="w-full text-left px-2.5 py-1 text-[11px] text-gray-400 hover:text-gray-600 disabled:opacity-60 disabled:cursor-not-allowed"
            :disabled="sharedSessionsLoadingMore"
            @click="loadSharedSessions(false)"
          >
            {{ sharedSessionsLoadingMore ? t('ui.loading') : t('app.sidebar.load_more') }}
          </button>
        </template>
        <section v-if="canUseCode && supportsLocalCodeProjects" class="space-y-3 pt-7" aria-label="项目对话">
          <div class="group flex items-center justify-between px-2 text-[10px] font-bold uppercase tracking-[0.1em] text-gray-400">
            <span>{{ locale === 'en' ? 'Projects' : '项目' }}</span>
            <button v-if="canUseCode && capabilities.localWorkspacePicker" type="button" class="flex h-4 w-4 items-center justify-center rounded text-blue-600 opacity-0 transition-opacity hover:bg-blue-50 group-hover:opacity-100" :aria-label="locale === 'en' ? 'Create project' : '创建项目'" :title="locale === 'en' ? 'Create project' : '创建项目'" @click="createProject"><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M8 3v10M3 8h10"/></svg></button>
          </div>
          <section v-for="group in projectHistoryGroups" :key="group.workspaceId" class="space-y-0.5">
            <button type="button" class="group flex w-full min-w-0 items-center gap-2 rounded-xl px-3 py-2 text-left text-sm font-semibold text-slate-500 hover:bg-gray-200/50 hover:text-slate-700" :aria-expanded="projectHistoryExpanded(group.workspaceId)" :title="group.title" @click="toggleProjectHistory(group.workspaceId)">
              <svg v-if="projectHistoryExpanded(group.workspaceId)" class="h-4 w-4 shrink-0 text-slate-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M3 7.5h6l2 2h10v9.5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7.5Z"/></svg>
              <svg v-else class="h-4 w-4 shrink-0 text-slate-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M3 7.5h6l2 2h10v9.5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7.5Z"/><path d="M3 7.5V6a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v1.5"/></svg>
              <span class="truncate">{{ group.title }}</span>
            </button>
            <div
              v-for="session in projectHistoryExpanded(group.workspaceId) ? group.items.filter((item) => !isSessionPinned(item.id)) : []"
              :key="session.id"
              class="group flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-[13px] transition-all"
              :class="session.id === currentSessionId && currentView === 'chat' ? 'bg-white font-semibold text-blue-700 shadow-sm ring-1 ring-gray-200' : 'text-gray-600 hover:bg-gray-200/50 hover:text-gray-900'"
              :title="displaySessionTitle(session)"
            >
              <button type="button" class="min-w-0 flex-1 truncate text-left" @click="selectSession(session.id)">{{ compactSessionTitle(session) }}</button>
              <button type="button" class="shrink-0 text-gray-400 opacity-0 group-hover:opacity-100 focus:opacity-100 hover:text-blue-600" :aria-label="locale === 'en' ? 'Pin' : '置顶'" :title="locale === 'en' ? 'Pin' : '置顶'" @click.stop="toggleSessionPin(session.id)"><svg viewBox="0 0 24 24" class="h-3.5 w-3.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 3h6l-1 6 3 3v2H7v-2l3-3-1-6Z"/><path d="M12 14v7"/></svg></button>
              <span v-if="sessionIsRunning(session.id)" class="h-1.5 w-1.5 shrink-0 rounded-full bg-blue-500 animate-pulse"></span>
              <span v-else-if="sessionIsUnread(session.id)" class="h-2 w-2 shrink-0 rounded-full bg-blue-500"></span>
            </div>
          </section>
        </section>
      </div>

      <div v-if="!capabilities.isDesktop && (canUseSkills || canUseTools)" class="mt-2 px-5 pb-1 text-[10px] font-bold text-gray-400 uppercase tracking-[0.1em]">{{ t('app.sidebar.skills') }}</div>
      <div v-if="!capabilities.isDesktop && (canUseSkills || canUseTools)" class="mb-2 space-y-0.5 px-3">
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
          <span
            v-if="pendingSkillShareCount > 0"
            class="ml-auto inline-flex min-w-[18px] items-center justify-center rounded-full bg-red-500 px-1.5 py-0.5 text-[10px] font-bold leading-none text-white shadow-sm"
            :title="t('skills.share.pending_nav', { count: pendingSkillShareCount })"
            :aria-label="t('skills.share.pending_nav', { count: pendingSkillShareCount })"
          >{{ pendingSkillShareCount > 99 ? '99+' : pendingSkillShareCount }}</span>
        </button>
        <button
          class="flex w-full items-center gap-3 rounded-xl border border-transparent px-3 py-2 text-left text-sm transition-all active:scale-95"
          :class="currentView === 'plugins' ? 'bg-white text-blue-700 shadow-sm border-gray-200 font-semibold' : 'text-gray-700 hover:bg-gray-200/50'"
          @click="navigateTo('plugins')"
        >
          <span class="text-gray-500"><svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M8 3h8v4h4v5h-4v3h4v6H4v-6h4v-3H4V7h4V3Z"/><path d="M8 7h8M8 15h8"/></svg></span>
          <span>{{ t('plugins.sidebar') }}</span>
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
        <button
          v-if="canUseTools"
          class="flex w-full items-center gap-3 rounded-xl border border-transparent px-3 py-2 text-left text-sm transition-all active:scale-95"
          :class="currentView === 'knowledge' ? 'bg-white text-blue-700 shadow-sm border-gray-200 font-semibold' : 'text-gray-700 hover:bg-gray-200/50'"
          @click="openKnowledgePage"
        >
          <span class="text-gray-500">
            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2Z"/></svg>
          </span>
          <span>{{ t('knowledge.sidebar') }}</span>
          <span v-if="personalKnowledgeUnreadCount > 0" class="ml-auto inline-flex min-w-[18px] items-center justify-center rounded-full bg-red-500 px-1.5 py-0.5 text-[10px] font-bold leading-none text-white">{{ personalKnowledgeUnreadCount > 99 ? '99+' : personalKnowledgeUnreadCount }}</span>
        </button>
      </div>

      <!-- User Profile (Bottom) -->
      <div :class="capabilities.isDesktop ? 'desktop-account-menu-host' : 'p-4 border-t border-gray-200 bg-white/50'" data-user-menu>
        <div
          v-if="!capabilities.isDesktop && isLoggedIn"
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
        <div v-else-if="!capabilities.isDesktop" class="flex items-center gap-3 p-2 rounded-xl hover:bg-gray-200/70 cursor-pointer transition-colors" @click="openLogin">
          <div class="w-9 h-9 rounded-xl bg-gray-200 flex items-center justify-center text-gray-400 font-bold border border-gray-300 border-dashed">
            ?
          </div>
          <div class="text-sm font-semibold text-gray-700">{{ t('app.sidebar.login_register') }}</div>
        </div>
        
        <!-- User Menu Popup -->
        <Teleport to="body">
          <div
            v-if="userMenuOpen && isLoggedIn"
            class="fixed bottom-20 z-[80] w-[360px] max-w-[calc(100vw-2rem)] rounded-2xl border border-gray-200 bg-white p-3 text-sm text-gray-700 shadow-[0_18px_56px_rgba(15,23,42,0.14)] animate-in fade-in slide-in-from-bottom-2 duration-200"
            :class="capabilities.isDesktop ? 'left-[72px]' : 'left-4'"
            data-user-menu
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
        </Teleport>
      </div>
    </aside>

    <!-- MAIN CONTENT -->
    <main class="app-main flex-1 flex flex-col min-w-0 min-h-0 bg-white">

      <!-- Web chat top bar: web-only (DesktopWindowChrome owns the title on desktop);
           renders in the chat view when a session is open, for owner and participants. -->
      <ChatSessionHeader
        v-if="!capabilities.isDesktop && currentView === 'chat' && currentSessionId"
        :session-id="currentSessionId"
        :title="chatHeaderTitle"
        :user-id="getUserId() || ''"
        :main-id="getMainId()"
        :auth-token="authToken"
        :refresh-token="chatRuntime.membersRevisionFor(currentSessionId)"
        @left="handleSessionLeft"
      />

      <!-- Main Area -->
      <div class="flex-1 flex min-w-0 min-h-0 overflow-hidden">
        <div v-if="currentView === 'skills'" class="flex-1 min-w-0 min-h-0 overflow-hidden">
          <SkillsPage
            :userId="getUserId()"
            :mainId="getMainId()"
            :pendingShareCount="pendingSkillShareActionCount"
            :pendingFeedbackCount="pendingSkillFeedbackCount"
            @configure="openSkillConfig"
            @login="openLogin"
            @share-count-change="refreshSkillShareCount"
          />
        </div>
        <div v-else-if="currentView === 'plugins'" class="flex-1 min-w-0 min-h-0 overflow-hidden"><PluginsPage /></div>
        <div v-else-if="currentView === 'tools'" class="flex-1 min-w-0 min-h-0 overflow-hidden">
          <ToolsPage
            :userId="getUserId()"
            :mainId="getMainId()"
          />
        </div>
        <div v-else-if="currentView === 'knowledge'" class="flex-1 min-w-0 min-h-0 overflow-hidden">
          <KnowledgePage
            :shared-unread-count="personalKnowledgeShareCount"
            :unread-count="personalKnowledgeUnreadCount"
            @viewed="refreshPersonalKnowledgeCount"
          />
        </div>
        <div v-else-if="currentView === 'skill-config'" class="flex-1 min-w-0 min-h-0 overflow-hidden">
          <SkillConfigPage
            :skill="selectedSkill"
            :userId="getUserId()"
            :mainId="getMainId()"
            @back="closeSkillConfig"
            @saved="handleSkillConfigSaved"
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
                    @click="() => startLocalSession({ inheritCurrentProject: true })"
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
              :model-instance-id="pane.modelInstanceId || undefined"
              :active="pane.key === activeChatKey"
              :shared="pane.shared"
              :user-id="getUserId() || undefined"
              :main-id="getMainId()"
              :auth-token="authToken"
              :running="pane.running"
              :foreign-run="pane.foreignRun"
              :foreign-run-finished="pane.foreignRunFinished"
              :refreshing-session="pane.refreshingSession"
              :busy-notice="pane.busyNotice"
              :stopping="pane.stopping || codeRuntime.stateFor(pane.key).stopping"
              :active-intervention="pane.activeIntervention"
              :code-workspace="codeRuntime.stateFor(pane.key).workspace"
              :code-workspaces="projectWorkspaces"
              :code-workspaces-loading="projectWorkspacesLoading"
              :code-session="codeRuntime.stateFor(pane.key).session"
              :code-events="codeRuntime.stateFor(pane.key).events"
              :code-approvals="codeRuntime.stateFor(pane.key).approvals"
              :code-approval-busy="codeRuntime.stateFor(pane.key).approvalBusy"
              :code-error="codeRuntime.stateFor(pane.key).error"
              :code-workspace-busy="codeRuntime.stateFor(pane.key).busy"
              :code-worktree="codeRuntime.stateFor(pane.key).worktree"
              :code-source-ref="codeRuntime.stateFor(pane.key).sourceRef"
              :code-history-read-only="pane.executionLocation !== 'server' && !codeRuntime.stateFor(pane.key).session"
              :code-history-restoring="codeRuntime.stateFor(pane.key).restoring"
              :code-history-location="pane.executionLocation === 'server' ? undefined : pane.executionLocation"
              :code-history-project="pane.codeProject"
              :code-history-local-folder-unavailable="Boolean(capabilities.localWorkspacePicker && pane.codeProject?.workspace_id && projectWorkspaces.find(workspace => workspace.workspace_id === pane.codeProject?.workspace_id)?.status !== 'ok')"
              :desktop-browser-request="desktopBrowserRequest"
              :browser-session-id="pane.sessionId || pane.key"
              :desktop-tool-tabs="desktopToolTabsFor(pane.key)"
              :desktop-active-tool="desktopActiveToolFor(pane.key)"
              :desktop-available-tools="pane.key === activeChatKey ? desktopAvailableTools : []"
              :desktop-code-review-path="pane.key === activeChatKey ? desktopCodeReviewPath : ''"
              :desktop-code-review-changes="pane.key === activeChatKey ? desktopCodeReviewChanges : null"
              :desktop-code-file-path="pane.key === activeChatKey ? desktopCodeFilePath : ''"
              :agent-policy="userProfile?.agentPolicy"
              @send="(payload) => handlePaneSend(pane.key, payload)"
              @stop="handlePaneStop(pane.key)"
              @refresh-session="refreshOpenSession(pane.sessionId || '')"
              @open-skills="openSkillsPage"
              @open-tools="openToolsPage"
              @open-knowledge="openKnowledgePage"
              @schedule-message="({ prompt, sessionId }) => openScheduledTasks({ prompt, sessionId, create: true })"
              @clear-intervention="chatRuntime.clearPaneIntervention(pane.key)"
              @approval-decided="refreshSessionSummaries"
              @choose-code-workspace="() => openProjectCreate(pane.key)"
              @select-code-workspace="(workspace) => selectBoundProject(pane.key, workspace)"
              @clear-code-workspace="codeRuntime.clear(pane.key)"
              @code-worktree="(enabled) => codeRuntime.setWorktree(pane.key, enabled)"
              @start-local-code-task="createProject"
              @code-source-ref="(fullRef) => codeRuntime.setSourceRef(pane.key, fullRef)"
              @code-branch-updated="(branch) => codeRuntime.setWorkspaceBranch(pane.key, branch)"
              @code-approval="(approvalId, decision, scope) => codeRuntime.decide(pane.key, approvalId, decision, scope)"
              @close-code-panel="hideDesktopTools"
              @select-desktop-tool="selectDesktopTool"
              @close-desktop-tool="closeDesktopTool"
              @open-desktop-tool="openDesktopTool"
              @open-desktop-file-tab="openDesktopFileTab"
              @open-desktop-diff-tab="openDesktopDiffTab"
              @code-workspace-change="refreshDesktopWorkspaceSummary"
              @review-code-changes="reviewCodeChanges"
              @open-code-file="openCodeFile"
            />
          </div>
          </div>
        </template>
      </div>
    </main>
    <component
      :is="ProductLoginModal"
      :open="loginOpen"
      :saved-users="savedUsers"
      @close="loginOpen = false"
      @login-success="handleLoginSuccess"
    />
    <component
      v-if="ProductBillingModal"
      :is="ProductBillingModal"
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
    <component
      v-if="ProductCreateOrganizationModal"
      :is="ProductCreateOrganizationModal"
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
    <div class="max-h-[calc(100vh-48px)] w-full max-w-3xl overflow-y-auto rounded-2xl border border-gray-200 bg-white p-5 shadow-[0_24px_80px_rgba(15,23,42,0.18)]">
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

      <div class="personalization-layout">
        <nav class="personalization-nav" :aria-label="t('shortcuts.personalization_menu')">
          <button type="button" class="personalization-nav-item" :class="{ active: personalizationSection === 'general' }" :aria-current="personalizationSection === 'general' ? 'page' : undefined" @click="personalizationSection = 'general'">
            <SettingsOutline class="personalization-nav-icon" aria-hidden="true" />
            <span>{{ t('shortcuts.general_settings') }}</span>
          </button>
          <button type="button" class="personalization-nav-item" :class="{ active: personalizationSection === 'shortcuts' }" :aria-current="personalizationSection === 'shortcuts' ? 'page' : undefined" @click="personalizationSection = 'shortcuts'">
            <AppsOutline class="personalization-nav-icon" aria-hidden="true" />
            <span>{{ t('shortcuts.title') }}</span>
          </button>
        </nav>

        <main class="personalization-content">
      <div v-show="personalizationSection === 'general'">
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
      <div v-if="personalizationSection === 'shortcuts'" class="mt-5">
        <ShortcutPreferencesPanel :user-id="getUserId()" :main-id="getMainId()" />
      </div>
        </main>
      </div>
    </div>
  </div>
  <div
    v-if="capabilities.isDesktop && settingsPanelOpen"
    class="desktop-settings-modal fixed inset-0 z-[80] flex items-start justify-center bg-slate-900/30 px-4 pb-4 pt-16 backdrop-blur-[2px]"
    @click.self="closeSettingsPanel"
  >
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="desktop-settings-title"
      class="flex max-h-[calc(100vh-80px)] w-full max-w-2xl flex-col overflow-hidden rounded-[28px] border border-gray-200 bg-white shadow-[0_24px_80px_rgba(15,23,42,0.18)]"
    >
      <div class="flex shrink-0 items-center justify-between border-b border-gray-100 py-2 pl-6 pr-3">
        <div id="desktop-settings-title" class="text-lg font-semibold text-gray-900">{{ t('settings.modal.title') }}</div>
        <button
          type="button"
          class="flex min-h-11 min-w-11 items-center justify-center rounded-xl px-3 text-sm text-gray-500 transition-colors hover:bg-gray-100 hover:text-gray-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
          @click="closeSettingsPanel"
        >
          {{ t('ui.close') }}
        </button>
      </div>
      <div class="min-h-0 overflow-y-auto overscroll-contain">
        <SettingsPanel />
      </div>
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

.app-shell--desktop > .desktop-primary-nav {
  padding-top: 58px;
}

.app-shell--windows-desktop > .app-sidebar,
.app-shell--windows-desktop > .app-main {
  padding-top: 88px;
}

.app-shell--windows-desktop > .desktop-primary-nav {
  padding-top: 98px;
}

.app-shell--windows-sidebar-collapsed > .app-sidebar {
  display: none;
}

.desktop-settings-modal,
.desktop-settings-modal * {
  -webkit-app-region: no-drag;
}

.personalization-layout {
  display: grid;
  grid-template-columns: 168px minmax(0, 1fr);
  min-height: 420px;
  overflow: hidden;
  border: 1px solid #e8edf5;
  border-radius: 16px;
  background: #fbfcfe;
}

.personalization-nav {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 14px 10px;
  border-right: 1px solid #e8edf5;
  background: #f6f8fc;
}

.personalization-nav-item {
  display: flex;
  align-items: center;
  gap: 9px;
  min-height: 42px;
  padding: 0 12px;
  border: 0;
  border-radius: 9px;
  color: #64748b;
  background: transparent;
  font-size: 13px;
  text-align: left;
  cursor: pointer;
  transition: color .15s ease, background .15s ease;
}

.personalization-nav-item:hover {
  color: #2563eb;
  background: #eef4ff;
}

.personalization-nav-item.active {
  color: #2563eb;
  background: #e8f0ff;
  font-weight: 600;
}

.personalization-nav-icon {
  display: inline-flex;
  width: 19px;
  height: 19px;
  align-items: center;
  justify-content: center;
  color: currentColor;
}

.personalization-content {
  min-width: 0;
  padding: 20px;
  overflow-y: auto;
  background: #fff;
}

@media (max-width: 640px) {
  .personalization-layout {
    grid-template-columns: 1fr;
    min-height: 0;
  }

  .personalization-nav {
    flex-direction: row;
    border-right: 0;
    border-bottom: 1px solid #e8edf5;
  }

  .personalization-nav-item {
    flex: 1;
    justify-content: center;
  }

  .personalization-content {
    padding: 14px;
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
