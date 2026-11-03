import type { ArtifactItem } from './delivery'
import { resolveArtifactKind } from './artifactKind'

function blueprintPath(item: ArtifactItem): string {
  return String(item.bundle?.deck_ir_artifact?.object_path
    || item.bundle?.preview_metadata?.blueprint_artifact_path || '').trim()
}

export function isPresentationDelivery(item: ArtifactItem): boolean {
  const kind = resolveArtifactKind(item)
  return ['ppt', 'pptx', 'presentation_preview_bundle'].includes(kind)
    || (kind === 'html' && Boolean(blueprintPath(item)))
}

function latest(items: ArtifactItem[]): ArtifactItem | undefined {
  return items.reduce<ArtifactItem | undefined>((selected, item) =>
    !selected || (Number(item.ts) || 0) >= (Number(selected.ts) || 0) ? item : selected,
  undefined)
}

/** One answer turn delivers the final presentation, not its generation history. */
export function finalPresentationDelivery(items: ArtifactItem[]): ArtifactItem | undefined {
  const presentations = items.filter(isPresentationDelivery)
  const final = latest(presentations)
  if (!final) return undefined
  const blueprint = blueprintPath(final)
  if (!blueprint) return final

  // Prefer the downloadable representation of the final deck. This also
  // handles a source preview replayed after its export during history load.
  return latest(presentations.filter((item) =>
    blueprintPath(item) === blueprint && ['ppt', 'pptx'].includes(resolveArtifactKind(item)),
  )) || final
}
