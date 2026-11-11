import type { ArtifactItem } from '../../features/execution-v3/domain/delivery'
import { visibleAnswerArtifacts } from '../../features/execution-v3/domain/artifactVisibility'
import { ensureMessageExecutionV3 } from '../../features/execution-v3/stores/messageExecution'
import { artifactToDocumentInfo } from './documentArtifacts'
import { openDshPresentedFile } from '../../platform'
import type { ChatMessage } from './chatMessage'

export function useChatArtifactActions(options: {
  downloadDocument: (document: ReturnType<typeof artifactToDocumentInfo>) => unknown
  openDocumentEditor: (document: ReturnType<typeof artifactToDocumentInfo>, message: ChatMessage, index: number) => unknown
  openPresentationEditor: (document: ReturnType<typeof artifactToDocumentInfo>, message: ChatMessage) => unknown
  confirmPresentationPreview: (document: ReturnType<typeof artifactToDocumentInfo>, message: ChatMessage) => unknown
  openHtmlPreview: (document: ReturnType<typeof artifactToDocumentInfo>) => unknown
  openFilePreview: (document: ReturnType<typeof artifactToDocumentInfo>) => unknown
}) {
  function visibleMessageArtifacts(message: ChatMessage): ArtifactItem[] {
    const state = ensureMessageExecutionV3(message).state
    return visibleAnswerArtifacts(state.artifacts, state.runStatus)
  }

  function onArtifactOpen(artifact: ArtifactItem, message: ChatMessage, index: number) {
    const document = artifactToDocumentInfo(artifact)
    if (document.object_path && ['pdf', 'doc', 'docx', 'xls', 'xlsx', 'xlsm', 'html'].includes(document.type)) {
      return options.openFilePreview(document)
    }
    if (document.local_artifact_id) return options.openDocumentEditor(document, message, index)
    if (['pdf', 'doc', 'docx', 'xls', 'xlsx', 'xlsm'].includes(document.type)) return options.downloadDocument(document)
    if (document.type === 'ppt' || document.type === 'pptx') {
      return document.bundle?.preview_metadata?.blueprint_artifact_path || document.bundle?.deck_ir_artifact?.object_path
        ? options.openPresentationEditor(document, message)
        : options.downloadDocument(document)
    }
    return options.openDocumentEditor(document, message, index)
  }
  function onArtifactEditPresentation(artifact: ArtifactItem, message: ChatMessage) {
    const document = artifactToDocumentInfo(artifact)
    if (['pdf', 'doc', 'docx', 'xls', 'xlsx', 'xlsm'].includes(document.type)) {
      return options.openFilePreview(document)
    }
    if (document.local_artifact_id) return options.openDocumentEditor(document, message, -1)
    if (document.type === 'docx') return options.openDocumentEditor(document, message, -1)
    return options.openPresentationEditor(document, message)
  }
  function onArtifactExportPresentation(artifact: ArtifactItem, message: ChatMessage) {
    if (artifact.local_artifact_id) return options.downloadDocument(artifactToDocumentInfo(artifact))
    return options.confirmPresentationPreview(artifactToDocumentInfo(artifact), message)
  }
  function onArtifactPreviewHtml(artifact: ArtifactItem) {
    const document = artifactToDocumentInfo(artifact)
    if (document.object_path && ['pdf', 'doc', 'docx', 'xls', 'xlsx', 'xlsm', 'html'].includes(document.type)) {
      return options.openFilePreview(document)
    }
    if (artifact.local_artifact_id && artifact.local_session_id) return openDshPresentedFile(artifact.local_session_id, artifact.local_artifact_id)
    return options.openFilePreview(document)
  }
  function onArtifactDownload(artifact: ArtifactItem) {
    return options.downloadDocument(artifactToDocumentInfo(artifact))
  }
  function downloadMessageArtifact(message: ChatMessage, objectPath: string) {
    const artifact = visibleMessageArtifacts(message).find(item => item.object_path === objectPath)
    if (artifact) return onArtifactDownload(artifact)
  }

  return {
    visibleMessageArtifacts, onArtifactOpen, onArtifactEditPresentation,
    onArtifactExportPresentation, onArtifactPreviewHtml, onArtifactDownload,
    downloadMessageArtifact,
  }
}
