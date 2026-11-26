import type { ArtifactItem } from './delivery'
import { finalPresentationDelivery, isPresentationDelivery } from './presentationDelivery'
import { isImageArtifact } from './artifactKind'

/** Tool artifact metadata, rather than model prose, determines deliverables. */
export function visibleAnswerArtifacts(
  artifacts: ArtifactItem[],
  runStatus: string,
): ArtifactItem[] {
  const visible = artifacts.filter((item) =>
    (runStatus !== 'running' || isImageArtifact(item))
    && item.lifecycle?.toLowerCase() !== 'intermediate'
    && item.visibility?.toLowerCase() !== 'internal',
  )
  const presentation = finalPresentationDelivery(visible)
  // Selection affects the answer only; the execution store retains every
  // version for audit. Non-presentation files keep their existing behavior.
  const latestByName = new Map<string, ArtifactItem>()
  for (const item of visible) {
    const name = String(item.relative_path || item.filename || '').trim().toLowerCase()
    if (name) latestByName.set(name, item)
  }
  return visible.filter((item) => {
    if (isPresentationDelivery(item) && item !== presentation) return false
    const name = String(item.relative_path || item.filename || '').trim().toLowerCase()
    return !name || latestByName.get(name) === item
  })
}
