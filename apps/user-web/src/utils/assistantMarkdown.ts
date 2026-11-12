/** Shared Markdown projection for streaming and completed assistant content. */

import { projectSafeMarkdownLinks } from './safeMarkdownLinks'
import { extractAssistantCodeBlocks } from './assistantCodeBlocks'

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;')
}

export function normalizeAssistantContent(content: string): string {
  if (!content) return content
  const lines = content.replace(/<br\s*\/?>/gi, '\n').split('\n')
  const result: string[] = []
  let inCodeBlock = false
  for (const line of lines) {
    if (/^\s{0,3}(?:`{3,}|~{3,})/.test(line)) {
      inCodeBlock = !inCodeBlock
      result.push(line)
      continue
    }
    if (inCodeBlock) {
      result.push(line)
      continue
    }
    const trimmed = line.trim()
    if (trimmed && result[result.length - 1]?.trim() === trimmed) continue
    result.push(line)
  }
  return result.join('\n')
}

export function sanitizeMermaid(code: string): string {
  let text = code.replace(/–/g, '-').replace(/\u00a0/g, ' ').replace(/\r/g, '')
  text = text.replace(/^\s*subgraph\s+([^"\n]+)$/gm, (match, title) => {
    const value = String(title || '').trim()
    return !value || value.startsWith('"') ? match : `subgraph "${value}"`
  })
  return text.replace(/(\[|\(|\{)([^\]\)\}\n]+)(\]|\)|\})/g, (match, open, content, close) => {
    let value = String(content || '').trim()
    if (value.startsWith('"') && value.endsWith('"')) return match
    value = value.replace(/"/g, "'")
    return `${open}"${value}"${close}`
  })
}

const FILE_EXTENSION = /\.(?:[cm]?[jt]sx?|vue|svelte|py|pyi|go|rs|java|kt|kts|swift|c|cc|cpp|cxx|h|hh|hpp|cs|php|rb|sh|bash|zsh|fish|ps1|sql|html?|css|scss|sass|less|json|ya?ml|toml|ini|conf|env|md|mdx|txt|xml|graphql|gql|proto|dockerfile)$/i
const WELL_KNOWN_FILE = /^(?:README|CHANGELOG|LICENSE|Makefile|Dockerfile|Procfile|Gemfile|Rakefile)(?:\.[a-z0-9_-]+)?$/i

export function workspaceFileReference(value: string): string | null {
  let path = value.trim().replace(/\\/g, '/')
  if (!path || /[\s{}"'<>]/.test(path) || path.startsWith('/') || /^[a-z]+:\/\//i.test(path)) return null
  path = path.replace(/^\.\//, '').replace(/:(\d+)(?::\d+)?$/, '')
  if (!path || path.split('/').some(part => !part || part === '.' || part === '..')) return null
  const name = path.split('/').at(-1) || ''
  return FILE_EXTENSION.test(name) || WELL_KNOWN_FILE.test(name) ? path : null
}

export function renderAssistantMarkdown(text: string, options: { workspaceFileReferences?: boolean; artifactPaths?: Record<string, string> } = {}): string {
  const extracted = extractAssistantCodeBlocks(normalizeAssistantContent(text), sanitizeMermaid)
  let html = extracted.text
  const blocks: string[] = [...extracted.blocks]
  const stash = (value: string) => {
    const key = `__BLOCK_PLACEHOLDER_${blocks.length}__`
    blocks.push(value)
    return key
  }

  html = html.replace(/!\[(.*?)\]\((.*?)\)/g, '<img alt="$1" src="$2" role="button" tabindex="0" style="max-width:100%; border-radius:12px;" />')
  html = html.replace(/^---+$/gm, '<hr class="my-4 border-gray-300"/>')

  html = html.replace(/`([^`]+)`/g, (_match, raw) => {
    const content = String(raw || '')
    const filePath = options.workspaceFileReferences ? workspaceFileReference(content) : null
    if (filePath) {
      return `<code class="assistant-inline-code assistant-file-reference" data-workspace-file="${escapeHtml(filePath)}" role="button" tabindex="0">${escapeHtml(content)}</code>`
    }
    return `<code class="assistant-inline-code">${escapeHtml(content)}</code>`
  })
  const artifactPaths = options.artifactPaths || {}
  html = projectSafeMarkdownLinks(html, (label, href) => stash(
    `<a href="${href}" target="_blank" rel="noopener noreferrer nofollow" class="text-blue-600 hover:text-blue-500 underline underline-offset-2">${label}</a>`,
  ), (label, path) => Object.prototype.hasOwnProperty.call(artifactPaths, path) ? stash(
    `<button type="button" data-artifact-path="${escapeHtml(artifactPaths[path])}" class="text-blue-600 hover:text-blue-500 underline underline-offset-2">${label}</button>`,
  ) : undefined)
  html = html.replace(/\|(.+)\|/g, (_match, content) => {
    const cells = String(content).split('|').map(cell => cell.trim()).filter(Boolean)
    return `<tr>${cells.map(cell => `<td class="border border-gray-300 px-3 py-2">${cell}</td>`).join('')}</tr>`
  })
  html = html.replace(/(<tr>.*<\/tr>\n?)+/g, (match) => {
    const rows = match.split('\n').filter(row => row.trim())
    if (rows.length > 1 && rows[1].includes('---')) {
      const header = rows[0].replace(/<td/g, '<th').replace(/<\/td>/g, '</th>').replace(/border-gray-300/g, 'border-gray-300 bg-gray-100 font-bold')
      return `<table class="w-full border-collapse my-4">${header}${rows.slice(2).join('\n')}</table>`
    }
    return `<table class="w-full border-collapse my-4">${match}</table>`
  })
  html = html.replace(/^\s*####\s+(.+)$/gim, '<h4 class="text-base font-semibold mt-3 mb-2">$1</h4>')
  html = html.replace(/^\s*###\s+(.+)$/gim, '<h3 class="text-lg font-bold mt-4 mb-2">$1</h3>')
  html = html.replace(/^\s*##\s+(.+)$/gim, '<h2 class="text-xl font-bold mt-4 mb-2">$1</h2>')
  html = html.replace(/^\s*#\s+(.+)$/gim, '<h1 class="text-2xl font-bold mt-4 mb-2">$1</h1>')
  html = html.replace(/\*\*(.*?)\*\*/g, '<strong class="font-bold">$1</strong>')
  html = html.replace(/\*(.*?)\*/g, '<em class="italic">$1</em>')
  html = html.replace(/^- (.*$)/gim, '<li class="list-disc ml-6">$1</li>')
  html = html.replace(/^\d+\. (.*$)/gim, '<li class="list-decimal ml-6">$1</li>')
  html = html.replace(/(<li class="list-disc[^>]*>.*<\/li>\n?)+/g, match => `<ul class="my-2">${match.replace(/\n/g, '')}</ul>`)
  html = html.replace(/(<li class="list-decimal[^>]*>.*<\/li>\n?)+/g, match => `<ol class="my-2">${match.replace(/\n/g, '')}</ol>`)
  html = html.replace(/(<\/(h[1-6]|ul|ol|table|tr|blockquote)>)\s*\n+/g, '$1')
  html = html.replace(/(<hr[^>]*>)\s*\n+/g, '$1')
  html = html.replace(/\n\n/g, '<br/><br/>').replace(/\n/g, '<br/>')
  blocks.forEach((block, index) => { html = html.replace(`__BLOCK_PLACEHOLDER_${index}__`, block) })
  return html
}
