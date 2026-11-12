import type { ArtifactItem } from '../../features/execution-v3/domain/delivery'
import type { DshTaskChangeSet } from '../../platform/types'

export function withoutCodeChangeArtifacts(
  artifacts: ArtifactItem[],
  changes: DshTaskChangeSet | undefined,
): ArtifactItem[] {
  if (!changes || changes.undone) return artifacts
  const changedPaths = new Set(changes.files.map(file => file.path.replace(/^\.\//, '')))
  return artifacts.filter(item => {
    const path = (item.relative_path || item.filename || '').replace(/^\.\//, '')
    return !path || !changedPaths.has(path)
  })
}
