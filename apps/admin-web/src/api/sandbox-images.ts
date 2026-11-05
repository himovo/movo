import { apiClient } from './client'

export async function exportSandboxImage(name: string): Promise<void> {
  const { data } = await apiClient.get<Blob>('/api/sandbox-images/export', {
    params: { name }, responseType: 'blob', timeout: 3600000,
  })
  const url = URL.createObjectURL(data)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = 'movo-sandbox-image.zip'
  anchor.click()
  setTimeout(() => URL.revokeObjectURL(url), 60000)
}

export async function importSandboxImage(file: File): Promise<void> {
  await apiClient.post('/api/sandbox-images/import', file, {
    timeout: 3600000, headers: { 'Content-Type': 'application/octet-stream' },
  })
}
