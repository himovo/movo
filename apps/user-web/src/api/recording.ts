// Thin client for the recording start/stop/stream REST endpoints.
// Stream delivery uses a streaming fetch() + NDJSON parsing (one event
// per line) to match the backend's /browser/recording/stream route.

import { createApiClient } from './client'
import type { CompositeStep, Locator } from './compositeSkill'

const api = createApiClient({ baseURL: '/askai-api/api', timeout: 15000 })

export type RecordingTarget = {
  selector?: string
  role?: string
  name?: string
  aria_label?: string
  icon_class?: string
  text?: string
  ancestor_role?: string
  ancestor_contains_text?: string
  nth?: number
  semanticPurpose?: string
  scopeName?: string
  scopeRole?: string
  placeholder?: string
  type?: string
  accept?: string
}

export type RecordingEvent = {
  recording_id?: string
  sequence?: number
  type: 'click' | 'fill' | 'navigate' | 'select' | 'upload' | 'paste_image' | 'press' | 'unresolved_click' | 'recording_target_unavailable' | 'recording_started' | 'recording_stopped'
  url?: string
  value?: string
  value_redacted?: boolean
  key?: string
  target?: RecordingTarget
  before_tab_id?: string
  after_tab_id?: string
  instruction?: string
  at?: number
}

export type RecordingPreviewStep = {
  index: number
  tool: string
  target: string
  label: string
  parameterized: boolean
}

export type RecordingAnalysis = {
  display_name: string
  operation: string
  capability_id: string
  event_count: number
  action_count: number
  steps: RecordingPreviewStep[]
  complete: boolean
  reasons: string[]
}

export async function startRecording(user_id: string, url: string, session_id = 'default', operation = '') {
  const res = await api.post('/browser/recording/start', { user_id, url, session_id, operation })
  return { ok: !!res.data?.ok, recording_id: String(res.data?.recording_id || '') }
}

export async function stopRecording(user_id: string, session_id = 'default', recording_id = '') {
  const res = await api.post('/browser/recording/stop', { user_id, session_id, recording_id })
  return !!res.data?.ok
}

export async function saveRecordingToCache(payload: {
  user_id: string
  recording_id: string
  operation: string
  display_name: string
  capability_id: string
  main_id?: string
  included_sequences?: number[]
  variable_names?: Record<number, string>
}) {
  const res = await api.post('/browser/recording/cache', payload, { timeout: 60000 })
  return { ok: !!res.data?.ok, reason: String(res.data?.reason || '') }
}

export async function analyzeRecording(payload: {
  user_id: string
  recording_id: string
}) {
  const res = await api.post('/browser/recording/analyze', payload, { timeout: 60000 })
  return {
    ok: !!res.data?.ok,
    analysis: (res.data?.analysis || null) as RecordingAnalysis | null,
    reason: String(res.data?.reason || ''),
  }
}

export type StreamHandle = { close: () => void }

// Open an NDJSON stream of recording events. The returned handle lets
// the caller abort reading (e.g. when the modal is closed). Each event
// flows to onEvent as it arrives.
export function streamRecording(
  user_id: string,
  onEvent: (ev: RecordingEvent) => void,
  onError?: (err: unknown) => void,
): StreamHandle {
  const ctrl = new AbortController()
  ;(async () => {
    try {
      const resp = await fetch(
        `/askai-api/api/browser/recording/stream?user_id=${encodeURIComponent(user_id)}`,
        { signal: ctrl.signal, headers: { 'Accept': 'application/x-ndjson' } },
      )
      if (!resp.body) return
      const reader = resp.body.getReader()
      const dec = new TextDecoder()
      let buf = ''
      while (true) {
        const { value, done } = await reader.read()
        if (done) break
        buf += dec.decode(value, { stream: true })
        const parts = buf.split('\n')
        buf = parts.pop() || ''
        for (const line of parts) {
          const s = line.trim()
          if (!s) continue
          try { onEvent(JSON.parse(s)) } catch { /* skip malformed */ }
        }
      }
    } catch (e) {
      if ((e as any)?.name !== 'AbortError') onError?.(e)
    }
  })()
  return { close: () => ctrl.abort() }
}

// Convert recording events into draft steps client-side. Mirrors the
// Python ``trajectory_distiller.distill_trajectory`` so the preview
// shown in the panel matches what the backend will persist.
export function eventsToSteps(
  events: RecordingEvent[],
  site_profile_id = '',
): CompositeStep[] {
  const out: CompositeStep[] = []
  for (const ev of events) {
    if (!['click', 'fill', 'navigate', 'select'].includes(ev.type)) continue
    const targetObj = ev.target || {}
    const name = targetObj.name || targetObj.text || targetObj.aria_label || ''
    let instruction = ''
    if (ev.type === 'click') {
      instruction = name ? `点击 ${name}` : '点击目标控件'
    } else if (ev.type === 'fill') {
      const val = ev.value || ''
      const preview = val.length <= 40 ? val : val.slice(0, 40) + '…'
      instruction = val
        ? `在 ${name || '输入框'} 输入 ${preview}`
        : `聚焦 ${name || '输入框'}`
    } else if (ev.type === 'navigate') {
      instruction = `打开 ${ev.url || '页面'}`
    } else if (ev.type === 'select') {
      instruction = name ? `选择 ${name}` : '选择下拉项'
    }

    const loc: Locator = {}
    for (const k of ['role', 'name', 'aria_label', 'icon_class', 'text', 'ancestor_role', 'ancestor_contains_text'] as const) {
      const v = (targetObj as any)[k]
      if (v) (loc as any)[k] = v
    }
    const step: CompositeStep = { kind: 'browser', instruction }
    if (site_profile_id) step.site_profile_id = site_profile_id
    if (Object.keys(loc).length) step.locators = { primary: loc }
    out.push(step)
  }
  return out
}

export async function saveSkillFromRecording(payload: {
  user_id: string
  name: string
  description?: string
  triggers?: string[]
  site_profile_id?: string
  events: RecordingEvent[]
  edits?: Array<Record<string, any>>
  variables?: Record<string, string>
  visibility?: string
  is_active?: boolean
}) {
  const res = await api.post('/skills/from_recording', payload, { timeout: 60000 })
  return res.data?.data
}
