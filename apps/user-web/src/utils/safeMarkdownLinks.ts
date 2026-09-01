/** Minimal standard Markdown-link projection with an explicit URL allowlist. */

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;')
}

function safeExternalHref(value: string): string | undefined {
  try {
    const url = new URL(value)
    if (url.protocol !== 'http:' && url.protocol !== 'https:') return undefined
    return escapeHtml(url.href)
  } catch {
    return undefined
  }
}

export function projectSafeMarkdownLinks(
  text: string,
  render: (label: string, href: string) => string,
): string {
  let output = ''
  let cursor = 0
  while (cursor < text.length) {
    const start = text.indexOf('[', cursor)
    if (start < 0) {
      output += text.slice(cursor)
      break
    }
    output += text.slice(cursor, start)
    if (start > 0 && text[start - 1] === '!') {
      output += '['
      cursor = start + 1
      continue
    }
    const labelEnd = text.indexOf('](', start + 1)
    if (labelEnd < 0 || text.slice(start + 1, labelEnd).includes('\n')) {
      output += '['
      cursor = start + 1
      continue
    }
    let depth = 0
    let end = labelEnd + 2
    for (; end < text.length; end += 1) {
      if (text[end] === '(') depth += 1
      else if (text[end] === ')' && depth > 0) depth -= 1
      else if (text[end] === ')') break
    }
    if (end >= text.length) {
      output += '['
      cursor = start + 1
      continue
    }
    const label = text.slice(start + 1, labelEnd)
    const href = safeExternalHref(text.slice(labelEnd + 2, end).trim())
    if (!href) {
      output += text.slice(start, end + 1)
    } else {
      output += render(escapeHtml(label), href)
    }
    cursor = end + 1
  }
  return output
}

