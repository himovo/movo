import assert from 'node:assert/strict'

class FakeHTMLElement {
  dataset: Record<string, string> = {}
  isContentEditable = false
  matches(selector: string): boolean {
    return selector.split(',').map(value => value.trim()).includes('textarea')
  }
}

class FakeTextareaElement extends FakeHTMLElement {
  disabled = false
  readOnly = false
}

Object.assign(globalThis, {
  HTMLElement: FakeHTMLElement,
  HTMLTextAreaElement: FakeTextareaElement,
  document: { body: {}, documentElement: {} },
})

const { shouldAutofocusComposer } = await import('../src/composables/composerFocusPolicy')

const input = new FakeTextareaElement() as unknown as HTMLTextAreaElement
const base = {
  activeElement: null,
  documentVisible: true,
  hasBlockingOverlay: false,
  hasTextSelection: false,
  mobileDevice: false,
}

assert.equal(shouldAutofocusComposer(input, true, base), true, 'focuses an available composer')
assert.equal(shouldAutofocusComposer(input, false, base), false, 'ignores inactive chat panes')
assert.equal(shouldAutofocusComposer(input, true, { ...base, mobileDevice: true }), false, 'does not open a mobile keyboard')
assert.equal(shouldAutofocusComposer(input, true, { ...base, hasBlockingOverlay: true }), false, 'does not focus behind a dialog')
assert.equal(shouldAutofocusComposer(input, true, { ...base, hasTextSelection: true }), false, 'preserves text selection')

const search = new FakeHTMLElement() as unknown as HTMLElement
assert.equal(shouldAutofocusComposer(input, true, { ...base, activeElement: search }), false, 'does not steal deliberate focus')
assert.equal(
  shouldAutofocusComposer(input, true, { ...base, activeElement: search }, true),
  true,
  'moves focus from navigation controls after an explicit chat switch',
)
assert.equal(
  shouldAutofocusComposer(input, true, { ...base, activeElement: search, hasBlockingOverlay: true }, true),
  false,
  'navigation never focuses behind a dialog',
)

const priorComposer = new FakeTextareaElement()
priorComposer.dataset.chatComposerInput = 'true'
assert.equal(
  shouldAutofocusComposer(input, true, { ...base, activeElement: priorComposer as unknown as HTMLElement }),
  true,
  'moves focus when switching chat panes',
)

console.log('composer focus policy tests passed')
