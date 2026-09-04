import assert from 'node:assert/strict'
import { ref } from 'vue'
import { useDesktopToolTabs } from '../src/composables/desktop/useDesktopToolTabs'

const scope = ref('chat-a')
const workspace = useDesktopToolTabs({
  getScopeKey: () => scope.value,
  getLocale: () => 'zh',
  isAvailable: () => true,
})

workspace.open('terminal')
workspace.open('terminal')
assert.deepEqual(workspace.tabs.value.map(tab => tab.title), ['终端 1', '终端 2'])
assert.equal(workspace.activeKind.value, 'terminal')

workspace.openFile('src/App.vue')
workspace.openFile('src/App.vue')
assert.equal(workspace.tabs.value.filter(tab => tab.kind === 'file').length, 1, 'same file reuses its tab')

workspace.openDiff('src/App.vue')
workspace.openDiff('src/App.vue', { task_id: 'task-1', session_id: 'session-a', created_at: 0, files: [], additions: 0, deletions: 0, undo_available: false, undone: false })
assert.equal(workspace.tabs.value.filter(tab => tab.kind === 'diff').length, 2, 'workspace and task diffs remain independent')

const chatATabs = workspace.tabs.value
scope.value = 'chat-b'
assert.equal(workspace.tabs.value.length, 0, 'a new conversation starts with an empty workspace')
workspace.open('files')
assert.equal(workspace.tabs.value[0].kind, 'files')

scope.value = 'chat-a'
assert.equal(workspace.tabs.value.length, chatATabs.length, 'switching back restores the conversation workspace')
const firstTerminal = workspace.tabs.value.find(tab => tab.title === '终端 1')!
workspace.close(firstTerminal.id)
assert.equal(workspace.tabs.value.some(tab => tab.id === firstTerminal.id), false)

console.log('desktop tool tabs tests passed')
