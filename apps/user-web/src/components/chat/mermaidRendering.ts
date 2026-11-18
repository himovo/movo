import { t } from '../../composables/i18n'
import { sanitizeMermaid } from '../../utils/assistantMarkdown'

export async function ensureScript(url: string, globalName: string): Promise<any> {
  if ((window as any)[globalName]) return (window as any)[globalName]
  return new Promise((resolve, reject) => {
    const existing = document.querySelector(`script[data-src="${url}"]`) as HTMLScriptElement | null
    if (existing) {
      existing.addEventListener('load', () => resolve((window as any)[globalName]))
      existing.addEventListener('error', reject)
      return
    }
    const script = document.createElement('script')
    script.src = url
    script.async = true
    script.dataset.src = url
    script.onload = () => resolve((window as any)[globalName])
    script.onerror = reject
    document.head.appendChild(script)
  })
}

export async function renderMermaidBlocks(): Promise<void> {
  const blocks = Array.from(document.querySelectorAll('.mermaid')) as HTMLElement[]
  if (!blocks.length) return
  const mermaid = await ensureScript('https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js', 'mermaid')
  if (!mermaid) return
  mermaid.initialize({ startOnLoad: false })
  for (const block of blocks) {
    if (block.dataset.rendered === 'true') continue
    block.dataset.rendered = 'true'
    try {
      await mermaid.run({ nodes: [block] })
    } catch {
      const raw = block.dataset.raw ? decodeURIComponent(block.dataset.raw) : (block.textContent || '')
      const sanitized = sanitizeMermaid(raw)
      if (sanitized !== raw) {
        try {
          block.textContent = sanitized
          await mermaid.run({ nodes: [block] })
          block.dataset.rendered = 'true'
          continue
        } catch {
          // Fall through to the original text preview.
        }
      }
      const preview = raw.length > 800 ? raw.slice(0, 800) + '…' : raw
      block.dataset.rendered = 'false'
      block.classList.remove('mermaid')
      const error = document.createElement('div')
      error.className = 'text-xs text-red-600 mb-2'
      error.textContent = t('chat.mermaid_error')
      const source = document.createElement('pre')
      source.className = 'bg-gray-50 border border-gray-200 rounded-lg p-3 text-xs overflow-auto whitespace-pre-wrap'
      source.textContent = preview
      block.replaceChildren(error, source)
    }
  }
}
