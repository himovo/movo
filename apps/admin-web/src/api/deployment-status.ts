import { apiClient } from './client'

export interface DeploymentService {
  name: string
  status: string
  health?: string
  image?: string
  imageId?: string
  revision?: string
  versionMismatch?: boolean
  containerId?: string
  createdAt?: string | null
  startedAt?: string | null
  restarts?: number
}

export interface DeploymentStatus {
  checkedAt: string
  deployment: { upgradedAt?: string; version?: string; commit?: string; revisions?: string[] }
  services: DeploymentService[]
  scriptImage: { image: string; imageId: string; available: boolean }
}

export async function fetchDeploymentStatus(): Promise<DeploymentStatus> {
  const { data } = await apiClient.get<DeploymentStatus>('/api/deployment/status')
  return data
}
