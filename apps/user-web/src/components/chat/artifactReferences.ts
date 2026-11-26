import type { ArtifactItem } from '../../features/execution-v3/domain/delivery'

export function artifactReferences(artifacts: ArtifactItem[]): Record<string, string> {
  const references: Record<string, string> = {}
  const names = new Map<string, string | null>()
  for (const item of artifacts) {
    const key = item.object_path || item.id
    if (!key) continue
    if (item.object_path) references[item.object_path] = key
    if (item.relative_path) references[item.relative_path] = key
    const filename = item.filename || item.relative_path?.split('/').at(-1)
    if (filename) names.set(filename, names.has(filename) ? null : key)
  }
  for (const [name, key] of names) if (key) references[name] = key
  return references
}
