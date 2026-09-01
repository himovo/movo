import type { ExecutionEventV3 } from '../../features/execution-v3/domain/protocol'
import type { BrowserAssistanceHandoff } from './useBrowserWorkspace'

export type ProjectedBrowserIntervention = {
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

export type BrowserInterventionTransition =
  | { kind: 'unchanged' }
  | { kind: 'cleared' }
  | { kind: 'activated'; intervention: ProjectedBrowserIntervention }

/**
 * Stable UI adapter for browser suspensions.
 *
 * New MOVO projections use a dedicated browser_handoff item.  The nested
 * tool payload remains accepted as a replay fallback for turns written before
 * the canonical side-band event was introduced.
 */
export function browserInterventionTransition(
  event: ExecutionEventV3,
): BrowserInterventionTransition {
  if (event.item_kind === 'browser_handoff') {
    if (event.type === 'item.completed' && event.payload?.cleared) {
      return { kind: 'cleared' }
    }
    return activate(event.payload)
  }
  if (event.item_kind === 'tool' && event.type === 'item.completed') {
    return activate(event.payload?.browser_intervention)
  }
  return { kind: 'unchanged' }
}

export function normalizeBrowserIntervention(
  value: unknown,
): ProjectedBrowserIntervention | null {
  if (!value || typeof value !== 'object') return null
  const source = value as Record<string, any>
  const suspensionId = String(source.suspension_id || '').trim()
  if (!suspensionId) return null
  return {
    ...source,
    suspension_id: suspensionId,
    reason: String(source.reason || ''),
    category: String(source.category || 'browser'),
    resumable: Boolean(source.resumable),
    handoff: source.handoff && typeof source.handoff === 'object'
      ? source.handoff as BrowserAssistanceHandoff
      : undefined,
  }
}

function activate(value: unknown): BrowserInterventionTransition {
  const intervention = normalizeBrowserIntervention(value)
  return intervention
    ? { kind: 'activated', intervention }
    : { kind: 'unchanged' }
}
