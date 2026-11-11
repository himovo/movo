import type { KnowledgeReference } from '../../api/knowledgeReferences'
import type { ExecutionStoreV3 } from '../../features/execution-v3/stores/executionStore'
import type { DshTaskChangeSet } from '../../platform/types'
import type { ChatMessageAuthor } from '../../api/sessions'
import type { QuestionAnswerEntry } from './questionAnswerHistory'
import type { DocumentInfo } from './types'

export interface ImageInfo {
  object_path?: string
  url?: string
  signed_url?: string
  filename?: string
  content_type?: string
  size?: number
}

export interface ChatMessage {
  knowledge_references?: KnowledgeReference[]
  role: 'user' | 'assistant'
  content: string
  _id?: string
  _execV3?: ExecutionStoreV3
  _connectionLostAt?: number
  /** Backend chat session id captured from streaming response header */
  _backendSid?: string
  /** Stable id for this assistant turn; used to bind persisted exec log */
  message_id?: string
  /** Message author (todo 28): present on session-GET messages, the viewer's
   *  own user_id on optimistic pushes. Absent (legacy/system) renders as today. */
  user_id?: string
  /** T5/T9: authoritative author projection (`{user_id, display_name,
   *  avatar_url} | null`) consumed verbatim when rendering shared rows. */
  author?: ChatMessageAuthor | null
  /** Persisted V3 events returned by GET /sessions/{id} for replay. */
  execution_events?: unknown[]
  question_answers?: QuestionAnswerEntry[]
  question_answer?: QuestionAnswerEntry
  trigger_source?: string
  scheduled_job_id?: string
  scheduled_run_id?: string
  created_at?: string
  _codeChanges?: DshTaskChangeSet
  evidence_bundles?: any[]
  evidenceBundles?: any[]
  documents?: DocumentInfo[]
  images?: ImageInfo[]
  // Legacy fields kept for compatibility with persisted messages but no
  // longer driven by the live stream.
  progress?: { content: string; timestamp?: string; kind?: string; url?: string }[]
  currentStatus?: string
  plan?: any
}
