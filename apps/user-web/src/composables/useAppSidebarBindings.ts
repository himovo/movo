import { computed, type Ref } from 'vue'
import { capabilities } from '../platform'
import type { AppSidebarBindings } from '../components/AppSidebarContent.vue'

type Layout = AppSidebarBindings['layout']
type History = AppSidebarBindings['history']
type Features = AppSidebarBindings['features']
type Account = AppSidebarBindings['account']

export interface AppSidebarSources {
  desktopSecondaryNavigationVisible: Ref<boolean>
  sidebarItems: Ref<Layout['items']>
  sessionSearchOpen: Ref<boolean>
  isLoggedIn: Ref<boolean>
  displayAvatar: () => string
  displayAvatarText: () => string
  displayName: () => string
  accountTierLabel: Ref<string>
  handleSidebarAction: NonNullable<Layout['onAction']>
  toggleUserMenu: NonNullable<Layout['onAccount']>
  openLogin: NonNullable<Layout['onLogin']>
  handleAvatarError: (event: Event) => void
  pinnedHistoryExpanded: Ref<boolean>
  normalHistoryExpanded: Ref<boolean>
  sharedHistoryExpanded: Ref<boolean>
  editingSessionTitle: Ref<string>
  pinnedSessions: Ref<History['pinnedSessions']>
  historyItems: Ref<History['historyItems']>
  sharedSessions: Ref<History['sharedSessions']>
  projectHistoryGroups: Ref<History['projectHistoryGroups']>
  currentSessionId: Ref<History['currentSessionId']>
  currentView: Ref<Features['currentView']>
  sessionsLoading: Ref<boolean>
  sessionsLoadingMore: Ref<boolean>
  sessionsHasMore: Ref<boolean>
  sharedSessionsLoading: Ref<boolean>
  sharedSessionsLoadingMore: Ref<boolean>
  sharedSessionsHasMore: Ref<boolean>
  sessionPageSize: number
  trimmedSessionSearchQuery: Ref<string>
  editingSessionId: Ref<History['editingSessionId']>
  renamingSessionId: Ref<History['renamingSessionId']>
  deletingSessionId: Ref<History['deletingSessionId']>
  canUseCode: Ref<boolean>
  supportsLocalCodeProjects: boolean
  isSessionPinned: History['isSessionPinned']
  isUnavailableProjectHistory: History['isUnavailableProjectHistory']
  sessionNeedsHumanAssistance: History['sessionNeedsHumanAssistance']
  sessionScheduledIsRunning: History['sessionScheduledIsRunning']
  sessionIsRunning: History['sessionIsRunning']
  sessionIsUnread: History['sessionIsUnread']
  displaySessionTitle: History['displaySessionTitle']
  compactSessionTitle: History['compactSessionTitle']
  selectSession: History['selectSession']
  toggleSessionPin: History['toggleSessionPin']
  startEditSessionTitle: History['startEditSessionTitle']
  commitSessionTitleEdit: History['commitSessionTitleEdit']
  cancelSessionTitleEdit: History['cancelSessionTitleEdit']
  handleDeleteSession: History['handleDeleteSession']
  loadSessions: History['loadSessions']
  loadSharedSessions: History['loadSharedSessions']
  projectHistoryExpanded: History['projectHistoryExpanded']
  toggleProjectHistory: History['toggleProjectHistory']
  createProject: History['createProject']
  canUseSkills: Ref<boolean>
  canUseTools: Ref<boolean>
  pendingSkillShareCount: Ref<number>
  personalKnowledgeUnreadCount: Ref<number>
  openSkillsPage: NonNullable<Features['onSkills']>
  navigateTo: (view: 'plugins') => unknown
  openToolsPage: NonNullable<Features['onTools']>
  openKnowledgePage: NonNullable<Features['onKnowledge']>
  userMenuOpen: Ref<boolean>
  maskedPhone: () => string
  billingSummary: Ref<unknown>
  billingSummaryLoading: Ref<boolean>
  billingSummaryLoaded: Ref<boolean>
  quotaRemaining: Ref<number>
  quotaTotal: Ref<number>
  quotaTotalLabel: Ref<string>
  quotaUsedPercent: Ref<number>
  quotaUsedPercentLabel: Ref<string>
  availableTenants: Ref<Account['availableTenants']>
  getMainId: () => string
  getUserId: () => string | null
  switchingTenant: Ref<boolean>
  adminSsoStarting: Ref<boolean>
  canCreateOrganization: Ref<boolean>
  canUpgradePlan: Ref<boolean>
  userProfile: Ref<{ orgName?: string } | null>
  locale: Ref<Account['locale']>
  canAccessAdmin: Account['canAccessAdmin']
  isEnterpriseTenant: Account['isEnterpriseTenant']
  openProfileEditor: NonNullable<Account['onProfile']>
  openTokenUsagePage: NonNullable<Account['onUsage']>
  handleSwitchTenant: NonNullable<Account['onSwitchTenant']>
  openAdminConsole: NonNullable<Account['onAdmin']>
  openCreateOrganization: NonNullable<Account['onCreateOrganization']>
  openBilling: NonNullable<Account['onBilling']>
  openPersonalization: NonNullable<Account['onPersonalization']>
  openSettingsPanel: NonNullable<Account['onSettings']>
  logout: NonNullable<Account['onLogout']>
}

export function useAppSidebarBindings(sources: AppSidebarSources) {
  const {
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
    quotaUsedPercent, quotaUsedPercentLabel, availableTenants, getMainId, getUserId,
    switchingTenant, adminSsoStarting, canCreateOrganization, canUpgradePlan,
    userProfile, locale, canAccessAdmin, isEnterpriseTenant,
    openProfileEditor, openTokenUsagePage, handleSwitchTenant,
    openAdminConsole, openCreateOrganization, openBilling,
    openPersonalization, openSettingsPanel, logout,
  } = sources
  const sidebarBindings = computed<AppSidebarBindings>(() => ({
  visible: !capabilities.isDesktop || desktopSecondaryNavigationVisible.value,
  layout: {
    desktop: capabilities.isDesktop,
    items: sidebarItems.value,
    searchOpen: sessionSearchOpen.value,
    loggedIn: isLoggedIn.value,
    avatarUrl: displayAvatar(),
    avatarText: displayAvatarText(),
    displayName: displayName(),
    accountTierLabel: accountTierLabel.value,
    onAction: handleSidebarAction,
    onAccount: toggleUserMenu,
    onLogin: openLogin,
    onAvatarError: handleAvatarError,
  },
  history: {
    pinnedExpanded: pinnedHistoryExpanded.value,
    normalExpanded: normalHistoryExpanded.value,
    sharedExpanded: sharedHistoryExpanded.value,
    editingTitle: editingSessionTitle.value,
    'onUpdate:pinnedExpanded': value => { pinnedHistoryExpanded.value = value },
    'onUpdate:normalExpanded': value => { normalHistoryExpanded.value = value },
    'onUpdate:sharedExpanded': value => { sharedHistoryExpanded.value = value },
    'onUpdate:editingTitle': value => { editingSessionTitle.value = value },
    pinnedSessions: pinnedSessions.value,
    historyItems: historyItems.value,
    sharedSessions: sharedSessions.value,
    projectHistoryGroups: projectHistoryGroups.value,
    currentSessionId: currentSessionId.value,
    currentView: currentView.value,
    sessionsLoading: sessionsLoading.value,
    sessionsLoadingMore: sessionsLoadingMore.value,
    sessionsHasMore: sessionsHasMore.value,
    sharedSessionsLoading: sharedSessionsLoading.value,
    sharedSessionsLoadingMore: sharedSessionsLoadingMore.value,
    sharedSessionsHasMore: sharedSessionsHasMore.value,
    sessionPageSize,
    trimmedSessionSearchQuery: trimmedSessionSearchQuery.value,
    editingSessionId: editingSessionId.value,
    renamingSessionId: renamingSessionId.value,
    deletingSessionId: deletingSessionId.value,
    canUseCode: canUseCode.value,
    supportsLocalCodeProjects,
    localWorkspacePicker: capabilities.localWorkspacePicker,
    isSessionPinned,
    isUnavailableProjectHistory,
    sessionNeedsHumanAssistance,
    sessionScheduledIsRunning,
    sessionIsRunning,
    sessionIsUnread,
    displaySessionTitle,
    compactSessionTitle,
    selectSession,
    toggleSessionPin,
    startEditSessionTitle,
    commitSessionTitleEdit,
    cancelSessionTitleEdit,
    handleDeleteSession,
    loadSessions,
    loadSharedSessions,
    projectHistoryExpanded,
    toggleProjectHistory,
    createProject,
  },
  showFeatures: !capabilities.isDesktop && (canUseSkills.value || canUseTools.value),
  pluginShortcuts: {
    mainId: getMainId(),
    userId: getUserId() || '',
    loggedIn: isLoggedIn.value,
    currentView: currentView.value,
  },
  features: {
    currentView: currentView.value,
    canUseSkills: canUseSkills.value,
    canUseTools: canUseTools.value,
    pendingSkillShareCount: pendingSkillShareCount.value,
    personalKnowledgeUnreadCount: personalKnowledgeUnreadCount.value,
    onSkills: openSkillsPage,
    onPlugins: () => navigateTo('plugins'),
    onTools: openToolsPage,
    onKnowledge: openKnowledgePage,
  },
  account: {
    open: userMenuOpen.value,
    loggedIn: isLoggedIn.value,
    desktop: capabilities.isDesktop,
    avatarUrl: displayAvatar(),
    avatarText: displayAvatarText(),
    displayName: displayName(),
    maskedPhone: maskedPhone(),
    accountTierLabel: accountTierLabel.value,
    billingSummary: billingSummary.value,
    billingSummaryLoading: billingSummaryLoading.value,
    billingSummaryLoaded: billingSummaryLoaded.value,
    quotaRemaining: quotaRemaining.value,
    quotaTotal: quotaTotal.value,
    quotaTotalLabel: quotaTotalLabel.value,
    quotaUsedPercent: quotaUsedPercent.value,
    quotaUsedPercentLabel: quotaUsedPercentLabel.value,
    availableTenants: availableTenants.value,
    mainId: getMainId(),
    switchingTenant: switchingTenant.value,
    adminSsoStarting: adminSsoStarting.value,
    canCreateOrganization: canCreateOrganization.value,
    canUpgradePlan: canUpgradePlan.value,
    orgName: userProfile.value?.orgName,
    locale: locale.value,
    canAccessAdmin,
    isEnterpriseTenant,
    onAvatarError: handleAvatarError,
    onProfile: openProfileEditor,
    onUsage: openTokenUsagePage,
    onSwitchTenant: handleSwitchTenant,
    onAdmin: openAdminConsole,
    onCreateOrganization: openCreateOrganization,
    onBilling: openBilling,
    onPersonalization: openPersonalization,
    onSettings: openSettingsPanel,
    onLogout: logout,
  },
}))
  return sidebarBindings
}
