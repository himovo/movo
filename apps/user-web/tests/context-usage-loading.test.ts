import assert from 'node:assert/strict'
import { createRenderer, nextTick, ref } from 'vue'
import type { ContextUsage } from '../src/api/contextUsage'
import { useContextUsage } from '../src/components/chat/useContextUsage'

Object.assign(globalThis, {
  document: { hidden: false, addEventListener() {}, removeEventListener() {} },
})

const renderer = createRenderer<object, object>({
  patchProp() {}, insert() {}, remove() {}, setText() {}, setElementText() {},
  createElement: () => ({}), createText: () => ({}), createComment: () => ({}),
  parentNode: () => null, nextSibling: () => null,
})
const session = ref('first')
const pending: Array<{ session: string; signal: AbortSignal; resolve: (value: ContextUsage) => void }> = []
let state!: ReturnType<typeof useContextUsage>
const app = renderer.createApp({
  setup() {
    state = useContextUsage({
      sessionId: () => session.value, modelId: () => 'model',
      active: () => true, running: () => false,
    }, (id, signal) => new Promise(resolve => pending.push({ session: id, signal, resolve })))
    return () => null
  },
})
app.mount({})
try {
  assert.equal(state.loading.value, true)
  await state.refresh()
  assert.equal(pending.length, 1, 'hover must not restart the pending read')
  session.value = 'second'
  assert.equal(pending[0]!.signal.aborted, true)
  assert.equal(state.usage.value, null)
  assert.equal(state.loading.value, true)
  pending[0]!.resolve({ available: true, usedTokens: 999 })
  await nextTick()
  assert.equal(state.usage.value, null, 'late results must not cross conversations')
  pending[1]!.resolve({ available: false })
  await nextTick()
  assert.equal(state.loading.value, false)
  assert.equal(state.usage.value?.available, false)
  const retry = state.refresh()
  assert.equal(state.loading.value, false, 'background retries must not flash a skeleton')
  pending[2]!.resolve({ available: true, usedTokens: 100, capacityTokens: 1000 })
  await retry
  assert.equal(state.usage.value?.usedTokens, 100)
  const refresh = state.refresh()
  assert.equal(state.loading.value, false, 'refreshing readable usage must retain the ring')
  pending[3]!.resolve({ available: true, usedTokens: 120, capacityTokens: 1000 })
  await refresh
  assert.equal(state.usage.value?.usedTokens, 120)
} finally {
  app.unmount()
}
console.log('Context usage loading and conversation isolation passed')
