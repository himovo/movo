import { computed, ref, shallowRef } from 'vue'
import { capabilities, createDshCodeSession, selectDshWorkspace } from '../../platform'
import type { DshCodeSession, DshWorkspace } from '../../platform/types'

/** Draft-only workspace choice; immutable only after the first local Session exists. */
export function useDshWorkspace() {
  const draftId = crypto.randomUUID()
  const selected = shallowRef<DshWorkspace | null>(null)
  const session = shallowRef<DshCodeSession | null>(null)
  const busy = ref(false)
  const locked = computed(() => session.value !== null)

  async function choose(modelId?: string) {
    if (locked.value) throw new Error('a started Code task cannot switch Workspace')
    if (!capabilities.localWorkspacePicker) throw new Error('local Workspace selection is unavailable')
    busy.value = true
    try {
      const value = await selectDshWorkspace(modelId)
      if (value) selected.value = value
      return value
    } finally { busy.value = false }
  }

  function clear() {
    if (locked.value) throw new Error('a started Code task cannot clear its Workspace')
    selected.value = null
  }

  async function solidify(title: string, modelId?: string, useWorktree = false) {
    if (session.value) return session.value
    if (!selected.value) return null
    if (selected.value.status !== 'ok') throw new Error('the selected Workspace directory is unavailable')
    busy.value = true
    try {
      session.value = await createDshCodeSession(selected.value.workspace_id, draftId, title, modelId, useWorktree)
      return session.value
    } finally { busy.value = false }
  }

  return { selected, session, busy, locked, choose, clear, solidify }
}
