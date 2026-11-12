import { ref, type ComputedRef } from 'vue'
import { useMessage } from 'naive-ui'
import { renderDocument, renderPresentationPptx, signDocument, fetchDocxEditSource } from '../../api/documents'
import { authenticatedJsonHeaders } from '../../api/authHeaders'
import { downloadResourceUrl, openPreviewResource, saveBlobDownload } from '../../utils/desktopResources'
import { t } from '../../composables/i18n'
import { openDshPresentedFile, saveDshPresentedFile } from '../../platform'
import type { ExecutionMessageV3 } from '../../features/execution-v3/stores/messageExecution'
import { findMarkdownDocument, normalizeDocumentType, toRenderableDocumentFormat, upsertDocumentEverywhere } from './documentArtifacts'
import type { DocumentInfo } from './types'

type DocumentMessage = Omit<ExecutionMessageV3, 'documents'> & {
  _id?: string
  role: 'user' | 'assistant'
  content: string
  documents?: DocumentInfo[]
}

export function useDocumentEditors<T extends DocumentMessage>(options: {
  messages: ComputedRef<T[]>
  getUserId: () => string | undefined
  debugEnabled: boolean
}) {
  const { messages, getUserId, debugEnabled } = options
  const activeDocument = ref<DocumentInfo | null>(null)
  const documentEditorOpen = ref(false)
  const documentEditorContent = ref('')
  const documentEditorLoading = ref(false)
  const documentEditorStatus = ref<'success' | 'warning' | 'error' | ''>('')
  const documentEditorMessageIndex = ref<number | null>(null)
  const presentationEditorOpen = ref(false)
  const presentationBlueprint = ref<any>(null)
  const presentationBlueprintPath = ref('')
  const presentationEditorMsg = ref<T | null>(null)
  const editorMessage = useMessage()

  async function openDocumentEditor(doc: DocumentInfo, msg: T, _renderIndex: number) {
    if (doc.local_session_id && doc.local_artifact_id) {
      try {
        await openDshPresentedFile(doc.local_session_id, doc.local_artifact_id)
      } catch (error) {
        editorMessage.error(String(error))
      }
      return
    }
    if (doc.type === 'presentation_preview_bundle') {
      await openPresentationEditor(doc, msg)
      return
    }
    if (doc.type === 'html') {
      const targetUrl = await resolveDocumentOpenUrl(doc)
      if (targetUrl) {
        await openPreviewResource(targetUrl)
      }
      return
    }
    const msgIndex = messages.value.findIndex((m) => m._id === msg._id && m.role === msg.role)
    if (msgIndex < 0) return
    activeDocument.value = doc
    documentEditorContent.value = ''
    documentEditorStatus.value = ''
    const mdDoc = doc.type === 'md'
      ? doc
      : findMarkdownDocument(msg)
    if (mdDoc?.object_path) {
      try {
        if (debugEnabled) {
          console.log('[doc-editor] fetching markdown', mdDoc.object_path)
        }
        const resp = await fetch('/askai-api/api/documents/fetch', {
          method: 'POST',
          headers: authenticatedJsonHeaders(),
          body: JSON.stringify({
            user_id: getUserId() || 'anonymous',
            object_path: mdDoc.object_path,
          }),
        })
        if (debugEnabled) {
          console.log('[doc-editor] fetch status', resp.status)
        }
        if (resp.ok) {
          documentEditorContent.value = await resp.text()
          if (debugEnabled) {
            console.log('[doc-editor] markdown length', documentEditorContent.value.length)
          }
        }
      } catch {
        // ignore and fallback to message content
      }
    }
    if (!documentEditorContent.value && doc.type === 'docx' && doc.object_path) {
      try {
        documentEditorContent.value = await fetchDocxEditSource(getUserId() || 'anonymous', doc.object_path)
      } catch (error) {
        console.error('Failed to load DOCX edit source:', error)
        window.alert(t('chat.docx_edit_source_failed'))
        return
      }
    }
    if (!documentEditorContent.value && doc.type === 'docx') {
      window.alert(t('chat.docx_edit_source_empty'))
      return
    }
    if (!documentEditorContent.value) {
      documentEditorContent.value = msg.content || ''
    }
    if (documentEditorContent.value) {
      try {
        const renewResp = await fetch('/askai-api/api/documents/refresh-markdown-urls', {
          method: 'POST',
          headers: authenticatedJsonHeaders(),
          body: JSON.stringify({
            user_id: getUserId() || 'anonymous',
            content: documentEditorContent.value,
          }),
        })
        if (renewResp.ok) {
          documentEditorContent.value = await renewResp.text()
        }
      } catch {
        // ignore and keep original content
      }
    }
    documentEditorMessageIndex.value = msgIndex
    documentEditorOpen.value = true
  }

  function closeDocumentEditor() {
    documentEditorOpen.value = false
    activeDocument.value = null
    documentEditorMessageIndex.value = null
  }

  async function openPresentationEditor(doc: DocumentInfo, msg: T) {
    const blueprintPath = String(
      doc.bundle?.preview_metadata?.blueprint_artifact_path ||
      doc.bundle?.deck_ir_artifact?.object_path ||
      ''
    ).trim()
    if (!blueprintPath) {
      editorMessage.info(t('chat.presentation_edit_unavailable'))
      return
    }
    try {
      const resp = await fetch('/askai-api/api/documents/fetch', {
        method: 'POST',
        headers: authenticatedJsonHeaders(),
        body: JSON.stringify({
          user_id: getUserId() || 'anonymous',
          object_path: blueprintPath,
        }),
      })
      if (!resp.ok) throw new Error('fetch failed')
      const text = await resp.text()
      presentationBlueprint.value = JSON.parse(text)
      presentationBlueprintPath.value = blueprintPath
      presentationEditorMsg.value = msg
      presentationEditorOpen.value = true
    } catch (err) {
      console.error('Failed to load blueprint:', err)
      editorMessage.error(t('chat.presentation_edit_load_failed'))
    }
  }

  async function openHtmlPreview(doc: DocumentInfo) {
    const targetUrl = await resolveDocumentOpenUrl(doc)
    if (targetUrl) await openPreviewResource(targetUrl)
  }

  function closePresentationEditor() {
    presentationEditorOpen.value = false
    presentationBlueprint.value = null
    presentationBlueprintPath.value = ''
    presentationEditorMsg.value = null
  }

  function onPresentationExported(result: any) {
    if (!result || !presentationEditorMsg.value) return
    const msg = presentationEditorMsg.value
    if (!msg.documents) msg.documents = []
    const exists = msg.documents.some((item) =>
      (result.object_path && item.object_path === result.object_path) ||
      (result.url && item.url === result.url)
    )
    if (!exists) {
      msg.documents.push(result as DocumentInfo)
    }
  }

  function getDocumentObjectPath(doc: DocumentInfo): string {
    return String(
      doc.object_path ||
      doc.bundle?.html_preview?.object_path ||
      ''
    ).trim()
  }

  async function resolveDocumentOpenUrl(doc: DocumentInfo): Promise<string> {
    const objectPath = getDocumentObjectPath(doc)
    if (objectPath) {
      try {
        const result = await signDocument({
          user_id: getUserId() || 'anonymous',
          object_path: objectPath,
        })
        const signed = String(result?.url || '').trim()
        if (signed) {
          doc.signed_url = signed
          if (doc.type === 'presentation_preview_bundle' && doc.bundle?.html_preview) {
            doc.bundle.html_preview.url = signed
          }
          return signed
        }
      } catch {
        // fallback to existing url
      }
    }
    return String(doc.signed_url || doc.url || doc.bundle?.html_preview?.url || '').trim()
  }

  async function downloadDocument(doc: DocumentInfo) {
    if (doc.local_session_id && doc.local_artifact_id) {
      try {
        await saveDshPresentedFile(doc.local_session_id, doc.local_artifact_id)
      } catch (error) {
        editorMessage.error(String(error))
      }
      return
    }
    if (doc.type === 'presentation_preview_bundle') {
      const targetUrl = await resolveDocumentOpenUrl(doc)
      if (targetUrl) {
        await openPreviewResource(targetUrl)
      }
      return
    }
    if (!doc.url && !doc.object_path) return
    const filename = doc.filename || doc.title || 'document'
    if (doc.object_path) {
      try {
        const resp = await fetch('/askai-api/api/documents/fetch', {
          method: 'POST',
          headers: authenticatedJsonHeaders(),
          body: JSON.stringify({
            user_id: getUserId() || 'anonymous',
            object_path: doc.object_path,
          }),
        })
        if (resp.ok) {
          const blob = await resp.blob()
          await saveBlobDownload(blob, filename)
          return
        }
      } catch {
        // fallback to existing url
      }
    }
    if (doc.url) {
      await downloadResourceUrl(doc.url, filename)
    }
  }

  async function confirmPresentationPreview(doc: DocumentInfo, msg: T) {
    const blueprintPath = String(
      doc.bundle?.preview_metadata?.blueprint_artifact_path ||
      doc.bundle?.deck_ir_artifact?.object_path ||
      ''
    ).trim()

    let result: any = null
    if (blueprintPath) {
      result = await renderPresentationPptx({
        user_id: getUserId() || 'anonymous',
        blueprint_object_path: blueprintPath,
        filename: `${doc.title || 'presentation'}.pptx`,
        title: doc.title || 'PPT',
      })
    } else {
      // No blueprint available — nothing to render.
      return
    }

    if (!result) return
    if (!msg.documents) msg.documents = []
    const exists = msg.documents.some((item) =>
      (result.object_path && item.object_path === result.object_path) ||
      (result.url && item.url === result.url)
    )
    if (!exists) {
      msg.documents.push(result as DocumentInfo)
    }
  }

  async function regenerateDocument() {
    if (!activeDocument.value) return
    if (documentEditorMessageIndex.value === null) return
    const content = documentEditorContent.value.trim()
    if (!content) return
    documentEditorStatus.value = ''
    documentEditorLoading.value = true
    try {
      const previousDocument = { ...activeDocument.value }
      const msg = messages.value[documentEditorMessageIndex.value]
      if (!msg) return
      const renderFormat = toRenderableDocumentFormat(activeDocument.value.type)
      if (!renderFormat) return
      const previousMarkdown = activeDocument.value.type !== 'md' ? findMarkdownDocument(msg) : null
      const result = await renderDocument({
        user_id: getUserId() || 'anonymous',
        content,
        format: renderFormat,
        filename: activeDocument.value.filename,
        title: activeDocument.value.title,
      })
      if (!result?.object_path) throw new Error('document render returned no file')
      const nextDocument = {
        ...activeDocument.value,
        ...result,
        id: result.object_path,
        type: normalizeDocumentType(result.type || activeDocument.value.type),
        signed_url: result.url || '',
        url: result.url || '',
      } as DocumentInfo
      upsertDocumentEverywhere(msg, previousDocument, nextDocument)
      activeDocument.value = nextDocument
      documentEditorStatus.value = 'success'
      if (nextDocument.type !== 'md') {
        try {
          const markdownResult = await renderDocument({
            user_id: getUserId() || 'anonymous',
            content,
            format: 'md',
            filename: `${nextDocument.title || nextDocument.filename || 'document'}.md`,
            title: nextDocument.title,
          })
          if (!markdownResult?.object_path) throw new Error('markdown render failed')
          const nextMarkdown = {
            ...(previousMarkdown || {}),
            ...markdownResult,
            id: markdownResult.object_path || markdownResult.url || previousMarkdown?.id,
            type: 'md',
            signed_url: markdownResult.url || '',
            url: markdownResult.url || '',
          } as DocumentInfo
          upsertDocumentEverywhere(msg, previousMarkdown, nextMarkdown)
        } catch (error) {
          console.error('Failed to save Markdown edit source:', error)
          documentEditorStatus.value = 'warning'
          editorMessage.warning(t('chat.regenerate_source_warning'))
        }
      }
      if (documentEditorStatus.value === 'success') editorMessage.success(t('chat.regenerate_success'))
    } catch (error) {
      console.error('Failed to regenerate document:', error)
      documentEditorStatus.value = 'error'
      editorMessage.error(t('chat.regenerate_failed'))
    } finally {
      documentEditorLoading.value = false
    }
  }

  return {
    activeDocument, documentEditorOpen, documentEditorContent,
    documentEditorLoading, documentEditorStatus, presentationEditorOpen,
    presentationBlueprint, presentationBlueprintPath,
    openDocumentEditor, closeDocumentEditor, openPresentationEditor,
    openHtmlPreview, closePresentationEditor, onPresentationExported,
    downloadDocument, confirmPresentationPreview, regenerateDocument,
  }
}
