import { nextTick, onBeforeUnmount, ref } from 'vue'
import type { ChatDocumentKind, PendingDocument } from './types'

export interface PendingImage {
  file: File
  previewUrl: string
}

interface Options {
  running: () => boolean
  onUnsupportedFiles: (names: string[]) => void
  onImagePasted: () => void
  focusInput: () => void
}

export function useComposerAttachments(options: Options) {
  const pendingImages = ref<PendingImage[]>([])
  const pendingDocuments = ref<PendingDocument[]>([])
  const imageInputRef = ref<HTMLInputElement | null>(null)
  const documentInputRef = ref<HTMLInputElement | null>(null)

  function revokePendingImage(url: string) {
    try { URL.revokeObjectURL(url) } catch { /* Already released by the browser. */ }
  }
  function removePendingImage(index: number) {
    const item = pendingImages.value[index]
    if (!item) return
    revokePendingImage(item.previewUrl)
    pendingImages.value.splice(index, 1)
  }
  function removePendingDocument(index: number) {
    pendingDocuments.value.splice(index, 1)
  }
  function detectDocumentType(file: File): ChatDocumentKind | null {
    const name = String(file.name || '').toLowerCase()
    if (name.endsWith('.pdf')) return 'pdf'
    if (name.endsWith('.docx') || name.endsWith('.doc')) return 'docx'
    if (name.endsWith('.pptx') || name.endsWith('.ppt')) return 'pptx'
    // The backend reads the original extension; text uses the Markdown path.
    if (name.endsWith('.md') || name.endsWith('.txt')) return 'md'
    if (name.endsWith('.html') || name.endsWith('.htm')) return 'html'
    if (name.endsWith('.xlsx') || name.endsWith('.xlsm') || name.endsWith('.xls')) return 'xlsx'
    if (name.endsWith('.csv') || name.endsWith('.tsv')) return 'xlsx'
    return null
  }
  function addImageFiles(files: File[]) {
    for (const file of files) {
      if (!(file.type || '').startsWith('image/')) continue
      pendingImages.value.push({ file, previewUrl: URL.createObjectURL(file) })
    }
  }
  function onImageSelected(event: Event) {
    const input = event.target as HTMLInputElement
    if (!input.files?.length) return
    addImageFiles(Array.from(input.files))
    input.value = ''
  }
  function onDocumentSelected(event: Event) {
    const input = event.target as HTMLInputElement
    if (!input.files?.length) return
    const unsupportedNames: string[] = []
    for (const file of Array.from(input.files)) {
      const kind = detectDocumentType(file)
      if (kind) pendingDocuments.value.push({ file, kind })
      else unsupportedNames.push(file.name)
    }
    if (unsupportedNames.length) options.onUnsupportedFiles(unsupportedNames)
    input.value = ''
  }
  function onComposerPaste(event: ClipboardEvent) {
    if (options.running()) return
    const files = Array.from(event.clipboardData?.items || [])
      .filter(item => item.kind === 'file' && item.type.startsWith('image/'))
      .map(item => item.getAsFile())
      .filter((file): file is File => Boolean(file))
    if (!files.length) return
    event.preventDefault()
    options.onImagePasted()
    addImageFiles(files)
    nextTick(options.focusInput)
  }

  onBeforeUnmount(() => {
    for (const item of pendingImages.value) revokePendingImage(item.previewUrl)
    pendingDocuments.value = []
  })

  return {
    pendingImages, pendingDocuments, imageInputRef, documentInputRef,
    revokePendingImage, removePendingImage, removePendingDocument,
    onImageSelected, onDocumentSelected, onComposerPaste,
  }
}
