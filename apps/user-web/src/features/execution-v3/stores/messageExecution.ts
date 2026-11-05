import type { ArtifactItem, EvidenceBundleItem } from '../domain/delivery'
import { isExecutionEventV3, type ExecutionEventV3 } from '../domain/protocol'
import { createExecutionStoreV3, type ExecutionStoreV3 } from './executionStore'

type PersistedDocument = Partial<ArtifactItem> & { type?: string }

export interface ExecutionMessageV3 {
  _execV3?: ExecutionStoreV3
  execution_events?: unknown[]
  documents?: PersistedDocument[]
  evidence_bundles?: EvidenceBundleItem[]
  evidenceBundles?: EvidenceBundleItem[]
}

function completedItem(
  itemKind: 'artifact' | 'evidence',
  itemId: string,
  payload: Record<string, unknown>,
): ExecutionEventV3 {
  return {
    v: 3,
    event_id: `history_seed_${itemId}`,
    id: `history_seed_${itemId}`,
    ts: Date.now(),
    type: 'item.completed',
    item_kind: itemKind,
    item_id: itemId,
    revision: 1,
    payload,
  }
}

/**
 * Single attachment boundary for V3 execution state.
 * Session APIs return V3 events, while document/evidence fields remain a
 * fallback for older records whose event log did not persist those cards.
 */
export function ensureMessageExecutionV3(message: ExecutionMessageV3): ExecutionStoreV3 {
  if (message._execV3) return message._execV3

  const store = createExecutionStoreV3()
  store.loadHistory(message.execution_events)
  seedDocuments(store, message.documents)

  if (!store.state.evidenceBundles.length) {
    const bundles = message.evidence_bundles || message.evidenceBundles || []
    bundles.forEach((bundle, index) => {
      const identity = String(bundle.id || index)
      store.applyEvent(completedItem('evidence', `evidence_${identity}`, { ...bundle }))
    })
  }

  message._execV3 = store
  return store
}

/** Reconcile durable events into an already-live store after a session snapshot replaces its message row. */
export function reconcileMessageExecutionSnapshot(message: ExecutionMessageV3): void {
  const store = message._execV3
  if (!store) return
  for (const event of message.execution_events || []) {
    if (isExecutionEventV3(event)) store.applyEvent(event)
  }
  seedDocuments(store, message.documents)
}

function seedDocuments(store: ExecutionStoreV3, documents: PersistedDocument[] | undefined): void {
  const rows = documents || []
  const hasRenderedDocument = store.state.artifacts.length > 0 || rows.some((document) => document.type !== 'md')
  const visibleDocuments = hasRenderedDocument ? rows.filter((document) => document.type !== 'md') : rows
  visibleDocuments.forEach((document, index) => {
    if (document.object_path && store.state.artifacts.some((artifact) => artifact.object_path === document.object_path)) return
    const identity = String(document.id || document.object_path || document.filename || index)
    store.applyEvent(completedItem('artifact', `artifact_${identity}`, {
      ...document,
      kind: document.kind || document.type || 'document',
    }))
  })
}
