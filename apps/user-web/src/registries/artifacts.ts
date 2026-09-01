// Artifact registry. Drives the "deliverable card" rendering & actions.

import type { ArtifactDescriptor } from './types'
import { resolveArtifactKind, type ArtifactIdentity } from '../features/execution-v3/domain/artifactKind'

// Resolve project-local icon assets once (bundled by Vite).
const I = (name: string) =>
  new URL(`../statics/images/${name}`, import.meta.url).href

const ICON_PDF  = I('pdf-file-format.png')
const ICON_DOCX = I('docx-file.png')
const ICON_PPT  = I('ppt.png')
const ICON_MD   = I('md.png')
const ICON_HTML = I('html.png')
const ICON_XLSX = I('excel-48.png')
const ICON_GENERIC = I('attachment.svg')

export const DEFAULT_ARTIFACT: ArtifactDescriptor = {
  icon: ICON_GENERIC, labelKey: 'artifact.generic', actions: ['download'],
}

const REGISTRY: Record<string, ArtifactDescriptor> = {}

export function registerArtifact(kind: string, d: ArtifactDescriptor): void {
  REGISTRY[kind] = d
}

export function resolveArtifact(kind: string): ArtifactDescriptor {
  return REGISTRY[kind] || DEFAULT_ARTIFACT
}

export function resolveArtifactPresentation(artifact: ArtifactIdentity): ArtifactDescriptor {
  return resolveArtifact(resolveArtifactKind(artifact))
}

export function resolveArtifactIcon(type: string): string {
  return resolveArtifactPresentation({ type }).icon
}

// ---- Built-in registrations ----
registerArtifact('pdf',  { icon: ICON_PDF,  labelKey: 'artifact.pdf',  actions: ['preview', 'download'] })
registerArtifact('docx', { icon: ICON_DOCX, labelKey: 'artifact.docx', actions: ['edit', 'download'] })
registerArtifact('doc',  { icon: ICON_DOCX, labelKey: 'artifact.docx', actions: ['edit', 'download'] })
registerArtifact('xlsx', { icon: ICON_XLSX, labelKey: 'artifact.xlsx', actions: ['download'] })
registerArtifact('xls',  { icon: ICON_XLSX, labelKey: 'artifact.xlsx', actions: ['download'] })
registerArtifact('pptx', { icon: ICON_PPT,  labelKey: 'artifact.pptx', actions: ['edit', 'preview', 'export', 'download'] })
registerArtifact('ppt',  { icon: ICON_PPT,  labelKey: 'artifact.pptx', actions: ['edit', 'preview', 'export', 'download'] })
registerArtifact('presentation_preview_bundle',
                          { icon: ICON_PPT,  labelKey: 'artifact.pptx', actions: ['edit', 'preview', 'export'] })
registerArtifact('md',   { icon: ICON_MD,   labelKey: 'artifact.md',   actions: ['copy', 'download'] })
registerArtifact('html', { icon: ICON_HTML, labelKey: 'artifact.html', actions: ['preview', 'download'] })
registerArtifact('email_draft',
                          { icon: ICON_GENERIC, labelKey: 'artifact.email', actions: ['edit'] })
registerArtifact('code_diff',
                          { icon: ICON_GENERIC, labelKey: 'artifact.code', actions: ['preview'] })
