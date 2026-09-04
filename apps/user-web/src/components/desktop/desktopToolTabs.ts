import type { DshTaskChangeSet } from '../../platform/types'

export type DesktopToolLauncherKind = 'browser' | 'changes' | 'files' | 'terminal'
export type DesktopToolTabKind = DesktopToolLauncherKind | 'file' | 'diff'

export interface DesktopToolTabResource {
  path?: string
  taskChanges?: DshTaskChangeSet
}

export interface DesktopToolTab {
  id: string
  kind: DesktopToolTabKind
  title: string
  resource?: DesktopToolTabResource
}

export function desktopResourceName(path: string): string {
  return path.split('/').filter(Boolean).pop() || path
}

export function desktopFileTabId(path: string): string {
  return `file:${encodeURIComponent(path)}`
}

export function desktopDiffTabId(path: string, taskId?: string): string {
  return `diff:${encodeURIComponent(taskId || 'workspace')}:${encodeURIComponent(path)}`
}
