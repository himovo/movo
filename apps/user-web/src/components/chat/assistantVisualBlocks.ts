export type VisualKind = 'metrics' | 'priorities' | 'flow' | 'timeline' | 'insights' | 'checklist'
export type VisualItem = { label: string; value?: string; detail?: string; tone?: 'blue' | 'green' | 'amber' | 'purple'; checked?: boolean }
export type VisualBlock = { kind: VisualKind; title?: string; items: VisualItem[]; note?: string }

const KINDS = new Set<VisualKind>(['metrics', 'priorities', 'flow', 'timeline', 'insights', 'checklist'])
const TONES = new Set(['blue', 'green', 'amber', 'purple'])
const MAX_ITEMS = 12
const MAX_TEXT = 500

export function visualKindFromHeading(value: string): VisualKind | null {
  const heading = value.toLowerCase()
  if (/timeline|milestone|\u65f6\u95f4\u7ebf|\u9636\u6bb5/.test(heading)) return 'timeline'
  if (/priorit|\u4f18\u5148\u7ea7/.test(heading)) return 'priorities'
  if (/checklist|check\s*list|\u6e05\u5355|\u68c0\u67e5/.test(heading)) return 'checklist'
  if (/insight|judg|\u5224\u65ad|\u6d1e\u5bdf/.test(heading)) return 'insights'
  if (/flow|layer|\u6d41\u7a0b|\u5206\u5c42/.test(heading)) return 'flow'
  if (/metric|compar|\u6307\u6807|\u5bf9\u6bd4/.test(heading)) return 'metrics'
  return null
}

function text(value: unknown, max = MAX_TEXT): string {
  return typeof value === 'string' ? value.trim().slice(0, max) : ''
}

export function parseVisualBlock(source: string, headingHint = ''): VisualBlock | null {
  if (source.length > 16_000) return null
  let data: unknown
  try { data = JSON.parse(source) } catch { return null }
  if (!data || typeof data !== 'object' || Array.isArray(data)) return null
  const row = data as Record<string, unknown>
  const kind = row.kind === undefined
    ? visualKindFromHeading(text(row.title, 160)) || visualKindFromHeading(headingHint)
    : row.kind as VisualKind
  if (!kind || !KINDS.has(kind) || !Array.isArray(row.items) || !row.items.length || row.items.length > MAX_ITEMS) return null
  const items: VisualItem[] = []
  for (const raw of row.items) {
    if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null
    const item = raw as Record<string, unknown>
    const label = text(item.label, 120)
    if (!label) return null
    items.push({
      label, value: text(item.value, 120) || undefined, detail: text(item.detail) || undefined,
      tone: TONES.has(item.tone as string) ? item.tone as VisualItem['tone'] : undefined,
      checked: typeof item.checked === 'boolean' ? item.checked : undefined,
    })
  }
  return { kind, title: text(row.title, 160) || undefined, items, note: text(row.note) || undefined }
}
