<script setup lang="ts">
import { createDiscreteApi, darkTheme, NConfigProvider, NDialogProvider, NMessageProvider, NNotificationProvider } from 'naive-ui'
import SkillCreationDialog from './components/SkillCreationDialog.vue'
import DesktopSettingsDialog from './components/desktop/DesktopSettingsDialog.vue'
import DeleteSessionDialog from './components/session/DeleteSessionDialog.vue'
import PersonalizationDialog from './components/PersonalizationDialog.vue'
import SessionSearchOverlay from './components/SessionSearchOverlay.vue'
import AppSidebarContent from './components/AppSidebarContent.vue'
import { useAppSidebarBindings } from './composables/useAppSidebarBindings'
import AppMainRegion from './components/AppMainRegion.vue'
import AppAccountDialogs from './components/AppAccountDialogs.vue'
import productUiExtension from '@movo-product-extension'
import AppDesktopNavigation from './components/desktop/AppDesktopNavigation.vue'
import SessionSnapshotViewer from './components/session/SessionSnapshotViewer.vue'
import DesktopServerSetup from './components/desktop/DesktopServerSetup.vue'
import CreateProjectDialog from './components/code/CreateProjectDialog.vue'
import { capabilities } from './platform'
import { useSkillManagement } from './composables/useSkillManagement'
import { useSessionSearch } from './composables/useSessionSearch'
import { useSessionDirectory } from './composables/useSessionDirectory'
import { useSessionShareLanding } from './composables/useSessionShareLanding'
import { computed, ref, watch } from 'vue'
import AppChatPanes from './components/AppChatPanes.vue'
import type { AppChatPaneActions } from './components/chat/appChatPaneActions'
import { registerProductMessages, t, useLocale } from './composables/i18n'
import { themeOverridesForPlatform } from './composables/naiveThemeOverrides'
import { useAppPreferences } from './composables/useAppPreferences'
import { useAppFeatureActions } from './composables/useAppFeatureActions'
import { useAppAccountActions } from './composables/useAppAccountActions'
import { useAdminConsoleLaunch } from './composables/useAdminConsoleLaunch'
import { useAppStartup } from './composables/useAppStartup'
import { useAppViewState } from './composables/useAppViewState'
import { useAppAuthState } from './composables/useAppAuthState'
import { useAppSessionState } from './composables/useAppSessionState'
import { useAppNavigation } from './composables/useAppNavigation'
import { useAccountIdentity } from './composables/useAccountIdentity'
import { useAuthProfileRefresh } from './composables/useAuthProfileRefresh'
import { useAuthLogin } from './composables/useAuthLogin'
import { useAuthSessionLifecycle } from './composables/useAuthSessionLifecycle'
import { useTenantSwitch } from './composables/useTenantSwitch'
import { useBillingSummary } from './composables/useBillingSummary'
import { useChatRuntimeStore } from './composables/useChatRuntimeStore'
import { usePaneTurnActions } from './composables/usePaneTurnActions'
import { useAppSessionController } from './composables/useAppSessionController'
import { useDshCodeRuntime } from './composables/code/useDshCodeRuntime'
import { useUserBoundProjects } from './composables/code/userBoundProjects'
import { useProjectCreation } from './composables/code/useProjectCreation'
import { useAppProjectBoundary } from './composables/code/useAppProjectBoundary'
import { useSidebarHistory } from './composables/useSidebarHistory'
import { useEnterpriseAccessPolicy } from './composables/useEnterpriseAccessPolicy'
import { useSkillShareInboxBadge } from './composables/useSkillShareInboxBadge'
import { usePersonalKnowledgeBadge } from './composables/usePersonalKnowledgeBadge'
import { useAppDesktopTools } from './composables/desktop/useAppDesktopTools'
import { syncDesktopAgentIdentity } from './composables/desktop/syncDesktopAgentIdentity'

const ProductLoginModal = productUiExtension.loginModal
const ProductBillingModal = productUiExtension.billingModal
const ProductCreateOrganizationModal = productUiExtension.createOrganizationModal
registerProductMessages(productUiExtension.messages)

const {
  storageKeys, loginOpen, billingOpen, profileOpen, createOrganizationOpen,
  authToken, currentAccount, userProfile, savedUsers, loadSavedUsers,
  persistSavedUsers, loadUserProfile, userMenuOpen, adminSsoStarting,
  billingSummary, billingSummaryLoading, billingSummaryLoaded,
  settingsPanelOpen, desktopServerState, personalizationOpen,
  isLoggedIn, availableTenants, getUserId, getMainId, isEnterpriseTenant,
} = useAppAuthState()
watch([authToken, () => userProfile.value?.mainId, () => userProfile.value?.userId], () => productUiExtension.refreshEntryVisibility?.(), { flush: 'sync' })
const {
  token: authTokenKey, account: authAccountKey,
  users: authUsersKey, profile: authUserProfileKey,
} = storageKeys
const { locale } = useLocale()
const {
  themeMode, isDarkTheme, themeOptions, languageSaving,
  timezoneSaving, timezoneValue, timezoneOptions,
  selectThemeMode, selectLanguage, selectTimezone,
  startThemeListener, stopThemeListener,
} = useAppPreferences(locale)
document.documentElement.classList.toggle('platform-desktop', capabilities.isDesktop)
const isWindowsDesktop = capabilities.isDesktop && document.documentElement.classList.contains('platform-windows')
const desktopSidebarCollapsed = ref(false)
const platformThemeOverrides = computed(() => themeOverridesForPlatform(
  isDarkTheme.value && capabilities.isDesktop,
))
const {
  sessions, sessionsLoading, sessionsLoadingMore, sessionsHasMore,
  sharedSessions, sharedSessionsLoading, sharedSessionsLoadingMore,
  sharedSessionsHasMore, deletingSessionId, pendingDeleteSession,
  editingSessionId, editingSessionTitle, renamingSessionId, currentView,
  scheduledTaskInitialPrompt, scheduledTaskInitialSessionId, scheduledTaskCreateRequestKey,
} = useAppSessionState()
const shareToastConfigProviderProps = computed(() => ({
  theme: isDarkTheme.value ? darkTheme : null,
  themeOverrides: platformThemeOverrides.value,
}))
const { message: shareToast } = createDiscreteApi(['message'], { configProviderProps: shareToastConfigProviderProps })
const {
  sessionSearchOpen, sessionSearchQuery, sessionSearchResults,
  sessionSearchLoading, sessionSearchHasMore, sessionSearchDidRun,
  trimmedSessionSearchQuery, closeSessionSearch, runSessionSearch,
} = useSessionSearch({ getUserId, getMainId, authToken })
const { navigateTo, handlePopState } = useAppNavigation(currentView, closeSessionSearch, text => shareToast.info(text))
const {
  skillFormOpen, skillName, skillSummary,
  skillType, skillScenario, skillChannels, skillForms, skillAudience, skillStyle,
  skillRequired, skillForbidden,
  skillCreating, skillEnriching, selectedSkill, loadSkills, closeSkillForm,
  enrichDraftFromForm, createSkill, removeSkill,
} = useSkillManagement({
  getUserId,
  getMainId,
  onCreated: () => { currentView.value = 'skill-config' },
  onSelectedRemoved: () => { currentView.value = 'skills' },
})
const sessionPageSize = 30

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
  fallbackTitle: workspaceId => `${t('app.project')} · ${workspaceId.slice(0, 8)}`,
})
const workspaceTitles = userBoundProjects.titles
const projectWorkspaces = userBoundProjects.workspaces
const projectWorkspacesLoading = userBoundProjects.loading
const {
  normalHistoryExpanded, sharedHistoryExpanded, pinnedHistoryExpanded,
  pinnedSessionIds, pinnedSessions, collapsedProjectHistory,
  isSessionPinned, toggleSessionPin, projectHistoryExpanded, toggleProjectHistory,
  historyItems, projectHistoryGroups, isUnavailableProjectHistory,
} = useSidebarHistory({
  profile: userProfile, sessions, sharedSessions,
  workspaces: projectWorkspaces, workspaceTitles, canUseCode,
  supportsLocalCodeProjects,
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
  onSessionBusy: () => shareToast.info(t('app.sidebar.session_running')),
})
const visibleChatPanes = chatRuntime.panes
const codeRuntime = useDshCodeRuntime(chatRuntime)
const {
  selectBoundProject, clearUserBoundProjectState, prepareProjectBoundary,
} = useAppProjectBoundary({ projects: userBoundProjects, codeRuntime, canUseCode })
const refreshWorkspaceTitles = userBoundProjects.refresh
const activeChatKey = chatRuntime.activeChatKey
const currentSessionId = chatRuntime.currentSessionId
const {
  sessionIsRunning, sessionScheduledIsRunning, sessionNeedsHumanAssistance,
  sessionIsUnread, displaySessionTitle, compactSessionTitle,
  startEditSessionTitle, cancelSessionTitleEdit, commitSessionTitleEdit,
  handleDeleteSession, cancelDeleteSession, confirmDeleteSession,
  loadSessions, refreshSessionSummaries, loadSharedSessions,
  refreshSharedSummaries,
} = useSessionDirectory({
  sessions, sessionsLoading, sessionsLoadingMore, sessionsHasMore,
  sharedSessions, sharedSessionsLoading, sharedSessionsLoadingMore, sharedSessionsHasMore,
  sessionSearchResults, deletingSessionId, pendingDeleteSession,
  editingSessionId, editingSessionTitle, renamingSessionId,
  authToken, canUseCode, pageSize: sessionPageSize, getUserId, getMainId,
  refreshWorkspaceTitles,
  sessionIsRunningLocally: chatRuntime.sessionIsRunning,
  sessionIsUnreadLocally: chatRuntime.sessionIsUnread,
  needsAssistanceLocally: codeRuntime.needsAssistance,
  hasActiveIntervention: sessionId => visibleChatPanes.value.some(
    pane => pane.sessionId === sessionId && Boolean(pane.activeIntervention),
  ),
  removeSession: chatRuntime.removeSession,
  syncActiveRuns: chatRuntime.syncActiveRuns,
})
const {
  desktopPrimarySection, desktopSecondaryNavigationVisible, desktopNavigationWidth,
  desktopWindowTitle, chatHeaderTitle, sessionSearchDisplayItems, sidebarItems,
} = useAppViewState({
  currentView, desktopSidebarCollapsed, currentSessionId, sessions, sharedSessions,
  selectedSkill, trimmedSessionSearchQuery, sessionSearchResults, displaySessionTitle,
})
const {
  createProjectOpen, createProjectBusy, createProjectSelecting,
  createProjectSelectionPhase, createProjectSelectionError,
  createProjectWorkspace, createProjectWorktree,
  addProjectToActiveConversation, createProject, openProjectCreate,
  closeProjectCreate, chooseProjectFolder, commitProjectCreate,
} = useProjectCreation({
  canUseCode, localWorkspacePicker: capabilities.localWorkspacePicker,
  currentView, activeChatKey, token: authToken, profile: userProfile,
  syncIdentity: syncDesktopAgentIdentity, onAuthExpired: () => handleAuthExpired(),
  getPane: key => visibleChatPanes.value.find(item => item.key === key),
  startLocalSession: () => chatRuntime.startLocalSession(),
  setDraftProject: (key, workspace, worktree) => codeRuntime.setDraftProject(key, workspace, worktree),
  addBinding: (binding, workspace) => userBoundProjects.add(binding, workspace),
  navigateToChat: () => navigateTo('chat'),
})
const { logout, handleAuthExpired } = useAuthSessionLifecycle({
  token: authToken, account: currentAccount, profile: userProfile,
  billingSummary, billingSummaryLoaded, userMenuOpen, loginOpen,
  sessions, sharedSessions, sessionsHasMore, sharedSessionsHasMore,
  sessionsLoading, sessionsLoadingMore, sharedSessionsLoading, sharedSessionsLoadingMore,
  createProjectOpen, createProjectSelectionError,
  tokenStorageKey: authTokenKey, accountStorageKey: authAccountKey,
  profileStorageKey: authUserProfileKey,
  clearProjectState: () => clearUserBoundProjectState(true),
  resetChat: () => chatRuntime.reset(),
  closeSessionSearch,
})
const {
  desktopBrowserRequest, activeCodeState,
  desktopCodeReviewPath, desktopCodeReviewChanges, desktopCodeFilePath,
  desktopWorkspaceSummary, refreshDesktopWorkspaceSummary,
  desktopAvailableTools, desktopToolTabs, desktopActiveTool,
  desktopActiveToolKind, desktopToolTabsFor, desktopActiveToolFor,
  openDesktopTool, revealDesktopTool, openDesktopFileTab, openDesktopDiffTab,
  selectDesktopTool, closeDesktopTool, hideDesktopTools,
  toggleDesktopCodePanel, reviewCodeChanges, openCodeFile, requestDesktopBrowser,
} = useAppDesktopTools({
  codeRuntime, activeChatKey, currentView, currentSessionId, locale, canUseBrowser,
})
const activeChatHasMessages = computed(() => (
  visibleChatPanes.value.find((pane) => pane.key === activeChatKey.value)?.messages.length || 0
) > 0)
const { maskedPhone, displayName, displayAvatar, displayAvatarText, handleAvatarError } = useAccountIdentity({
  profile: userProfile, account: currentAccount, token: authToken, profileStorageKey: authUserProfileKey,
})
const { accountTierLabel, quotaTotal, quotaRemaining, quotaUsedPercent, quotaUsedPercentLabel, quotaTotalLabel, loadBillingSummary } = useBillingSummary({
  profile: userProfile, token: authToken, summary: billingSummary, loading: billingSummaryLoading,
  loaded: billingSummaryLoaded, enterpriseSpace: isEnterpriseSpace,
})

const {
  openLogin, closeUserMenu, openProfileEditor, openCreateOrganization,
  openBilling, openPersonalization, closePersonalization,
  handleProfileUpdated, toggleUserMenu, openSettingsPanel,
  closeSettingsPanel, handleDocumentClick,
} = useAppAccountActions({
  isLoggedIn, canCreateOrganization, canUpgradePlan, loginOpen,
  profileOpen, createOrganizationOpen, billingOpen, personalizationOpen,
  userMenuOpen, settingsPanelOpen, userProfile, currentAccount,
  profileStorageKey: authUserProfileKey, accountStorageKey: authAccountKey,
  prepareProjectBoundary, loadBillingSummary,
})

const {
  startLocalSession, selectSession, refreshOpenSession, handleSessionLeft,
} = useAppSessionController({
  chatRuntime, codeRuntime, sharedSessions,
  canUseCode: () => canUseCode.value,
  authToken: () => authToken.value,
  userId: getUserId, mainId: getMainId,
  syncDesktopIdentity: syncDesktopAgentIdentity,
  navigateToChat: () => navigateTo('chat'),
  closeSessionSearch,
  refreshSessionSummaries, refreshSharedSummaries,
  loadSessions: () => loadSessions(true),
  loadSharedSessions: () => loadSharedSessions(true),
  showRefreshError: message => shareToast.error(message),
  showAccessLostNotice: message => shareToast.warning(message),
})

const {
  openTokenUsagePage, closeTokenUsagePage, openScheduledTasks, handleSidebarAction,
  openSkillsPage, closeSkillsPage, openToolsPage, openKnowledgePage,
  openDesktopPrimarySection, openSkillConfig,
  closeSkillConfig, handleCompositeSaved, handleSkillConfigSaved,
} = useAppFeatureActions({
  isLoggedIn, currentSessionId, scheduledTaskInitialPrompt,
  scheduledTaskInitialSessionId, scheduledTaskCreateRequestKey, selectedSkill,
  sessionSearchOpen, navigateTo, openLogin, closeUserMenu, closeSessionSearch,
  startLocalSession, loadSkills, refreshSkillShareCount, refreshPersonalKnowledgeCount,
})

const { switchingTenant, switchToTenant, handleSwitchTenant } = useTenantSwitch({
  token: authToken, profile: userProfile, account: currentAccount,
  billingSummary, billingSummaryLoaded,
  tokenStorageKey: authTokenKey, profileStorageKey: authUserProfileKey,
  accountStorageKey: authAccountKey, getMainId,
  clearProjectState: () => clearUserBoundProjectState(true),
  loadBillingSummary,
  startLocalSession,
  loadSessions: () => loadSessions(true),
  loadSharedSessions: () => loadSharedSessions(true),
})

const { openAdminConsole } = useAdminConsoleLaunch({
  authToken, adminSsoStarting, availableTenants, userProfile,
  isEnterpriseSpace, canAccessAdmin, isEnterpriseTenant, getMainId,
  switchToTenant, activeChatKey, currentSessionId,
  navigateToChat: () => navigateTo('chat'),
  startLocalSession,
  revealDesktopBrowser: () => revealDesktopTool('browser'),
  closeUserMenu,
})

const {
  pendingSnapshotToken, captureSessionShareToken, captureSnapshotToken,
  joinPendingSharedSession,
} = useSessionShareLanding({
  getUserId,
  loadSharedSessions: () => loadSharedSessions(true),
  selectSession,
  showError: message => shareToast.error(message),
})

const { refreshUserProfile } = useAuthProfileRefresh({
  token: authToken, profile: userProfile, loginOpen, sessionsLoading, currentView,
  tokenStorageKey: authTokenKey, profileStorageKey: authUserProfileKey,
  startLocalSession,
  loadSessions: () => loadSessions(true),
  loadSharedSessions: () => loadSharedSessions(true),
  joinPendingSharedSession,
  prepareProjectBoundary,
  onAuthExpired: handleAuthExpired,
  refreshWorkspaceTitles,
  loadSkills,
})

const { handleLoginSuccess } = useAuthLogin({
  sessions, sharedSessions, sessionsHasMore, sharedSessionsHasMore,
  token: authToken, account: currentAccount, profile: userProfile, loginOpen,
  billingSummary, billingSummaryLoaded,
  tokenStorageKey: authTokenKey, accountStorageKey: authAccountKey,
  profileStorageKey: authUserProfileKey,
  resetChat: () => chatRuntime.reset(),
  clearProjectState: () => clearUserBoundProjectState(true),
  persistSavedUser: persistSavedUsers,
  startLocalSession,
  loadSessions: () => loadSessions(true),
  loadSharedSessions: () => loadSharedSessions(true),
  joinPendingSharedSession,
  refreshUserProfile,
  canUseCode, refreshWorkspaceTitles,
})

const { send: handlePaneSend, stop: handlePaneStop } = usePaneTurnActions({
  chatRuntime, codeRuntime,
  canUseCode: () => canUseCode.value,
  authToken: () => authToken.value,
  userId: getUserId, mainId: getMainId,
  profile: () => userProfile.value,
  locale: () => locale.value === 'en' ? 'en' : 'zh',
  timezone: () => timezoneValue.value,
})

const { handleDesktopServerConnected } = useAppStartup({
  storageKeys: { token: authTokenKey, account: authAccountKey, users: authUsersKey, profile: authUserProfileKey },
  locale, currentView, desktopServerState, timezoneValue, currentAccount, authToken,
  userProfile, loginOpen, sessionsLoading,
  captureSessionShareToken, captureSnapshotToken, handleAuthExpired,
  startThemeListener, stopThemeListener, loadSavedUsers, loadUserProfile,
  startLocalSession, refreshUserProfile,
  loadSessions: () => loadSessions(true),
  handleDocumentClick, handlePopState,
  refreshSessionSummaries, refreshSharedSummaries,
})

const chatPaneActions = {
  send: handlePaneSend,
  stop: handlePaneStop,
  refreshSession: refreshOpenSession,
  openSkills: openSkillsPage,
  openTools: openToolsPage,
  openKnowledge: openKnowledgePage,
  scheduleMessage: ({ prompt, sessionId }) => openScheduledTasks({ prompt, sessionId, create: true }),
  clearIntervention: chatRuntime.clearPaneIntervention,
  approvalDecided: refreshSessionSummaries,
  chooseCodeWorkspace: openProjectCreate,
  selectCodeWorkspace: selectBoundProject,
  clearCodeWorkspace: codeRuntime.clear,
  codeWorktree: codeRuntime.setWorktree,
  startLocalCodeTask: createProject,
  codeSourceRef: codeRuntime.setSourceRef,
  codePermissionMode: codeRuntime.setPermissionMode,
  codeBranchUpdated: codeRuntime.setWorkspaceBranch,
  codeApproval: codeRuntime.decide,
  closeCodePanel: hideDesktopTools,
  selectDesktopTool,
  closeDesktopTool,
  openDesktopTool,
  openDesktopFileTab,
  openDesktopDiffTab,
  codeWorkspaceChange: refreshDesktopWorkspaceSummary,
  reviewCodeChanges,
  openCodeFile,
} satisfies AppChatPaneActions

const sidebarBindings = useAppSidebarBindings({
  desktopSecondaryNavigationVisible, sidebarItems, sessionSearchOpen, isLoggedIn,
  displayAvatar, displayAvatarText, displayName, accountTierLabel,
  handleSidebarAction, toggleUserMenu, openLogin, handleAvatarError,
  pinnedHistoryExpanded, normalHistoryExpanded, sharedHistoryExpanded,
  editingSessionTitle, pinnedSessions, historyItems, sharedSessions,
  projectHistoryGroups, currentSessionId, currentView, sessionsLoading,
  sessionsLoadingMore, sessionsHasMore, sharedSessionsLoading,
  sharedSessionsLoadingMore, sharedSessionsHasMore, sessionPageSize,
  trimmedSessionSearchQuery, editingSessionId, renamingSessionId,
  deletingSessionId, canUseCode, supportsLocalCodeProjects,
  isSessionPinned, isUnavailableProjectHistory, sessionNeedsHumanAssistance,
  sessionScheduledIsRunning, sessionIsRunning, sessionIsUnread,
  displaySessionTitle, compactSessionTitle, selectSession, toggleSessionPin,
  startEditSessionTitle, commitSessionTitleEdit, cancelSessionTitleEdit,
  handleDeleteSession, loadSessions, loadSharedSessions,
  projectHistoryExpanded, toggleProjectHistory, createProject,
  canUseSkills, canUseTools, pendingSkillShareCount, personalKnowledgeUnreadCount,
  openSkillsPage, navigateTo, openToolsPage, openKnowledgePage,
  userMenuOpen, maskedPhone, billingSummary, billingSummaryLoading,
  billingSummaryLoaded, quotaRemaining, quotaTotal, quotaTotalLabel,
  quotaUsedPercent, quotaUsedPercentLabel, availableTenants, getMainId,
  switchingTenant, adminSsoStarting, canCreateOrganization, canUpgradePlan,
  userProfile, locale, canAccessAdmin, isEnterpriseTenant,
  openProfileEditor, openTokenUsagePage, handleSwitchTenant,
  openAdminConsole, openCreateOrganization, openBilling,
  openPersonalization, openSettingsPanel, logout,
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
      @update:worktree="(value) => createProjectWorktree = value"
      @choose-folder="chooseProjectFolder"
      @create="commitProjectCreate"
      @close="closeProjectCreate"
    />
    <AppDesktopNavigation
      v-if="capabilities.isDesktop"
      :windows="isWindowsDesktop"
      :collapsed="desktopSidebarCollapsed"
      :dark="isDarkTheme"
      :locale="locale === 'en' ? 'en' : 'zh'"
      :navigation-width="desktopNavigationWidth"
      :section="desktopPrimarySection"
      :title="desktopWindowTitle"
      :view="currentView"
      :session-id="currentSessionId"
      :user-id="getUserId()"
      :main-id="getMainId()"
      :auth-token="authToken"
      :members-revision="currentSessionId ? chatRuntime.membersRevisionFor(currentSessionId) : undefined"
      :code-state="activeCodeState"
      :workspace-summary="desktopWorkspaceSummary"
      :has-messages="activeChatHasMessages"
      :active-tool="desktopActiveToolKind"
      :code-available="canUseCode"
      :browser-available="canUseBrowser"
      :workspaces="projectWorkspaces"
      :workspaces-loading="projectWorkspacesLoading"
      :skills-available="canUseSkills"
      :tools-available="canUseTools"
      :knowledge-available="canUseKnowledge"
      :skill-badge="pendingSkillShareCount"
      :knowledge-badge="personalKnowledgeUnreadCount"
      :logged-in="isLoggedIn"
      :avatar-url="displayAvatar()"
      :avatar-text="displayAvatarText()"
      :account-label="isLoggedIn ? displayName() : t('app.sidebar.login_register')"
      @toggle-sidebar="desktopSidebarCollapsed = !desktopSidebarCollapsed"
      @new-chat="handleSidebarAction('plus')"
      @add-project="createProject"
      @session-left="handleSessionLeft"
      @choose-workspace="addProjectToActiveConversation"
      @select-workspace="(workspace) => selectBoundProject(activeChatKey, workspace)"
      @clear-workspace="codeRuntime.clear(activeChatKey)"
      @worktree="(enabled) => codeRuntime.setWorktree(activeChatKey, enabled)"
      @source-ref="(fullRef) => codeRuntime.setSourceRef(activeChatKey, fullRef)"
      @branch-updated="(branch) => codeRuntime.setWorkspaceBranch(activeChatKey, branch)"
      @open-browser="requestDesktopBrowser"
      @toggle-code-panel="toggleDesktopCodePanel"
      @back="closeSkillsPage"
      @navigate="openDesktopPrimarySection"
      @account="toggleUserMenu"
      @avatar-error="handleAvatarError"
    />
    <AppSidebarContent :bindings="sidebarBindings" />

    <AppMainRegion
      :desktop="capabilities.isDesktop"
      :current-view="currentView"
      :current-session-id="currentSessionId"
      :chat-header-title="chatHeaderTitle"
      :user-id="getUserId()"
      :main-id="getMainId()"
      :auth-token="authToken"
      :members-revision="currentSessionId ? chatRuntime.membersRevisionFor(currentSessionId) : undefined"
      :selected-skill="selectedSkill"
      :pending-skill-share-action-count="pendingSkillShareActionCount"
      :pending-skill-feedback-count="pendingSkillFeedbackCount"
      :personal-knowledge-share-count="personalKnowledgeShareCount"
      :personal-knowledge-unread-count="personalKnowledgeUnreadCount"
      :sessions="sessions"
      :scheduled-task-initial-session-id="scheduledTaskInitialSessionId"
      :scheduled-task-initial-prompt="scheduledTaskInitialPrompt"
      :scheduled-task-create-request-key="scheduledTaskCreateRequestKey"
      :timezone-value="timezoneValue"
      @session-left="handleSessionLeft"
      @configure="openSkillConfig"
      @login="openLogin"
      @share-count-change="refreshSkillShareCount"
      @knowledge-viewed="refreshPersonalKnowledgeCount"
      @skill-back="closeSkillConfig"
      @skill-saved="handleSkillConfigSaved"
      @composite-saved="handleCompositeSaved"
      @remove-skill="removeSkill"
      @scheduled-back="navigateTo('chat')"
      @open-session="selectSession"
      @usage-back="closeTokenUsagePage"
    >
      <template #chat>
            <SessionSearchOverlay
              :open="sessionSearchOpen"
              :query="sessionSearchQuery"
              :trimmed-query="trimmedSessionSearchQuery"
              :results="sessionSearchResults"
              :display-items="sessionSearchDisplayItems"
              :loading="sessionSearchLoading"
              :did-run="sessionSearchDidRun"
              :has-more="sessionSearchHasMore"
              :current-session-id="currentSessionId"
              :editing-session-id="editingSessionId"
              :editing-title="editingSessionTitle"
              :renaming-session-id="renamingSessionId"
              :deleting-session-id="deletingSessionId"
              :display-session-title="displaySessionTitle"
              :compact-session-title="compactSessionTitle"
              :session-needs-human-assistance="sessionNeedsHumanAssistance"
              :session-scheduled-is-running="sessionScheduledIsRunning"
              :session-is-running="sessionIsRunning"
              :session-is-unread="sessionIsUnread"
              @close="closeSessionSearch"
              @update:query="sessionSearchQuery = $event"
              @update:editing-title="editingSessionTitle = $event"
              @new-session="startLocalSession({ inheritCurrentProject: true })"
              @select-session="selectSession"
              @edit-session="startEditSessionTitle"
              @commit-title="commitSessionTitleEdit"
              @cancel-title="cancelSessionTitleEdit"
              @delete-session="handleDeleteSession"
              @load-more="runSessionSearch(false)"
            />
          <AppChatPanes
            :panes="visibleChatPanes"
            :active-key="activeChatKey"
            :code-state-for="codeRuntime.stateFor"
            :user-id="getUserId() || undefined"
            :main-id="getMainId()"
            :auth-token="authToken"
            :project-workspaces="projectWorkspaces"
            :project-workspaces-loading="projectWorkspacesLoading"
            :desktop-browser-request="desktopBrowserRequest"
            :desktop-tool-tabs-for="desktopToolTabsFor"
            :desktop-active-tool-for="desktopActiveToolFor"
            :desktop-available-tools="desktopAvailableTools"
            :desktop-code-review-path="desktopCodeReviewPath"
            :desktop-code-review-changes="desktopCodeReviewChanges"
            :desktop-code-file-path="desktopCodeFilePath"
            :agent-policy="userProfile?.agentPolicy"
            :actions="chatPaneActions"
          />
      </template>
    </AppMainRegion>
    <AppAccountDialogs
      :login-modal="ProductLoginModal"
      :billing-modal="ProductBillingModal"
      :create-organization-modal="ProductCreateOrganizationModal"
      :login-open="loginOpen"
      :billing-open="billingOpen"
      :profile-open="profileOpen"
      :create-organization-open="createOrganizationOpen"
      :saved-users="savedUsers"
      :token="authToken"
      :profile="userProfile"
      :can-access-billing-admin="isEnterpriseSpace && userProfile?.canAccessAdmin === true"
      @close-login="loginOpen = false"
      @close-billing="billingOpen = false"
      @close-profile="profileOpen = false"
      @close-create-organization="createOrganizationOpen = false"
      @login-success="handleLoginSuccess"
      @profile-updated="handleProfileUpdated"
    />

    <DeleteSessionDialog
      :session="pendingDeleteSession"
      :deleting-session-id="deletingSessionId"
      @cancel="cancelDeleteSession"
      @confirm="confirmDeleteSession"
    />
  </div>

  <SkillCreationDialog v-model:name="skillName" v-model:summary="skillSummary" v-model:type="skillType" v-model:scenario="skillScenario" v-model:channels="skillChannels" v-model:forms="skillForms" v-model:audience="skillAudience" v-model:style="skillStyle" v-model:required="skillRequired" v-model:forbidden="skillForbidden" :open="skillFormOpen" :creating="skillCreating" :enriching="skillEnriching" @close="closeSkillForm" @enrich="enrichDraftFromForm" @create="createSkill" />
  <PersonalizationDialog
    :open="personalizationOpen"
    :locale="locale"
    :language-saving="languageSaving"
    :timezone-value="timezoneValue"
    :timezone-options="timezoneOptions"
    :timezone-saving="timezoneSaving"
    :theme-mode="themeMode"
    :theme-options="themeOptions"
    :user-id="getUserId()"
    :main-id="getMainId()"
    @close="closePersonalization"
    @select-language="selectLanguage"
    @select-timezone="selectTimezone"
    @select-theme="selectThemeMode"
  />
  <DesktopSettingsDialog :open="capabilities.isDesktop && settingsPanelOpen" @close="closeSettingsPanel" />
  <SessionSnapshotViewer
    v-if="pendingSnapshotToken && authToken && userProfile"
    :token="pendingSnapshotToken"
    @close="pendingSnapshotToken = null"
  />
  </n-dialog-provider>
  </n-notification-provider>
  </n-message-provider>
  </n-config-provider>
</template>

<style src="./styles/appShell.css"></style>
