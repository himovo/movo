import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import vm from 'node:vm'

test('plugin page waiting reports failure after timeout and clears its timer on disposal', async () => {
  let exported, effect, timer, cleanup, failed = false, cleared = false
  const React = {
    Component: class {},
    createElement: (type, props, ...children) => ({ type, props, children }),
    useState: () => [failed, value => { failed = value }],
    useEffect: fn => { effect = fn },
  }
  vm.runInNewContext(await readFile(new URL('../src/plugin-client-shell/page-status.js', import.meta.url), 'utf8'), {
    window: { __ModuleLoader__: { load: module => { exported = module.factory(() => React) } } },
    setTimeout: callback => { timer = callback; return 42 },
    clearTimeout: id => { cleared = id === 42 },
    URLSearchParams,
    location: { search: '?locale=en' }, document: { documentElement: { lang: 'en' } }, navigator: {}, console,
  })
  assert.equal(exported.Waiting().props.failed, false)
  cleanup = effect()
  timer()
  assert.equal(exported.Waiting().props.failed, true)
  cleanup()
  assert.equal(cleared, true)
  const failure = exported.Status({ failed: true })
  assert.equal(failure.props.role, 'alert')
  assert.equal(failure.children[1].children[0], 'Retry')
})
