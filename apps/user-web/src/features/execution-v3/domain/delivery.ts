export interface ArtifactItem {
  id: string
  ts: number
  kind: string
  url?: string
  signed_url?: string
  object_path?: string
  filename?: string
  title?: string
  content_type?: string
  size?: number
  bundle?: Record<string, any>
}

export interface EvidenceSourceItem {
  id: string
  title: string
  source_name?: string
  source_url?: string
  snippet: string
  content?: string
  content_format?: 'json' | 'text' | string
  source_type: 'web' | 'kb' | 'document' | 'internal' | string
  citation_id?: string
  document_id?: string
  chunk_id?: string
  page_no?: number | string | null
  content_type?: string
  source_chunk_ids?: string[]
  source_anchor?: Record<string, any>
}

export interface EvidenceBundleItem {
  id: string
  ts: number
  summary: string
  sources: EvidenceSourceItem[]
  confirmed_facts: string[]
  open_questions: string[]
}
