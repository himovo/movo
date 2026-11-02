import { entryVisible } from './useEntryVisibility'
import { computed, type Ref } from 'vue'
import type { SessionSearchResult, SessionSummary } from '../api/sessions'
import type { DesktopPrimarySection } from '../components/desktop/DesktopPrimaryNavigation.vue'
import { capabilities } from '../platform'
import { t } from './i18n'
import type { AppView } from './useAppNavigation'

type Options = {
  currentView: Ref<AppView>
  desktopSidebarCollapsed: Ref<boolean>
  currentSessionId: Ref<string | null>
  sessions: Ref<SessionSummary[]>
  sharedSessions: Ref<SessionSummary[]>
  selectedSkill: Ref<any>
  trimmedSessionSearchQuery: Ref<string>
  sessionSearchResults: Ref<SessionSearchResult[]>
  displaySessionTitle: (session: Pick<SessionSummary, 'title'>) => string
}

/** Keeps navigation and title projections out of the root component. */
export function useAppViewState(options: Options) {
  const desktopPrimarySection = computed<DesktopPrimarySection>(() => {
    const view = options.currentView.value
    if (view === 'scheduled-tasks') return 'scheduled'
    if (view === 'skills' || view === 'skill-config' || view === 'composite-editor') return 'skills'
    if (view === 'plugins') return 'plugins'
    if (view === 'tools') return 'tools'
    if (view === 'knowledge') return 'knowledge'
    return 'home'
  })

  const desktopSecondaryNavigationVisible = computed(() =>
    capabilities.isDesktop && desktopPrimarySection.value === 'home' && !options.desktopSidebarCollapsed.value,
  )
  const desktopNavigationWidth = computed(() => capabilities.isDesktop
    ? 52 + (desktopSecondaryNavigationVisible.value ? 260 : 0)
    : 260)

  const desktopWindowTitle = computed(() => {
    const view = options.currentView.value
    if (view === 'chat') {
      const current = options.sessions.value.find(session => session.id === options.currentSessionId.value)
      return current ? options.displaySessionTitle(current) : t('app.sidebar.new_chat')
    }
    if (view === 'tools') return t('app.sidebar.tools')
    if (view === 'knowledge') return t('knowledge.sidebar')
    if (view === 'scheduled-tasks') return t('app.scheduledTasks')
    if (view === 'token-usage') return t('app.account.usage')
    if (view === 'skill-config' || view === 'composite-editor') {
      return options.selectedSkill.value?.name || t('app.sidebar.marketplace')
    }
    return t('app.sidebar.marketplace')
  })

  const chatHeaderTitle = computed(() => {
    if (options.currentView.value !== 'chat') return ''
    const current = options.sessions.value.find(session => session.id === options.currentSessionId.value)
      || options.sharedSessions.value.find(session => session.id === options.currentSessionId.value)
    return current ? options.displaySessionTitle(current) : ''
  })

  const sessionSearchDisplayItems = computed(() =>
    options.trimmedSessionSearchQuery.value ? options.sessionSearchResults.value : options.sessions.value,
  )
  const sidebarItems = computed(() => [
    { icon: 'plus', label: t('app.sidebar.new_chat') },
    ...(capabilities.isDesktop || !entryVisible('scheduled') ? [] : [{ icon: 'clock', label: t('app.scheduledTasks') }]),
    { icon: 'search', label: t('app.sidebar.search_chats') },
  ])

  return {
    desktopPrimarySection, desktopSecondaryNavigationVisible, desktopNavigationWidth,
    desktopWindowTitle, chatHeaderTitle, sessionSearchDisplayItems, sidebarItems,
  }
}
