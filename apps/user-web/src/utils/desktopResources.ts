import { capabilities, openResource, saveBytes } from '../platform'

export async function openPreviewResource(url: string): Promise<void> {
  await openResource(url, 'preview')
}

export async function saveBlobDownload(blob: Blob, filename: string): Promise<void> {
  await saveBytes(filename, new Uint8Array(await blob.arrayBuffer()))
}

export async function downloadResourceUrl(url: string, filename: string): Promise<void> {
  if (capabilities.managedDownloads) {
    await openResource(url, 'preview')
    return
  }
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.target = '_blank'
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
}
