import type { ArtifactItem } from './delivery'
import { finalPresentationDelivery, isPresentationDelivery } from './presentationDelivery'

/** Tool artifact metadata, rather than model prose, determines deliverables. */
export function visibleAnswerArtifacts(
  artifacts: ArtifactItem[],
  runStatus: string,
): ArtifactItem[] {
  if (runStatus === 'running') return []
  const visible = artifacts.filter((item) =>
    item.lifecycle?.toLowerCase() !== 'intermediate'
    && item.visibility?.toLowerCase() !== 'internal',
  )
  const presentation = finalPresentationDelivery(visible)
  // Selection affects the answer only; the execution store retains every
  // version for audit. Non-presentation files keep their existing behavior.
  return visible.filter((item) => !isPresentationDelivery(item) || item === presentation)
}
