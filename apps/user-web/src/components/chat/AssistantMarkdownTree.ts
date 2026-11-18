import MarkdownIt from 'markdown-it'
import { defineComponent, h, type PropType, type VNodeChild } from 'vue'
import type Token from 'markdown-it/lib/token.mjs'
import AssistantVisualBlock from './AssistantVisualBlock.vue'
import { parseVisualBlock } from './assistantVisualBlocks'
import { normalizeAssistantContent, sanitizeMermaid, workspaceFileReference } from '../../utils/assistantMarkdown'
import { t } from '../../composables/i18n'
import { highlightAssistantCode } from '../../utils/assistantCodeHighlight'

const parser = new MarkdownIt({ html: false, linkify: true, breaks: true, typographer: false })
parser.validateLink = value => Boolean(safeUrl(value)) || value.startsWith('sandbox:/') || !/^[a-z][a-z0-9+.-]*:/i.test(value)
const allowedTags = new Set(['p', 'h1', 'h2', 'h3', 'h4', 'blockquote', 'ul', 'ol', 'li', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'em', 'strong', 's'])

function highlightedCode(source: string, language: string): VNodeChild[] {
  const highlighted = highlightAssistantCode(source, language)
  if (!highlighted || typeof DOMParser === 'undefined') return [source]
  const document = new DOMParser().parseFromString(`<body>${highlighted}</body>`, 'text/html')
  const visit = (node: ChildNode): VNodeChild => {
    if (node.nodeType === Node.TEXT_NODE) return node.textContent || ''
    if (node instanceof HTMLElement && node.tagName === 'SPAN') {
      const name = [...node.classList].find(value => /^hljs-[a-z-]+$/.test(value))
      if (name) return h('span', { class: name }, [...node.childNodes].map(visit))
    }
    return node.textContent || ''
  }
  return [...document.body.childNodes].map(visit)
}

function safeUrl(raw: string): string | null {
  try {
    const url = new URL(raw)
    return ['http:', 'https:'].includes(url.protocol) ? url.href : null
  } catch { return null }
}

function inline(tokens: Token[], props: { fileReferences: boolean; artifactPaths: Record<string, string> }): VNodeChild[] {
  const roots: VNodeChild[] = []
  const stack: Array<{ tag: string; attrs: Record<string, unknown>; children: VNodeChild[] }> = []
  const append = (child: VNodeChild) => (stack.at(-1)?.children || roots).push(child)
  for (const token of tokens) {
    if (token.type === 'text') { append(token.content); continue }
    if (token.type === 'softbreak' || token.type === 'hardbreak') { append(h('br')); continue }
    if (token.type === 'code_inline') {
      const path = props.fileReferences ? workspaceFileReference(token.content) : null
      append(h('code', { class: path ? 'assistant-inline-code assistant-file-reference' : 'assistant-inline-code', ...(path ? { 'data-workspace-file': path, role: 'button', tabindex: 0 } : {}) }, token.content))
      continue
    }
    if (token.type === 'image') {
      const src = safeUrl(token.attrGet('src') || '')
      if (src) append(h('img', { src, alt: token.content, role: 'button', tabindex: 0, loading: 'lazy' }))
      else append(token.content)
      continue
    }
    if (token.nesting === 1) {
      const tag = token.type === 'link_open' ? 'a' : token.tag
      if (tag === 'a') {
        const target = token.attrGet('href') || ''
        const href = safeUrl(target)
        const artifact = Object.prototype.hasOwnProperty.call(props.artifactPaths, target) ? props.artifactPaths[target] : null
        stack.push({ tag: href ? 'a' : artifact ? 'button' : 'span', attrs: href ? { href, target: '_blank', rel: 'noopener noreferrer nofollow' } : artifact ? { type: 'button', 'data-artifact-path': artifact } : {}, children: [] })
      } else if (allowedTags.has(tag)) stack.push({ tag, attrs: {}, children: [] })
      continue
    }
    if (token.nesting === -1) {
      const frame = stack.pop()
      if (frame) append(h(frame.tag, frame.attrs, frame.children))
    }
  }
  return roots
}

function renderTokens(tokens: Token[], props: { fileReferences: boolean; artifactPaths: Record<string, string> }): VNodeChild[] {
  const roots: VNodeChild[] = []
  const stack: Array<{ tag: string; attrs: Record<string, unknown>; children: VNodeChild[] }> = []
  let currentHeading = ''
  let pendingHeading = ''
  const append = (child: VNodeChild) => (stack.at(-1)?.children || roots).push(child)
  for (const token of tokens) {
    if (token.type === 'inline') {
      if (/^h[1-4]$/.test(stack.at(-1)?.tag || '')) pendingHeading = token.content
      for (const child of inline(token.children || [], props)) append(child)
      continue
    }
    if (token.type === 'fence' || token.type === 'code_block') {
      const language = (token.info || '').trim().split(/\s+/)[0]?.toLowerCase() || 'text'
      if (language === 'movo-visual') {
        const block = parseVisualBlock(token.content, currentHeading)
        if (block) { append(h(AssistantVisualBlock, { block })); continue }
      }
      if (language === 'mermaid') {
        const source = sanitizeMermaid(token.content)
        append(h('div', { class: 'mermaid', 'data-raw': encodeURIComponent(source) }, source))
        continue
      }
      if (language === 'chart') { append(h('div', { class: 'chart-container', style: 'height:360px' }, [h('canvas', { class: 'chart-block', 'data-chart': encodeURIComponent(token.content) })])); continue }
      const source = token.content.replace(/\n$/, '')
      append(h('div', { class: 'assistant-code-block' }, [
        h('div', { class: 'assistant-code-header' }, [h('span', { class: 'assistant-code-language' }, language.toUpperCase()), h('button', { class: 'assistant-code-copy', type: 'button', 'aria-label': t('chat.copy_code'), title: t('chat.copy_code') }, [
          h('svg', { class: 'assistant-code-copy-icon', 'aria-hidden': 'true', viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': '1.8', 'stroke-linecap': 'round', 'stroke-linejoin': 'round' }, [h('rect', { x: 8, y: 8, width: 11, height: 11, rx: 2 }), h('path', { d: 'M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3' })]),
          h('svg', { class: 'assistant-code-check-icon', 'aria-hidden': 'true', viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': '1.8', 'stroke-linecap': 'round', 'stroke-linejoin': 'round' }, [h('path', { d: 'm5 12 4 4L19 6' })]),
        ])]),
        h('div', { class: 'assistant-code-scroll' }, [h('pre', { class: 'assistant-code-content' }, [h('code', highlightedCode(source, language))])]),
      ]))
      continue
    }
    if (token.type === 'hr') { append(h('hr')); continue }
    if (token.nesting === 1 && allowedTags.has(token.tag)) {
      const attrs: Record<string, unknown> = {}
      if (token.tag === 'ol' && token.attrGet('start')) attrs.start = token.attrGet('start')
      stack.push({ tag: token.tag, attrs, children: [] })
      continue
    }
    if (token.nesting === -1 && allowedTags.has(token.tag)) {
      const frame = stack.pop()
      if (frame) {
        const node = h(frame.tag, frame.attrs, frame.children)
        append(frame.tag === 'table' ? h('div', { class: 'assistant-table-scroll', role: 'region', tabindex: 0, 'aria-label': t('chat.table') }, [node]) : node)
      }
      if (/^h[1-4]$/.test(token.tag)) {
        currentHeading = pendingHeading
        pendingHeading = ''
      }
    }
  }
  return roots
}

export default defineComponent({
  name: 'AssistantMarkdownTree',
  props: {
    content: { type: String, required: true },
    fileReferences: { type: Boolean, default: false },
    artifactPaths: { type: Object as PropType<Record<string, string>>, default: () => ({}) },
  },
  setup(props) {
    return () => h('div', { class: 'assistant-markdown-tree' }, renderTokens(parser.parse(normalizeAssistantContent(props.content), {}), props))
  },
})
