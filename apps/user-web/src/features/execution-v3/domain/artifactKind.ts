export interface ArtifactIdentity {
  kind?: string
  type?: string
  filename?: string
  title?: string
  object_path?: string
  url?: string
  signed_url?: string
  content_type?: string
}

const SUPPORTED_KINDS = new Set([
  'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'md', 'html',
  'presentation_preview_bundle', 'email_draft', 'code_diff',
])

// These are business artifact identities, not file formats. Their persisted
// payload may point at an HTML preview, but the card must retain the declared
// product type so the correct editor/export actions remain available.
const SEMANTIC_KINDS = new Set([
  'presentation_preview_bundle', 'email_draft', 'code_diff',
])

const MIME_KINDS: Record<string, string> = {
  'application/pdf': 'pdf',
  'application/msword': 'doc',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx',
  'application/vnd.ms-excel': 'xls',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'xlsx',
  'application/vnd.ms-powerpoint': 'ppt',
  'application/vnd.openxmlformats-officedocument.presentationml.presentation': 'pptx',
  'text/markdown': 'md',
  'text/html': 'html',
}

function normalizedExtension(value: unknown): string {
  const clean = String(value || '').split(/[?#]/, 1)[0].replace(/\\/g, '/')
  const basename = clean.slice(clean.lastIndexOf('/') + 1)
  const dot = basename.lastIndexOf('.')
  return dot > 0 ? basename.slice(dot + 1).toLowerCase() : ''
}

/** Resolve a deliverable type from stable file metadata, not a generic event kind. */
export function resolveArtifactKind(artifact: ArtifactIdentity): string {
  for (const value of [artifact.type, artifact.kind]) {
    const kind = String(value || '').trim().toLowerCase()
    if (SEMANTIC_KINDS.has(kind)) return kind
  }
  for (const value of [artifact.filename, artifact.object_path, artifact.url, artifact.signed_url, artifact.title]) {
    const extension = normalizedExtension(value)
    if (SUPPORTED_KINDS.has(extension)) return extension
  }
  const mime = String(artifact.content_type || '').split(';', 1)[0].trim().toLowerCase()
  if (MIME_KINDS[mime]) return MIME_KINDS[mime]
  for (const value of [artifact.kind, artifact.type]) {
    const kind = String(value || '').trim().toLowerCase()
    if (SUPPORTED_KINDS.has(kind)) return kind
  }
  return 'generic'
}
