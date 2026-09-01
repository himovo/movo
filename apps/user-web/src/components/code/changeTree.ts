import type { DshWorkspaceSummary } from '../../platform/types'

export type WorkspaceChange = DshWorkspaceSummary['changes'][number]
export interface WorkspaceChangeNode {
  name: string
  path: string
  kind: 'directory' | 'file'
  children: WorkspaceChangeNode[]
  change?: WorkspaceChange
}

export function buildWorkspaceChangeTree(changes: WorkspaceChange[]): WorkspaceChangeNode[] {
  const roots: WorkspaceChangeNode[] = []
  for (const change of changes) {
    const parts = change.path.split('/').filter(Boolean)
    let current = roots
    let path = ''
    parts.forEach((part, index) => {
      path = path ? `${path}/${part}` : part
      const file = index === parts.length - 1
      let node = current.find(item => item.name === part)
      if (!node) {
        node = { name: part, path, kind: file ? 'file' : 'directory', children: [], change: file ? change : undefined }
        current.push(node)
      }
      current = node.children
    })
  }
  const sort = (nodes: WorkspaceChangeNode[]) => {
    nodes.sort((left, right) => Number(right.kind === 'directory') - Number(left.kind === 'directory') || left.name.localeCompare(right.name))
    nodes.forEach(node => sort(node.children))
  }
  sort(roots)
  return roots
}

