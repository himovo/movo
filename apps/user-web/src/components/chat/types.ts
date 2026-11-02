export type ChatDocumentKind = 'pdf' | 'docx' | 'ppt' | 'pptx' | 'md' | 'html' | 'xlsx' | 'presentation_preview_bundle'

export interface PendingDocument {
  file: File
  kind: ChatDocumentKind
}

export interface DocumentInfo {
  id?: string
  type: 'pdf' | 'doc' | 'docx' | 'xls' | 'xlsx' | 'ppt' | 'pptx' | 'md' | 'html' | 'presentation_preview_bundle' | 'generic'
  url: string
  filename?: string
  title?: string
  object_path?: string
  local_session_id?: string
  local_artifact_id?: string
  signed_url?: string
  content_type?: string
  size?: number
  bundle?: Record<string, any>
}
