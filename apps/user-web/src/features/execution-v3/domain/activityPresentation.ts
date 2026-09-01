import type { ExecutionItemV3, V3ItemStatus } from './model'

export type ActivityOutcome = 'inconclusive' | 'needs_repair' | 'passed' | ''

export function activityOutcome(payload: Record<string, any> | undefined): ActivityOutcome {
  const value = String(payload?.detail?.outcome || payload?.outcome || '')
  return ['inconclusive', 'needs_repair', 'passed'].includes(value)
    ? value as ActivityOutcome
    : ''
}

export function activityStateMessageKey(
  status: V3ItemStatus,
  outcome: ActivityOutcome,
  payload?: Record<string, any>,
): string {
  if (outcome === 'inconclusive') {
    const errorType = String(payload?.detail?.error_type || payload?.error_type || '').toLowerCase()
    return errorType.includes('timeout')
      ? 'execution.v3.quality_timeout'
      : 'execution.v3.quality_inconclusive'
  }
  if (outcome === 'needs_repair') return 'execution.v3.quality_needs_repair'
  if (status === 'failed') return 'ui.failed'
  return ''
}

export function runningContainerIds(items: ExecutionItemV3[]): Set<string> {
  const byId = new Map(items.map((item) => [item.id, item]))
  const containers = new Set<string>()

  // A running item that already owns visible children is a grouping stage,
  // not the active leaf. Completed children still establish that ownership
  // during the short gap before the next child starts.
  for (const item of items) {
    const visited = new Set<string>()
    let parentId = item.parentId
    while (parentId && !visited.has(parentId)) {
      visited.add(parentId)
      const parent = byId.get(parentId)
      if (!parent) break
      if (parent.status === 'running') containers.add(parent.id)
      parentId = parent.parentId
    }
  }
  return containers
}

export function hasActiveRunningLeaf(
  items: ExecutionItemV3[],
  containerIds = runningContainerIds(items),
): boolean {
  return items.some((item) => item.status === 'running' && !containerIds.has(item.id))
}
