import type { ArtifactItem, EvidenceBundleItem } from './delivery'
import type { V3ItemKind } from './protocol'

export type V3ItemStatus = 'running' | 'completed' | 'failed' | 'cancelled' | 'blocked' | 'abandoned'

export interface ExecutionItemV3 {
  id: string
  kind: V3ItemKind
  parentId?: string
  revision: number
  startedAt: number
  updatedAt: number
  status: V3ItemStatus
  payload: Record<string, any>
}

export interface ExecutionStateV3 {
  items: Record<string, ExecutionItemV3>
  order: string[]
  artifacts: ArtifactItem[]
  evidenceBundles: EvidenceBundleItem[]
  errors: string[]
  intervention: Record<string, any> | null
  rawEvents: any[]
  seenEventIds: Set<string>
  runStatus: 'idle' | 'running' | 'completed' | 'failed' | 'cancelled' | 'blocked'
  runStartedAt: number | null
  runEndedAt: number | null
  finalAnswerComplete: boolean
}
