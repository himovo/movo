function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

export function decodeResponseJsonField(response: unknown, path: string): unknown {
  const parts = path.trim().split('.')
  const ancestors: Array<{ record: Record<string, unknown>; key: string }> = []
  let value = response
  for (const key of parts) {
    if (!key || !isRecord(value) || !Object.prototype.hasOwnProperty.call(value, key)) return response
    ancestors.push({ record: value, key })
    value = value[key]
  }
  if (typeof value !== 'string') return response

  let parsed: unknown
  try {
    parsed = JSON.parse(value)
  } catch {
    return response
  }
  if (!isRecord(parsed) && !Array.isArray(parsed)) return response
  return ancestors.reduceRight<unknown>((child, { record, key }) => ({ ...record, [key]: child }), parsed)
}
