import { highlightAssistantCode } from './assistantCodeHighlight'

function escapeHtml(value: string): string {
  return value.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#039;')
}

function renderCode(code: string, language: string): string {
  const label = language ? escapeHtml(language.toUpperCase()) : 'TEXT'
  const content = highlightAssistantCode(code, language) ?? escapeHtml(code)
  return `<div class="assistant-code-block">
    <div class="assistant-code-header"><span class="assistant-code-language">${label}</span>
      <button class="assistant-code-copy" type="button" aria-label="Copy code" title="Copy code">
        <svg class="assistant-code-copy-icon" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="8" y="8" width="11" height="11" rx="2"/><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3"/></svg>
        <svg class="assistant-code-check-icon" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="m5 12 4 4L19 6"/></svg>
      </button>
    </div>
    <div class="assistant-code-scroll"><pre class="assistant-code-content"><code>${content}</code></pre></div>
  </div>`
}

function renderFence(code: string, language: string, sanitizeMermaid: (code: string) => string): string {
  if (language === 'mermaid') {
    const safe = sanitizeMermaid(code)
    return `<div class="mermaid" data-raw="${encodeURIComponent(safe)}">${escapeHtml(safe)}</div>`
  }
  if (language === 'chart') {
    return `<div class="chart-container" style="height:360px"><canvas class="chart-block" data-chart="${encodeURIComponent(code)}"></canvas></div>`
  }
  return renderCode(code, language === 'skill' ? 'skill' : language)
}

/** Extract fenced blocks before inline Markdown rules can reinterpret their contents. */
export function extractAssistantCodeBlocks(source: string, sanitizeMermaid: (code: string) => string): { text: string; blocks: string[] } {
  const lines = source.split('\n')
  const output: string[] = []
  const blocks: string[] = []
  for (let index = 0; index < lines.length; index += 1) {
    const opening = /^ {0,3}(`{3,}|~{3,})[ \t]*([^`~]*)$/.exec(lines[index])
    if (!opening) { output.push(lines[index]); continue }
    const marker = opening[1][0]
    const length = opening[1].length
    const language = opening[2].trim().split(/\s+/)[0]?.toLowerCase() || ''
    const closing = new RegExp(`^ {0,3}${marker}{${length},}[ \\t]*$`)
    const body: string[] = []
    let cursor = index + 1
    while (cursor < lines.length && !closing.test(lines[cursor])) body.push(lines[cursor++])
    if (cursor === lines.length && body.at(-1) === '') body.pop()
    const key = `__BLOCK_PLACEHOLDER_${blocks.length}__`
    blocks.push(renderFence(body.join('\n'), language, sanitizeMermaid))
    output.push(key)
    index = cursor
  }
  return { text: output.join('\n'), blocks }
}
