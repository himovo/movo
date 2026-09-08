import type { BrowserPurpose } from '../../platform/types'

export function canDisplayEmbeddedBrowserSurface(input: {
  embeddedBrowser: boolean
  activePane: boolean
  browserActive: boolean
  purpose: BrowserPurpose
  sessionMatches: boolean
}): boolean {
  if (!input.embeddedBrowser || !input.activePane || !input.browserActive) return false
  return input.purpose === 'automation' ? input.sessionMatches : true
}
