<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'

interface PreviewBlock {
  key: string
  type: 'text' | 'markdown'
  html: string
  text: string
  highlighted: boolean
}

const props = defineProps<{
  kind: string
  content: string
  highlightTexts?: string[]
}>()

const rootRef = ref<HTMLElement | null>(null)

const normalizedTargets = computed(() => (props.highlightTexts || [])
  .map((item) => normalizeText(item))
  .filter(Boolean))

const blocks = computed<PreviewBlock[]>(() => {
  if (props.kind === 'html') return []
  if (props.kind === 'markdown') return markdownBlocks(props.content, normalizedTargets.value)
  return textBlocks(props.content, normalizedTargets.value)
})

const sanitizedHtml = computed(() => props.kind === 'html' ? sanitizeHtmlDocument(props.content) : '')

function normalizeText(value: string): string {
  return String(value || '')
    .replace(/\s+/g, '')
    .replace(/[|，。、“”‘’：；（）()《》<>【】\[\]{}.,:;'"`~!！?？—_\-·]/g, '')
    .toLowerCase()
}

function escapeHtml(value: string): string {
  return String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function isTargetMatch(text: string, targets: string[]): boolean {
  const normalized = normalizeText(text)
  if (!normalized || !targets.length) return false
  return targets.some((target) => {
    if (!target) return false
    if (normalized.includes(target) || target.includes(normalized)) return true
    const common = longestCommonSubstring(normalized, target)
    const base = Math.min(normalized.length, target.length)
    return base > 0 && common / base >= 0.58 && common >= Math.min(16, Math.max(6, Math.floor(base * 0.4)))
  })
}

function longestCommonSubstring(a: string, b: string): number {
  if (!a || !b) return 0
  const previous = new Array(b.length + 1).fill(0)
  const current = new Array(b.length + 1).fill(0)
  let best = 0
  for (let i = 1; i <= a.length; i += 1) {
    for (let j = 1; j <= b.length; j += 1) {
      if (a[i - 1] === b[j - 1]) {
        current[j] = previous[j - 1] + 1
        best = Math.max(best, current[j])
      } else {
        current[j] = 0
      }
    }
    for (let j = 0; j <= b.length; j += 1) {
      previous[j] = current[j]
      current[j] = 0
    }
  }
  return best
}

function textBlocks(content: string, targets: string[]): PreviewBlock[] {
  return String(content || '').split(/\r?\n/).map((line, index) => ({
    key: `line-${index}`,
    type: 'text',
    html: escapeHtml(line || ' '),
    text: line,
    highlighted: isTargetMatch(line, targets),
  }))
}

function isMarkdownTableSeparator(line: string): boolean {
  const compact = line.replace(/[|\s:]/g, '')
  return compact.length > 0 && /^-+$/.test(compact)
}

function splitTableCells(line: string): string[] {
  return line.replace(/^\|/, '').replace(/\|$/, '').split('|').map((cell) => cell.trim())
}

function renderInlineMarkdown(value: string): string {
  return escapeHtml(value)
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\*([^*]+)\*/g, '<em>$1</em>')
}

function markdownBlocks(content: string, targets: string[]): PreviewBlock[] {
  const lines = String(content || '').split(/\r?\n/)
  const output: PreviewBlock[] = []
  let index = 0
  while (index < lines.length) {
    const line = lines[index] || ''
    const trimmed = line.trim()
    if (!trimmed) {
      index += 1
      continue
    }

    if (trimmed.startsWith('```')) {
      const start = index
      const lang = trimmed.slice(3).trim()
      const codeLines: string[] = []
      index += 1
      while (index < lines.length && !String(lines[index]).trim().startsWith('```')) {
        codeLines.push(lines[index] || '')
        index += 1
      }
      if (index < lines.length) index += 1
      const text = codeLines.join('\n')
      output.push({
        key: `code-${start}`,
        type: 'markdown',
        html: `<pre><code${lang ? ` data-lang="${escapeHtml(lang)}"` : ''}>${escapeHtml(text)}</code></pre>`,
        text,
        highlighted: isTargetMatch(text, targets),
      })
      continue
    }

    if (index + 1 < lines.length && line.includes('|') && isMarkdownTableSeparator(lines[index + 1] || '')) {
      const start = index
      const header = splitTableCells(line)
      index += 2
      const rows: string[][] = []
      while (index < lines.length && String(lines[index]).includes('|') && String(lines[index]).trim()) {
        rows.push(splitTableCells(lines[index] || ''))
        index += 1
      }
      const rowHtml = rows.map((row) => {
        const text = row.join(' ')
        const cls = isTargetMatch(text, targets) ? ' class="native-preview-row-highlight"' : ''
        return `<tr${cls}>${row.map((cell) => `<td>${renderInlineMarkdown(cell)}</td>`).join('')}</tr>`
      }).join('')
      const text = [header.join(' '), ...rows.map((row) => row.join(' '))].join('\n')
      output.push({
        key: `table-${start}`,
        type: 'markdown',
        html: `<div class="native-table-wrap"><table><thead><tr>${header.map((cell) => `<th>${renderInlineMarkdown(cell)}</th>`).join('')}</tr></thead><tbody>${rowHtml}</tbody></table></div>`,
        text,
        highlighted: isTargetMatch(text, targets),
      })
      continue
    }

    const heading = /^(#{1,6})\s+(.+)$/.exec(trimmed)
    if (heading) {
      const level = Math.min(6, heading[1].length)
      const text = heading[2]
      output.push({
        key: `heading-${index}`,
        type: 'markdown',
        html: `<h${level}>${renderInlineMarkdown(text)}</h${level}>`,
        text,
        highlighted: isTargetMatch(text, targets),
      })
      index += 1
      continue
    }

    if (/^[-*+]\s+/.test(trimmed)) {
      const start = index
      const items: string[] = []
      while (index < lines.length && /^[-*+]\s+/.test(String(lines[index]).trim())) {
        items.push(String(lines[index]).trim().replace(/^[-*+]\s+/, ''))
        index += 1
      }
      const text = items.join('\n')
      output.push({
        key: `list-${start}`,
        type: 'markdown',
        html: `<ul>${items.map((item) => `<li>${renderInlineMarkdown(item)}</li>`).join('')}</ul>`,
        text,
        highlighted: isTargetMatch(text, targets),
      })
      continue
    }

    const start = index
    const paragraph: string[] = []
    while (index < lines.length && String(lines[index]).trim() && !String(lines[index]).trim().startsWith('```')) {
      if (index + 1 < lines.length && String(lines[index]).includes('|') && isMarkdownTableSeparator(lines[index + 1] || '')) break
      paragraph.push(String(lines[index]).trim())
      index += 1
    }
    const text = paragraph.join(' ')
    output.push({
      key: `p-${start}`,
      type: 'markdown',
      html: `<p>${renderInlineMarkdown(text)}</p>`,
      text,
      highlighted: isTargetMatch(text, targets),
    })
  }
  return output
}

function sanitizeHtmlDocument(content: string): string {
  if (!content) return ''
  const parser = new DOMParser()
  const doc = parser.parseFromString(content, 'text/html')
  doc.querySelectorAll('script, iframe, object, embed, link, meta').forEach((node) => node.remove())
  doc.querySelectorAll('*').forEach((node) => {
    for (const attr of Array.from(node.attributes)) {
      const name = attr.name.toLowerCase()
      const value = attr.value.trim().toLowerCase()
      if (name.startsWith('on') || value.startsWith('javascript:')) {
        node.removeAttribute(attr.name)
      }
    }
  })
  return doc.body.innerHTML
}

function applyHtmlHighlight() {
  const root = rootRef.value
  if (!root || props.kind !== 'html' || !normalizedTargets.value.length) return
  root.querySelectorAll('.native-preview-highlight').forEach((node) => node.classList.remove('native-preview-highlight'))
  const candidates = Array.from(root.querySelectorAll('p, li, td, th, pre, blockquote, h1, h2, h3, h4, h5, h6, div'))
    .filter((node) => isTargetMatch(node.textContent || '', normalizedTargets.value))
  const target = candidates[0] as HTMLElement | undefined
  if (target) target.classList.add('native-preview-highlight')
}

async function scrollToHighlight() {
  await nextTick()
  applyHtmlHighlight()
  const root = rootRef.value
  const target = root?.querySelector('.native-preview-highlight, .native-preview-row-highlight') as HTMLElement | null
  target?.scrollIntoView({ block: 'center', inline: 'nearest' })
}

watch(() => [props.kind, props.content, props.highlightTexts], () => {
  void scrollToHighlight()
}, { deep: true })

onMounted(() => {
  void scrollToHighlight()
})
</script>

<template>
  <div ref="rootRef" class="native-preview" :class="`native-preview-${kind}`">
    <div v-if="kind === 'html'" class="native-preview-html" v-html="sanitizedHtml"></div>
    <template v-else>
      <div
        v-for="block in blocks"
        :key="block.key"
        class="native-preview-block"
        :class="{ 'native-preview-highlight': block.highlighted, 'native-preview-line': block.type === 'text' }"
        v-html="block.html"
      ></div>
    </template>
  </div>
</template>

<style scoped>
.native-preview {
  height: 100%;
  min-height: 100%;
  overflow: auto;
  padding: 24px;
  color: #0f172a;
  line-height: 1.75;
}

.native-preview-block,
.native-preview-html :deep(p),
.native-preview-html :deep(li),
.native-preview-html :deep(td),
.native-preview-html :deep(th),
.native-preview-html :deep(pre),
.native-preview-html :deep(blockquote),
.native-preview-html :deep(h1),
.native-preview-html :deep(h2),
.native-preview-html :deep(h3),
.native-preview-html :deep(h4),
.native-preview-html :deep(h5),
.native-preview-html :deep(h6) {
  border-radius: 8px;
  padding: 2px 4px;
}

.native-preview-line {
  min-height: 1.75em;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
  font-size: 13px;
}

.native-preview :deep(h1),
.native-preview :deep(h2),
.native-preview :deep(h3) {
  margin: 0.8em 0 0.35em;
  font-weight: 700;
  line-height: 1.3;
}

.native-preview :deep(p),
.native-preview :deep(ul),
.native-preview :deep(ol),
.native-preview :deep(pre),
.native-preview :deep(blockquote),
.native-table-wrap {
  margin: 0.65em 0;
}

.native-preview :deep(pre) {
  overflow: auto;
  border-radius: 8px;
  background: #0f172a;
  color: #e2e8f0;
  padding: 12px;
}

.native-table-wrap {
  overflow-x: auto;
}

.native-preview :deep(table) {
  width: max-content;
  min-width: min(100%, 720px);
  border-collapse: collapse;
  background: #fff;
}

.native-preview :deep(th),
.native-preview :deep(td) {
  border: 1px solid #dbe4f0;
  padding: 8px 10px;
  text-align: left;
  vertical-align: top;
}

.native-preview :deep(th) {
  background: #f8fafc;
  font-weight: 700;
}

.native-preview-highlight,
.native-preview :deep(.native-preview-highlight),
.native-preview :deep(.native-preview-row-highlight > td) {
  background: rgba(251, 191, 36, 0.36);
  box-shadow: inset 0 0 0 1px rgba(245, 158, 11, 0.5);
}
</style>
