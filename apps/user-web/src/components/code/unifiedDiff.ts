export type DiffLineKind = 'add' | 'delete' | 'hunk' | 'meta' | 'context'

export interface UnifiedDiffLine {
  id: number
  content: string
  kind: DiffLineKind
  oldLine: number | null
  newLine: number | null
}

export function parseUnifiedDiff(diff: string): UnifiedDiffLine[] {
  let oldLine: number | null = null
  let newLine: number | null = null
  const source = diff.endsWith('\n') ? diff.slice(0, -1) : diff
  if (!source) return []
  return source.split('\n').map((content, id) => {
    const hunk = /^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/.exec(content)
    if (hunk) {
      oldLine = Number(hunk[1])
      newLine = Number(hunk[2])
      return { id, content, kind: 'hunk', oldLine: null, newLine: null }
    }
    if (content.startsWith('+') && !content.startsWith('+++')) {
      const row = { id, content, kind: 'add' as const, oldLine: null, newLine }
      if (newLine !== null) newLine += 1
      return row
    }
    if (content.startsWith('-') && !content.startsWith('---')) {
      const row = { id, content, kind: 'delete' as const, oldLine, newLine: null }
      if (oldLine !== null) oldLine += 1
      return row
    }
    const isContext = oldLine !== null && newLine !== null && (content.startsWith(' ') || content === '')
    if (isContext) {
      const row = { id, content, kind: 'context' as const, oldLine, newLine }
      oldLine += 1
      newLine += 1
      return row
    }
    return { id, content, kind: 'meta', oldLine: null, newLine: null }
  })
}
