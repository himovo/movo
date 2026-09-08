import assert from 'node:assert/strict'
import { canDisplayEmbeddedBrowserSurface } from '../src/composables/browser/browserSurfaceVisibility'

const base = {
  embeddedBrowser: true,
  activePane: true,
  browserActive: true,
  sessionMatches: false,
}

assert.equal(
  canDisplayEmbeddedBrowserSurface({ ...base, purpose: 'internal' }),
  true,
  'an internal page can use a new chat pane before a server session exists',
)
assert.equal(canDisplayEmbeddedBrowserSurface({ ...base, purpose: 'preview' }), true)
assert.equal(canDisplayEmbeddedBrowserSurface({ ...base, purpose: 'automation' }), false)
assert.equal(
  canDisplayEmbeddedBrowserSurface({ ...base, purpose: 'automation', sessionMatches: true }),
  true,
)
assert.equal(
  canDisplayEmbeddedBrowserSurface({ ...base, purpose: 'internal', activePane: false }),
  false,
)

console.log('browser surface visibility tests passed')
