import { onBeforeUnmount, ref } from 'vue'
import { fetchChatFilePreviewText, prepareChatFilePreview, prepareDraftFilePreview, type ChatFilePreviewState } from '../../api/chatFilePreviews'
import { uploadChatDocument } from '../../api/chat'
import { readDshPresentedText } from '../../platform'
import type { DocumentInfo, PendingDocument } from './types'

export function useChatFilePreview(getSessionId: () => string | undefined, getUserId: () => string | undefined, getToken: () => string | undefined) {
  const open = ref(false)
  const document = ref<DocumentInfo | null>(null)
  const state = ref<ChatFilePreviewState | null>(null)
  const text = ref('')
  const busy = ref(false)
  const error = ref('')
  const pending = ref<PendingDocument | null>(null)
  let generation = 0
  let timer: ReturnType<typeof setTimeout> | null = null
  let localUrl: string | null = null

  function stopTimer() {
    if (timer) clearTimeout(timer)
    timer = null
  }

  async function refresh(retry = false) {
    const selected = document.value
    const draft = pending.value
    const sessionId = getSessionId()
    const current = ++generation
    stopTimer()
    if (!selected || (!draft && !(selected.local_session_id && selected.local_artifact_id) && (!selected.object_path || !sessionId))) {
      error.value = 'unavailable'
      return
    }
    busy.value = true
    error.value = ''
    try {
      if (selected.local_session_id && selected.local_artifact_id) {
        const result = await readDshPresentedText(selected.local_session_id, selected.local_artifact_id)
        if (current !== generation) return
        text.value = result.text
        state.value = { kind: 'code', status: 'ready', filename: result.filename }
        return
      }
      if (draft) {
        const name = draft.file.name.toLowerCase()
        if (name.endsWith('.pdf')) {
          if (current !== generation) return
          localUrl = URL.createObjectURL(draft.file)
          state.value = { kind: 'pdf', status: 'ready', filename: draft.file.name, url: localUrl }
          return
        }
        if (['.txt', '.md', '.csv', '.tsv'].some(ext => name.endsWith(ext))) {
          if (draft.file.size > 5 * 1024 * 1024) throw new Error('Text preview is too large')
          text.value = await draft.file.text()
          if (current !== generation) return
          state.value = { kind: 'text', status: 'ready', filename: draft.file.name }
          return
        }
        if (!draft.uploadPromise && !draft.uploaded) {
          draft.uploadPromise = uploadChatDocument(getUserId() || '', draft.file, getToken())
        }
        const uploaded = draft.uploaded || await draft.uploadPromise
        draft.uploaded = uploaded
        if (!uploaded.object_path) throw new Error('Upload did not return a file path')
        const result = await prepareDraftFilePreview(uploaded.object_path, retry)
        if (current !== generation) return
        state.value = result
        if (result.status === 'queued') timer = setTimeout(() => void refresh(), 1600)
        return
      }
      const result = await prepareChatFilePreview(sessionId!, selected.object_path!, retry)
      if (current !== generation) return
      state.value = result
      if (result.status === 'ready' && (result.kind === 'text' || result.kind === 'code' || result.kind === 'html') && result.url) {
        text.value = await fetchChatFilePreviewText(result.url)
      }
      if (result.status === 'queued') timer = setTimeout(() => void refresh(), 1600)
    } catch (cause) {
      if (draft && !draft.uploaded) draft.uploadPromise = undefined
      if (current === generation) error.value = cause instanceof Error ? cause.message : String(cause)
    } finally {
      if (current === generation) busy.value = false
    }
  }

  function show(selected: DocumentInfo) {
    close()
    pending.value = null
    document.value = selected
    state.value = null
    text.value = ''
    open.value = true
    void refresh()
  }

  function showPending(item: PendingDocument) {
    close()
    pending.value = item
    document.value = { type: item.kind, url: '', filename: item.file.name, title: item.file.name }
    open.value = true
    void refresh()
  }

  function downloadPending() {
    const file = pending.value?.file
    if (!file) return
    const url = URL.createObjectURL(file)
    const link = window.document.createElement('a')
    link.href = url
    link.download = file.name
    link.click()
    window.setTimeout(() => URL.revokeObjectURL(url), 1000)
  }

  function close() {
    open.value = false
    document.value = null
    state.value = null
    pending.value = null
    generation += 1
    stopTimer()
    if (localUrl) URL.revokeObjectURL(localUrl)
    localUrl = null
  }

  onBeforeUnmount(stopTimer)
  return { open, document, state, text, busy, error, pending, show, showPending, close, refresh, downloadPending }
}
