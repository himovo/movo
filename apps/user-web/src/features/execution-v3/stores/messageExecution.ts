import type { ArtifactItem, EvidenceBundleItem } from '../domain/delivery'
import type { ExecutionEventV3 } from '../domain/protocol'
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

  if (!store.state.artifacts.length) {
    const documents = message.documents || []
    const hasRenderedDocument = documents.some((document) => document.type !== 'md')
    const visibleDocuments = hasRenderedDocument
      ? documents.filter((document) => document.type !== 'md')
      : documents
    visibleDocuments.forEach((document, index) => {
      const identity = String(document.id || document.object_path || document.filename || index)
      store.applyEvent(completedItem('artifact', `artifact_${identity}`, {
        ...document,
        kind: document.kind || document.type || 'document',
      }))
    })
  }

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
