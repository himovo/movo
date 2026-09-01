export type PresentationStyle = Record<string, any>

const aliases: Record<string, string> = {
  fill: 'background',
  background_color: 'background',
  stroke_width: 'line_weight',
  line_width: 'line_weight',
  radius: 'border_radius',
  align: 'text_align',
  valign: 'vertical_align',
}

function snakeCase(value: string): string {
  return value
    .replace(/-/g, '_')
    .replace(/([a-z0-9])([A-Z])/g, '$1_$2')
    .toLowerCase()
}

/** Defensive compatibility for old/mixed blueprints loaded in the editor. */
export function canonicalPresentationStyle(raw: unknown, blockType = ''): PresentationStyle {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return {}
  const output: PresentationStyle = {}
  for (const [rawKey, value] of Object.entries(raw as PresentationStyle)) {
    const key = snakeCase(rawKey)
    let target = aliases[key] || key
    if (key === 'stroke') target = blockType === 'line' ? 'color' : 'border_color'
    if (key === 'stroke_width') target = blockType === 'line' ? 'line_weight' : 'border_width'
    output[target] = value
  }
  return output
}

