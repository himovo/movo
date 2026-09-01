export interface TextInsets {
  top: number
  right: number
  bottom: number
  left: number
}

function numberValue(value: unknown, fallback = 0): number {
  const parsed = Number.parseFloat(String(value ?? ''))
  return Number.isFinite(parsed) ? parsed : fallback
}

export function resolveTextInsets(padding: unknown): TextInsets {
  if (typeof padding === 'number') {
    return { top: padding, right: padding, bottom: padding, left: padding }
  }
  const values = String(padding ?? '').trim().split(/\s+/).filter(Boolean).map((item) => numberValue(item))
  if (!values.length) return { top: 0, right: 0, bottom: 0, left: 0 }
  if (values.length === 1) return { top: values[0], right: values[0], bottom: values[0], left: values[0] }
  if (values.length === 2) return { top: values[0], right: values[1], bottom: values[0], left: values[1] }
  if (values.length === 3) return { top: values[0], right: values[1], bottom: values[2], left: values[1] }
  return { top: values[0], right: values[1], bottom: values[2], left: values[3] }
}

export function resolveAlignedTextTop(
  boxTop: number,
  boxHeight: number,
  measuredTextHeight: number,
  insets: TextInsets,
  verticalAlign: unknown,
): number {
  const available = Math.max(0, boxHeight - insets.top - insets.bottom)
  const textHeight = Math.min(Math.max(0, measuredTextHeight), available || measuredTextHeight)
  const align = String(verticalAlign || 'top').toLowerCase()
  if (align === 'middle' || align === 'center') {
    return boxTop + insets.top + Math.max(0, (available - textHeight) / 2)
  }
  if (align === 'bottom' || align === 'end') {
    return boxTop + boxHeight - insets.bottom - textHeight
  }
  return boxTop + insets.top
}

export function resolveFontWeight(value: unknown): string {
  const normalized = String(value ?? '').trim().toLowerCase()
  const numeric = numberValue(value)
  return normalized === 'bold' || normalized === 'semibold' || numeric >= 600 ? 'bold' : 'normal'
}

