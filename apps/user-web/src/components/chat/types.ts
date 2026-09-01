export type ChatDocumentKind = 'pdf' | 'docx' | 'ppt' | 'pptx' | 'md' | 'html' | 'xlsx' | 'presentation_preview_bundle'

export interface PendingDocument {
  file: File
  kind: ChatDocumentKind
}
