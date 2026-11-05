import { apiClient } from './client'

export interface OfflinePackageInventory {
  offlineOnly: boolean
  platform: string
  os: string
  counts: Record<string, number>
  sizes: Record<string, number>
  collections: {
    digest: string
    kind?: string
    name?: string
    version?: string
    skillId?: string
    skillName?: string
    recordId: string
    source: string
    createdAt: string
    declared: Record<string, string[]>
  }[]
}

export async function fetchOfflinePackages(): Promise<OfflinePackageInventory> {
  const { data } = await apiClient.get<OfflinePackageInventory>('/api/offline-packages')
  return data
}

export async function setOfflineOnly(offlineOnly: boolean): Promise<OfflinePackageInventory> {
  const { data } = await apiClient.put<OfflinePackageInventory>('/api/offline-packages/mode', { offlineOnly })
  return data
}

export async function importOfflinePackages(file: File): Promise<OfflinePackageInventory> {
  const { data } = await apiClient.post<OfflinePackageInventory>('/api/offline-packages/import', file, {
    timeout: 3600000, headers: { 'Content-Type': 'application/octet-stream' },
  })
  return data
}

export async function exportOfflinePackages(recordIds: string[] = []): Promise<void> {
  const { data } = await apiClient.get<Blob>('/api/offline-packages/export', {
    responseType: 'blob', timeout: 3600000,
    params: recordIds.length ? { records: recordIds.join(',') } : undefined,
  })
  const url = URL.createObjectURL(data)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = 'movo-offline-packages.zip'
  anchor.click()
  setTimeout(() => URL.revokeObjectURL(url), 60000)
}
