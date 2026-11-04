import type { DeploymentService, DeploymentStatus } from '@/api/deployment-status'

export const INFRASTRUCTURE = new Set(['mongo', 'redis', 'weaviate'])

export function serviceTone(service: DeploymentService): 'good' | 'warning' | 'muted' {
  if (service.status === 'disabled') return 'muted'
  if (service.status !== 'running' || service.health === 'unhealthy' || service.versionMismatch) return 'warning'
  return 'good'
}

export function serviceCounts(status: DeploymentStatus) {
  const services = status.services
  return {
    running: services.filter(service => service.status === 'running').length,
    issues: services.filter(service => serviceTone(service) === 'warning').length,
    disabled: services.filter(service => service.status === 'disabled').length,
    mismatches: services.filter(service => service.versionMismatch).length,
  }
}

export function shortId(value?: string | null) {
  if (!value) return '—'
  return value.length > 23 ? `${value.slice(0, 20)}…` : value
}

export function diagnostics(status: DeploymentStatus) {
  return JSON.stringify({
    checkedAt: status.checkedAt,
    deployment: status.deployment,
    services: status.services.map(({ name, status: state, health, image, imageId, revision, versionMismatch, containerId, createdAt, startedAt, restarts }) => ({
      name, status: state, health, image, imageId, revision, versionMismatch, containerId, createdAt, startedAt, restarts,
    })),
    scriptImage: status.scriptImage,
  }, null, 2)
}
