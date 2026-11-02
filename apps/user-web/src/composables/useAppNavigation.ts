import { watch, type Ref } from 'vue'
import { entryVisibilityReady, viewEntryVisible } from './useEntryVisibility'
import { t } from './i18n'

export type AppView = 'chat' | 'skills' | 'plugins' | 'tools' | 'knowledge'
  | 'skill-config' | 'composite-editor' | 'token-usage' | 'scheduled-tasks'

export function resolveViewFromPath(pathname: string): AppView {
  const path = String(pathname || '/').replace(/\/+$/, '') || '/'
  if (path === '/usage' || path === '/token-usage') return 'token-usage'
  if (path === '/skills') return 'skills'
  if (path === '/plugins') return 'plugins'
  if (path === '/tools') return 'tools'
  if (path === '/knowledge') return 'knowledge'
  if (path === '/scheduled-tasks') return 'scheduled-tasks'
  return 'chat'
}

function routePathForView(view: AppView): string {
  if (view === 'token-usage') return '/usage'
  if (view === 'tools') return '/tools'
  if (view === 'knowledge') return '/knowledge'
  if (view === 'scheduled-tasks') return '/scheduled-tasks'
  if (view === 'skills' || view === 'skill-config' || view === 'composite-editor') return '/skills'
  if (view === 'plugins') return '/plugins'
  return '/'
}

export function useAppNavigation(currentView: Ref<AppView>, closeSessionSearch: () => void, notifyUnavailable?: (message: string) => void) {
  function navigateTo(view: AppView, replace = false): void {
    if (!viewEntryVisible(view)) {
      if (entryVisibilityReady()) notifyUnavailable?.(t('app.entryUnavailable'))
      view = 'chat'
    }
    currentView.value = view
    if (typeof window === 'undefined') return
    const nextPath = routePathForView(view)
    const currentPath = window.location.pathname || '/'
    if (currentPath === nextPath) return
    window.history[replace ? 'replaceState' : 'pushState']({}, '', nextPath)
  }

  function handlePopState(): void {
    currentView.value = resolveViewFromPath(window.location.pathname)
    if (currentView.value !== 'chat') closeSessionSearch()
  }

  watch(() => [currentView.value, entryVisibilityReady(), viewEntryVisible(currentView.value)], () => {
    if (entryVisibilityReady() && !viewEntryVisible(currentView.value)) navigateTo(currentView.value, true)
  }, { immediate: true })

  return { navigateTo, handlePopState }
}
