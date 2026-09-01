import { ref, watch } from 'vue'
import { selectEmbeddedBrowserSession, setEmbeddedBrowserOwner } from '../../platform'
import { notifyBrowserAgentReturned } from './browserAgentReturn'

export interface BrowserIntervention {
  reason: string
  category: string
  url?: string
  domain?: string
  screenshot?: string
  suspension_id?: string
  run_id?: string
  node_id?: string
  browser_session_id?: string
  tab_id?: string
  resumable?: boolean
  handoff?: BrowserAssistanceHandoff
}

export interface BrowserAssistanceContract {
  schema_version: string
  contract_id: string
  kind: 'form_fill' | 'form_media' | 'form_commit' | 'form_effect_verify' | 'form_task_completion' | string
  action: string
  payload: Record<string, unknown>
  replay_policy: string
  allowed_outcomes: string[]
}

export interface MediaUploadHandoff {
  schema_version: string
  contract?: BrowserAssistanceContract
  article: { title: string; body: string }
  images: Array<{
    candidate_id: string
    source_index: number
    filename: string
    url: string
    signed_url?: string
    download_url: string
    anchor?: Record<string, unknown>
    _oss_object_path?: string
  }>
  pending_candidate_ids: string[]
}

export type BrowserAssistanceHandoff = Partial<MediaUploadHandoff> & {
  schema_version?: string
  contract?: BrowserAssistanceContract
}

interface BrowserWorkspaceOptions {
  getUserId: () => string | undefined
  getSessionId: () => string | null | undefined
  getIntervention: () => BrowserIntervention | null | undefined
  onClearIntervention: () => void
}

export function useBrowserWorkspace(options: BrowserWorkspaceOptions) {
  const activeIntervention = ref<BrowserIntervention | null>(null)
  const isPreviewExpanded = ref(false)

  watch(options.getIntervention, (value) => { activeIntervention.value = value ? { ...value } : null }, { immediate: true, deep: true })

  function openForIntervention() {
    const intervention = activeIntervention.value
    const domain = intervention?.domain || ''
    const url = intervention?.url || ''
    if (!domain && !url) return
    const purpose = intervention?.category.toLowerCase() === 'login' ? 'login' : 'user_interaction'
    void browserCommand('/askai-api/api/browser/show', { domain, url, purpose })
    isPreviewExpanded.value = true
  }

  function clearIntervention() {
    activeIntervention.value = null
    options.onClearIntervention()
  }

  async function completeLocalIntervention(signal: import('./browserAgentReturn').BrowserAgentReturnSignal = {}) {
    const intervention = activeIntervention.value
    if (!intervention?.resumable || !intervention.suspension_id) {
      clearIntervention()
      return
    }
    const sessionId = String(options.getSessionId() || '').trim()
    if (sessionId) {
      await selectEmbeddedBrowserSession(sessionId).catch((error) => {
        console.warn('[browser-workspace] session selection failed', { sessionId, error })
      })
    }
    await setEmbeddedBrowserOwner('agent').catch((error) => {
      console.warn('[browser-workspace] owner handoff failed', { error })
    })
    if (sessionId) notifyBrowserAgentReturned(sessionId, signal)
  }

  function reset() {
    activeIntervention.value = null
    isPreviewExpanded.value = false
  }

  async function browserCommand(path: string, payload: Record<string, unknown>) {
    try {
      await fetch(path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: options.getUserId() || 'anonymous', ...payload }),
      })
    } catch (error) {
      console.warn('[browser-workspace] command failed', { path, error })
    }
  }

  return {
    activeIntervention,
    isPreviewExpanded,
    openForIntervention,
    completeLocalIntervention,
    reset,
  }
}
