import assert from 'node:assert/strict'
import { effectScope, nextTick, ref } from 'vue'
import extension from './fixtures/entry-visibility-extension'
import { entryVisible, viewEntryVisible } from '../src/composables/useEntryVisibility'
import { useAppNavigation, type AppView } from '../src/composables/useAppNavigation'

const paths: string[] = []
;(globalThis as any).window = { location: { pathname: '/skills' }, history: {
  replaceState: (_: unknown, __: string, path: string) => paths.push(path),
  pushState: (_: unknown, __: string, path: string) => paths.push(path),
} }
assert.equal(entryVisible('skills'), true, 'Community defaults to visible')
extension.entryVisibility.value = { ready: false, entries: {} }
assert.equal(entryVisible('skills'), false, 'Hide entries until policy loads')
assert.equal(viewEntryVisible('chat'), true)
const current = ref<AppView>('skills')
const notices: string[] = []
const scope = effectScope()
let nav!: ReturnType<typeof useAppNavigation>
scope.run(() => { nav = useAppNavigation(current, () => {}, text => notices.push(text)) })
assert.equal(current.value, 'skills', 'Wait for policy before redirecting')
extension.entryVisibility.value = { ready: true, entries: { skills: false, tools: true } }
await nextTick()
assert.equal(current.value, 'chat', 'Blocked initial deep link returns to chat')
assert.equal(paths.at(-1), '/')
assert.equal(notices.length, 1)
assert.equal(viewEntryVisible('skill-config'), false)
assert.equal(viewEntryVisible('composite-editor'), false)
nav.navigateTo('tools')
assert.equal(current.value, 'tools')
extension.entryVisibility.value = { ready: true, entries: { tools: false } }
await nextTick()
assert.equal(current.value, 'chat', 'Policy change closes an open page')
;(globalThis as any).window.location.pathname = '/tools'
nav.handlePopState()
await nextTick()
assert.equal(current.value, 'chat', 'Back navigation cannot reopen a hidden page')
scope.stop()
console.log('Entry visibility navigation checks passed')
