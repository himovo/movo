/**
 * T9: pure author-presentation resolver for shared user-message rows.
 *
 * `UserMessageAuthor.vue` is a thin template delegation to this module, so the
 * headless contract suite can assert the return values without a DOM and
 * `typecheck` proves the wiring. The helper never returns a raw avatar value:
 * unsafe or relative paths degrade to deterministic initials.
 */

export type AuthorIdentityInput = {
  display_name: string | null | undefined
  avatar_url: string | null | undefined
}

export type AuthorPresentation =
  | { kind: 'image'; src: string; alt: string }
  | { kind: 'initials'; text: string; ariaLabel: string }

const FALLBACK_NAME = 'User'
const FALLBACK_IMAGE_ALT = 'User avatar'
const FALLBACK_INITIALS = '?'

function normalizedName(displayName: string | null | undefined): string | null {
  const name = (displayName ?? '').trim().replace(/\s+/g, ' ')
  return name.length > 0 ? name : null
}

function initialsFromName(name: string | null): string {
  if (!name) return FALLBACK_INITIALS
  const letters: string[] = []
  for (const word of name.split(/\s+/)) {
    const first = Array.from(word)[0]
    if (!first) continue
    letters.push(first.toUpperCase())
    if (letters.length === 2) break
  }
  return letters.join('') || FALLBACK_INITIALS
}

/** Allows only absolute http(s) URLs; rejects object paths, protocols, and whitespace. */
function safeAvatarUrl(avatarUrl: string | null | undefined): string | null {
  const raw = (avatarUrl ?? '').trim()
  if (!raw) return null
  if (/[\u0000-\u0020\u007f]/.test(raw)) return null
  let parsed: URL
  try {
    parsed = new URL(raw)
  } catch {
    return null
  }
  if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') return null
  return parsed.href
}

export function resolveAuthorPresentation(input: AuthorIdentityInput): AuthorPresentation {
  const name = normalizedName(input.display_name)
  const src = safeAvatarUrl(input.avatar_url)
  if (src !== null) return { kind: 'image', src, alt: name ?? FALLBACK_IMAGE_ALT }
  return { kind: 'initials', text: initialsFromName(name), ariaLabel: name ?? FALLBACK_NAME }
}
