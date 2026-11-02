import type { ArtifactItem } from '../../features/execution-v3/domain/delivery'
import { resolveArtifactKind } from '../../features/execution-v3/domain/artifactKind'
import { ensureMessageExecutionV3, type ExecutionMessageV3 } from '../../features/execution-v3/stores/messageExecution'
import type { DocumentInfo } from './types'

type DocumentMessage = Omit<ExecutionMessageV3, 'documents'> & { documents?: DocumentInfo[] }

export function artifactToDocumentInfo(a: ArtifactItem): DocumentInfo {
  return {
    id: a.id,
    type: resolveArtifactKind(a) as DocumentInfo['type'],
    url: a.url || '',
    signed_url: a.signed_url,
    object_path: a.object_path,
    local_session_id: a.local_session_id,
    local_artifact_id: a.local_artifact_id,
    filename: a.filename,
    title: a.title,
    content_type: a.content_type,
    size: a.size,
    bundle: a.bundle,
  }
}

export function normalizeDocumentType(type?: string): DocumentInfo['type'] {
  return (type === 'markdown' ? 'md' : type || 'generic') as DocumentInfo['type']
}

function documentToArtifact(doc: DocumentInfo): ArtifactItem {
  return {
    id: doc.id || doc.object_path || doc.url || `${doc.type}_${Date.now()}`,
    ts: Date.now(),
    kind: doc.type,
    url: doc.url,
    signed_url: doc.signed_url,
    object_path: doc.object_path,
    local_session_id: doc.local_session_id,
    local_artifact_id: doc.local_artifact_id,
    filename: doc.filename,
    title: doc.title,
    content_type: doc.content_type,
    size: doc.size,
    bundle: doc.bundle,
  }
}

function sameDocumentIdentity(a: DocumentInfo, b?: DocumentInfo | null): boolean {
  if (!b) return false
  return (
    (!!a.id && a.id === b.id) ||
    (!!a.object_path && a.object_path === b.object_path) ||
    (!!a.url && a.url === b.url) ||
    (a.type === b.type && !!a.filename && a.filename === b.filename && a.title === b.title)
  )
}

function upsertMessageDocument(msg: DocumentMessage, previous: DocumentInfo | null, next: DocumentInfo) {
  if (!msg.documents) msg.documents = []
  const index = msg.documents.findIndex((doc) => sameDocumentIdentity(doc, previous) || sameDocumentIdentity(doc, next))
  if (index >= 0) {
    msg.documents[index] = { ...msg.documents[index], ...next }
  } else {
    msg.documents.push(next)
  }
}

function upsertExecutionArtifact(msg: DocumentMessage, previous: DocumentInfo | null, next: DocumentInfo) {
  const store = ensureMessageExecutionV3(msg)
  const nextArtifact = documentToArtifact(next)
  const index = store.state.artifacts.findIndex((artifact) => {
    const doc = artifactToDocumentInfo(artifact)
    return sameDocumentIdentity(doc, previous) || sameDocumentIdentity(doc, next)
  })
  if (index >= 0) {
    store.state.artifacts[index] = { ...store.state.artifacts[index], ...nextArtifact }
  } else {
    store.state.artifacts.push(nextArtifact)
  }
}

export function upsertDocumentEverywhere(msg: DocumentMessage, previous: DocumentInfo | null, next: DocumentInfo) {
  upsertMessageDocument(msg, previous, next)
  if (next.type !== 'md') {
    upsertExecutionArtifact(msg, previous, next)
  }
}

export function findMarkdownDocument(msg: DocumentMessage): DocumentInfo | null {
  const fromDocuments = (msg.documents || []).find((d) => d.type === 'md')
  if (fromDocuments) return fromDocuments
  const artifact = ensureMessageExecutionV3(msg).state.artifacts.find((a: ArtifactItem) => {
    const kind = String(a.kind || '').toLowerCase()
    return kind === 'md' || kind === 'markdown'
  })
  return artifact ? artifactToDocumentInfo(artifact) : null
}

export function toRenderableDocumentFormat(type: DocumentInfo['type']): 'pdf' | 'docx' | 'ppt' | 'pptx' | 'md' | null {
  if (type === 'pdf' || type === 'docx' || type === 'ppt' || type === 'pptx' || type === 'md') return type
  return null
}

export function getDisplayDocuments(docs?: DocumentInfo[]) {
  const list = docs || []
  const hasPreviewBundle = list.some((d) => d.type === 'presentation_preview_bundle')
  if (hasPreviewBundle) {
    return list.filter((d) => d.type === 'presentation_preview_bundle')
  }
  const hasNonMd = list.some((d) => d.type !== 'md')
  if (hasNonMd) {
    return list.filter((d) => d.type !== 'md')
  }
  return list
}
