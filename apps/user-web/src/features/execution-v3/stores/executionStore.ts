import { computed, markRaw, reactive } from 'vue'
import type { ArtifactItem, EvidenceBundleItem } from '../domain/delivery'
import type { ExecutionItemV3, ExecutionStateV3, V3ItemStatus } from '../domain/model'
import { isExecutionEventV3, type ExecutionEventV3 } from '../domain/protocol'
import { TERMINAL_RUN_EVENT_TYPES } from '../domain/runTiming'

function freshState(): ExecutionStateV3 {
  return {
    items: {}, order: [], artifacts: [], evidenceBundles: [], errors: [], intervention: null,
    rawEvents: [], seenEventIds: new Set<string>(), runStatus: 'idle',
    runStartedAt: null, runEndedAt: null, finalAnswerComplete: false,
  }
}

function statusFor(type: ExecutionEventV3['type']): V3ItemStatus {
  if (type === 'item.completed') return 'completed'
  if (type === 'item.failed') return 'failed'
  return 'running'
}

export function createExecutionStoreV3() {
  const state = reactive<ExecutionStateV3>(freshState())

  function applyEvent(event: ExecutionEventV3) {
    if (!isExecutionEventV3(event) || state.seenEventIds.has(event.event_id)) return
    state.seenEventIds.add(event.event_id)
    state.rawEvents.push(event)
    if (event.type === 'run.started') {
      state.runStatus = 'running'
      if (state.runStartedAt === null) state.runStartedAt = event.ts
      state.runEndedAt = null
    }
    if (event.type === 'run.completed') state.runStatus = 'completed'
    if (event.type === 'run.failed') state.runStatus = 'failed'
    if (event.type === 'run.cancelled') state.runStatus = 'cancelled'
    if (event.type === 'run.blocked') state.runStatus = 'blocked'
    if (TERMINAL_RUN_EVENT_TYPES.has(event.type)) state.runEndedAt = event.ts
    if (['run.completed', 'run.failed', 'run.cancelled'].includes(event.type)) {
      for (const id of state.order) {
        const item = state.items[id]
        if (item.status !== 'running') continue
        item.status = event.type === 'run.completed'
          ? 'completed'
          : event.type === 'run.cancelled' ? 'cancelled' : 'abandoned'
      }
    }
    if (!event.item_id || !event.item_kind) return

    const existing = state.items[event.item_id]
    const clearsIntervention = Boolean(
      existing
      && event.item_kind === 'browser_handoff'
      && event.type === 'item.completed'
      && event.payload?.cleared,
    )
    if (existing && event.revision <= existing.revision && !clearsIntervention) return
    const payload = { ...(existing?.payload || {}), ...(event.payload || {}) }
    if (event.type === 'item.delta') {
      payload.text = String(existing?.payload?.text || '') + String(event.payload?.text || '')
    }
    const nextStatus = statusFor(event.type)
    const terminalExisting = existing && ['completed', 'failed', 'cancelled', 'abandoned'].includes(existing.status)
    const item: ExecutionItemV3 = {
      id: event.item_id,
      kind: event.item_kind,
      parentId: event.parent_item_id || existing?.parentId,
      revision: clearsIntervention ? existing!.revision + 1 : event.revision,
      startedAt: existing?.startedAt || event.ts,
      updatedAt: event.ts,
      status: terminalExisting && nextStatus === 'running' ? existing.status : nextStatus,
      payload,
    }
    state.items[item.id] = item
    if (!existing) state.order.push(item.id)

    if (item.kind === 'final_answer' && event.type === 'item.completed') state.finalAnswerComplete = true
    if (item.kind === 'browser_handoff') {
      state.intervention = event.type === 'item.completed' ? null : payload
    }
    if (item.kind === 'error' && event.type === 'item.failed') {
      state.errors.push(String(payload.message || 'unknown error'))
    }
    if (item.kind === 'artifact' && event.type === 'item.completed') {
      const artifact: ArtifactItem = { id: item.id, ts: item.updatedAt, kind: String(payload.kind || 'document'), ...payload }
      if (!state.artifacts.some((a) => a.id === artifact.id || (artifact.object_path && a.object_path === artifact.object_path))) {
        state.artifacts.push(artifact)
      }
    }
    if (item.kind === 'evidence' && event.type === 'item.completed') {
      const bundle = { id: item.id, ts: item.updatedAt, ...payload } as EvidenceBundleItem
      if (!state.evidenceBundles.some((value) => value.id === bundle.id)) state.evidenceBundles.push(bundle)
    }
    if (item.kind === 'tool' && event.type === 'item.completed') {
      const browserIntervention = payload.browser_intervention as Record<string, any> | undefined
      if (browserIntervention?.suspension_id) state.intervention = browserIntervention
      const evidence = payload.evidence_bundle as EvidenceBundleItem | undefined
      if (evidence && !state.evidenceBundles.some((value) => value.id === evidence.id)) {
        state.evidenceBundles.push({ ts: item.updatedAt, ...evidence })
      }
      const artifacts = Array.isArray(payload.artifacts) ? payload.artifacts : []
      artifacts.forEach((value: Record<string, any>, index: number) => {
        const artifact: ArtifactItem = {
          id: String(value.id || value.object_path || `${item.id}:${index}`),
          ts: item.updatedAt,
          kind: String(value.kind || value.type || 'document'),
          ...value,
        }
        if (!state.artifacts.some((existing) => existing.id === artifact.id || (artifact.object_path && existing.object_path === artifact.object_path))) {
          state.artifacts.push(artifact)
        }
      })
    }
  }

  function loadHistory(events: any[] | undefined) {
    for (const event of events || []) if (isExecutionEventV3(event)) applyEvent(event)
    if (state.runStatus === 'running') {
      state.runStatus = 'failed'
      state.runEndedAt = Math.max(state.runStartedAt || 0, ...state.rawEvents.map((event) => Number(event.ts) || 0)) || null
      for (const id of state.order) if (state.items[id].status === 'running') state.items[id].status = 'abandoned'
    }
  }

  function resumeLive() {
    const hasTerminalEvent = state.rawEvents.some((event) => TERMINAL_RUN_EVENT_TYPES.has(event.type))
    if (hasTerminalEvent) return
    state.runStatus = 'running'
    state.runEndedAt = null
    for (const id of state.order) {
      const item = state.items[id]
      if (item.status !== 'abandoned') continue
      const latest = [...state.rawEvents].reverse().find((event) => event.item_id === id)
      if (latest && !['item.completed', 'item.failed'].includes(latest.type)) item.status = 'running'
    }
  }

  function reset() { Object.assign(state, freshState()) }

  const visibleItems = computed(() => state.order
    .map((id) => state.items[id])
    .filter((item) => item.kind !== 'final_answer' || Boolean(item.payload?.provisional)))
  // Execution stores are service objects containing refs and methods. They can
  // be attached to a deeply-reactive message, but the service boundary itself
  // must not be proxied or Vue will auto-unwrap visibleItems.
  return markRaw({ state, applyEvent, loadHistory, resumeLive, reset, visibleItems })
}

export type ExecutionStoreV3 = ReturnType<typeof createExecutionStoreV3>
