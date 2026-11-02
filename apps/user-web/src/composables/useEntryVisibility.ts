import productUiExtension from '@movo-product-extension'
import type { UserEntry } from '../product/contracts'
import type { AppView } from './useAppNavigation'

export function entryVisible(key: UserEntry): boolean {
  const state = productUiExtension.entryVisibility?.value
  return !state || (state.ready && state.entries[key] !== false)
}

export function entryForView(view: AppView): UserEntry | undefined {
  if (view === 'skill-config' || view === 'composite-editor') return 'skills'
  if (view === 'scheduled-tasks') return 'scheduled'
  if (['skills', 'plugins', 'tools', 'knowledge'].includes(view)) return view as UserEntry
}

export function viewEntryVisible(view: AppView): boolean {
  const key = entryForView(view)
  return !key || entryVisible(key)
}

export function entryVisibilityReady(): boolean {
  return productUiExtension.entryVisibility?.value.ready ?? true
}
