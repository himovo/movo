<script setup lang="ts">
import { useMessage } from 'naive-ui'
import AssistantMarkdownTree from './AssistantMarkdownTree'
import { copyTextToClipboard } from '../../utils/copyTextToClipboard'
import { t } from '../../composables/i18n'

const props = withDefaults(defineProps<{ content: string; compact?: boolean; fileReferences?: boolean; artifactPaths?: Record<string, string> }>(), {
  compact: true,
  fileReferences: false,
})
const emit = defineEmits<{
  (event: 'open-file', path: string): void
  (event: 'download-artifact', path: string): void
  (event: 'image-preview', payload: { src: string; alt: string }): void
}>()

const message = useMessage()

function fileReference(target: EventTarget | null): HTMLElement | null {
  return target instanceof Element ? target.closest<HTMLElement>('[data-workspace-file]') : null
}
async function handleClick(event: Event) {
  const artifact = event.target instanceof Element ? event.target.closest<HTMLElement>('[data-artifact-path]') : null
  if (artifact?.dataset.artifactPath) {
    event.preventDefault()
    emit('download-artifact', artifact.dataset.artifactPath)
    return
  }
  if (event.target instanceof HTMLImageElement) {
    event.preventDefault()
    emit('image-preview', { src: event.target.currentSrc || event.target.src, alt: event.target.alt })
    return
  }
  const copyButton = event.target instanceof Element ? event.target.closest<HTMLButtonElement>('.assistant-code-copy') : null
  if (copyButton) {
    const code = copyButton.closest('.assistant-code-block')?.querySelector('code')?.textContent
    if (code == null) return
    try {
      await copyTextToClipboard(code)
      copyButton.dataset.copied = 'true'
      copyButton.setAttribute('aria-label', t('legacy.copied'))
      copyButton.title = t('legacy.copied')
      window.setTimeout(() => {
        copyButton.removeAttribute('data-copied')
        copyButton.setAttribute('aria-label', t('chat.copy_code'))
        copyButton.title = t('chat.copy_code')
      }, 1800)
    } catch {
      copyButton.title = t('chat.code_copy_failed')
      message.error(t('chat.code_copy_failed'))
    }
    return
  }
  const reference = fileReference(event.target)
  const path = reference?.dataset.workspaceFile
  if (path) emit('open-file', path)
}
function openFileByKeyboard(event: KeyboardEvent) {
  if (!['Enter', ' '].includes(event.key)) return
  if (event.target instanceof HTMLImageElement) {
    event.preventDefault()
    emit('image-preview', { src: event.target.currentSrc || event.target.src, alt: event.target.alt })
    return
  }
  const reference = fileReference(event.target)
  const path = reference?.dataset.workspaceFile
  if (!path) return
  event.preventDefault()
  emit('open-file', path)
}
</script>

<template>
  <div
    class="assistant-markdown prose prose-slate max-w-none prose-headings:font-bold prose-headings:text-slate-900 prose-a:text-blue-600 hover:prose-a:text-blue-500"
    :class="{ 'assistant-markdown-compact': compact }"
    @click="handleClick"
    @keydown="openFileByKeyboard"
  >
    <AssistantMarkdownTree
      :content="props.content"
      :file-references="props.fileReferences"
      :artifact-paths="props.artifactPaths || {}"
    />
  </div>
</template>

<style scoped>
.assistant-markdown {
  --assistant-code-bg: #f8fafc;
  --assistant-code-header-bg: #f1f5f9;
  --assistant-code-border: #dbe3ee;
  --assistant-code-divider: #e2e8f0;
  --assistant-code-label: #64748b;
  --assistant-code-text: #334155;
  --assistant-copy-hover: #e2e8f0;
  --assistant-copy-text: #475569;
  --assistant-rule: #d7dee8;
  --assistant-quote-bg: #f6f8fb;
  --assistant-quote-border: #96afcf;
  color: #111827;
  line-height: 2;
  font-family: Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
  overflow-wrap: anywhere;
}

.assistant-markdown :deep(.assistant-code-block) {
  margin: 1.15em 0;
  border: 1px solid var(--assistant-code-border);
  border-radius: 10px;
  background: var(--assistant-code-bg);
  overflow: hidden;
  box-shadow: 0 1px 2px rgba(15, 23, 42, .05);
}

.assistant-markdown :deep(.assistant-code-header) {
  min-height: 39px;
  padding: 3px 7px 3px 14px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid var(--assistant-code-divider);
  background: var(--assistant-code-header-bg);
}

.assistant-markdown :deep(.assistant-code-language) { color: var(--assistant-code-label); font: 600 11px/1.3 ui-sans-serif, system-ui, sans-serif; letter-spacing: .07em; }
.assistant-markdown :deep(.assistant-code-copy) {
  width: 32px;
  height: 32px;
  border: 0;
  border-radius: 7px;
  background: transparent;
  color: var(--assistant-copy-text);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: background-color .15s ease, color .15s ease;
}
.assistant-markdown :deep(.assistant-code-copy:hover),
.assistant-markdown :deep(.assistant-code-copy[data-copied="true"]) { background: var(--assistant-copy-hover); color: var(--assistant-code-text); }
.assistant-markdown :deep(.assistant-code-copy:focus-visible) { outline: 2px solid #3b82f6; outline-offset: 1px; }
.assistant-markdown :deep(.assistant-code-copy svg) { width: 16px; height: 16px; }
.assistant-markdown :deep(.assistant-code-check-icon) { display: none; }
.assistant-markdown :deep(.assistant-code-copy[data-copied="true"] .assistant-code-copy-icon) { display: none; }
.assistant-markdown :deep(.assistant-code-copy[data-copied="true"] .assistant-code-check-icon) { display: block; }
.assistant-markdown :deep(.assistant-code-scroll) { background: var(--assistant-code-bg); overflow-x: auto; }
.assistant-markdown :deep(.assistant-code-content) {
  margin: 0;
  border: 0;
  background: transparent;
  padding: 15px 17px 17px;
  color: var(--assistant-code-text);
  text-shadow: none;
  font: 12.5px/1.65 ui-monospace, SFMono-Regular, Consolas, 'Liberation Mono', monospace;
  white-space: pre;
  overflow: visible;
}
.assistant-markdown :deep(.assistant-code-content code) { background: none; padding: 0; border: 0; color: inherit; font: inherit; white-space: inherit; }
.assistant-markdown :deep(.hljs-keyword), .assistant-markdown :deep(.hljs-selector-tag), .assistant-markdown :deep(.hljs-literal) { color: #6d28d9; }
.assistant-markdown :deep(.hljs-string), .assistant-markdown :deep(.hljs-attr), .assistant-markdown :deep(.hljs-template-variable) { color: #047857; }
.assistant-markdown :deep(.hljs-comment), .assistant-markdown :deep(.hljs-quote) { color: #64748b; }
.assistant-markdown :deep(.hljs-number), .assistant-markdown :deep(.hljs-built_in) { color: #a34b00; }
.assistant-markdown :deep(.hljs-title), .assistant-markdown :deep(.hljs-function), .assistant-markdown :deep(.hljs-type), .assistant-markdown :deep(.hljs-selector-class) { color: #1d4ed8; }
.assistant-markdown :deep(.hljs-variable), .assistant-markdown :deep(.hljs-params) { color: #334155; }

.assistant-markdown :deep(a) { color: #1d5fb8; text-underline-offset: 3px; }
.assistant-markdown :deep(a:hover) { color: #174a91; }
.assistant-markdown :deep(img) { cursor: zoom-in; }
.assistant-markdown :deep(img:focus-visible) { outline: 2px solid #3b82f6; outline-offset: 3px; }
.assistant-markdown :deep(hr) { border-color: var(--assistant-rule); }
.assistant-markdown :deep(blockquote) { margin: 1em 0; padding: .35em 1em; border-left: 3px solid var(--assistant-quote-border); background: var(--assistant-quote-bg); color: inherit; }
.assistant-markdown :deep(.assistant-table-scroll) { max-width: 100%; margin: 1.1em 0; overflow-x: auto; border: 1px solid var(--assistant-rule); border-radius: 10px; }
.assistant-markdown :deep(.assistant-table-scroll:focus-visible) { outline: 2px solid #3b82f6; outline-offset: 2px; }
.assistant-markdown :deep(table) { width: 100%; min-width: max-content; margin: 0; border-collapse: collapse; font-size: .92em; line-height: 1.55; }
.assistant-markdown :deep(th), .assistant-markdown :deep(td) { padding: .6em .85em; border-bottom: 1px solid var(--assistant-rule); border-right: 1px solid var(--assistant-rule); text-align: left; vertical-align: top; }
.assistant-markdown :deep(th:last-child), .assistant-markdown :deep(td:last-child) { border-right: 0; }
.assistant-markdown :deep(tbody tr:last-child td) { border-bottom: 0; }
.assistant-markdown :deep(th) { background: var(--assistant-code-header-bg); color: inherit; font-weight: 650; white-space: nowrap; }
.assistant-markdown :deep(tbody tr:nth-child(even)) { background: #f8fafc; }
.assistant-markdown :deep(ul) { list-style-type: disc; padding-left: 1.5em; }
.assistant-markdown :deep(ol) { list-style-type: decimal; padding-left: 1.65em; }
.assistant-markdown :deep(ul ul) { list-style-type: circle; }
.assistant-markdown :deep(ul ul ul) { list-style-type: square; }
.assistant-markdown :deep(li::marker) { color: #64748b; font-weight: 600; }
.assistant-markdown :deep(h1), .assistant-markdown :deep(h2), .assistant-markdown :deep(h3), .assistant-markdown :deep(h4), .assistant-markdown :deep(strong) { color: inherit; }

.assistant-markdown :deep(.assistant-inline-code) {
  border: 1px solid #dfe4eb;
  border-radius: 5px;
  background: #f4f6f8;
  padding: .08em .38em;
  color: #475569;
  font: .92em/1.55 ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  overflow-wrap: anywhere;
}
.assistant-markdown :deep(.assistant-file-reference) {
  border-color: #cfe0f7;
  background: #f1f7ff;
  color: #2563a9;
  cursor: pointer;
  transition: background-color .18s ease, border-color .18s ease, color .18s ease;
}
.assistant-markdown :deep(.assistant-file-reference:hover) { border-color:#9fc2ef; background:#e8f2ff; color:#164f91; }
.assistant-markdown :deep(.assistant-file-reference:focus-visible) { outline:2px solid #3b82f6; outline-offset:2px; }

:global(html.theme-dark .assistant-markdown){
  --assistant-code-bg: #0f172a;
  --assistant-code-header-bg: #182235;
  --assistant-code-border: #2a3850;
  --assistant-code-divider: #334155;
  --assistant-code-label: #94a3b8;
  --assistant-code-text: #e2e8f0;
  --assistant-copy-hover: #2a3a50;
  --assistant-copy-text: #b2c1d5;
  --assistant-rule: #34445c;
  --assistant-quote-bg: #1a2a40;
  --assistant-quote-border: #5c85b5;
  color: #e2eaf5;
}
:global(html.theme-dark .assistant-markdown a){ color: #9dc8ff; }
:global(html.theme-dark .assistant-markdown a:hover){ color: #c5dfff; }
:global(html.theme-dark .assistant-markdown p), :global(html.theme-dark .assistant-markdown li), :global(html.theme-dark .assistant-markdown td), :global(html.theme-dark .assistant-markdown blockquote){ color: #e2eaf5; }
:global(html.theme-dark .assistant-markdown h1), :global(html.theme-dark .assistant-markdown h2), :global(html.theme-dark .assistant-markdown h3), :global(html.theme-dark .assistant-markdown h4), :global(html.theme-dark .assistant-markdown strong), :global(html.theme-dark .assistant-markdown th){ color: #f0f5fc; }
:global(html.theme-dark .assistant-markdown .hljs-keyword), :global(html.theme-dark .assistant-markdown .hljs-selector-tag), :global(html.theme-dark .assistant-markdown .hljs-literal){ color: #c4b5fd; }
:global(html.theme-dark .assistant-markdown .hljs-string), :global(html.theme-dark .assistant-markdown .hljs-attr), :global(html.theme-dark .assistant-markdown .hljs-template-variable){ color: #94dfb7; }
:global(html.theme-dark .assistant-markdown .hljs-comment), :global(html.theme-dark .assistant-markdown .hljs-quote){ color: #a4b3c7; }
:global(html.theme-dark .assistant-markdown .hljs-number), :global(html.theme-dark .assistant-markdown .hljs-built_in){ color: #f7bd88; }
:global(html.theme-dark .assistant-markdown .hljs-title), :global(html.theme-dark .assistant-markdown .hljs-function), :global(html.theme-dark .assistant-markdown .hljs-type), :global(html.theme-dark .assistant-markdown .hljs-selector-class){ color: #a5c8ff; }
:global(html.theme-dark .assistant-markdown .hljs-variable), :global(html.theme-dark .assistant-markdown .hljs-params){ color: #dce7f5; }
:global(html.theme-dark .assistant-markdown .assistant-inline-code){ border-color:#334155; background:#172033; color:#cbd5e1; }
:global(html.theme-dark .assistant-markdown .assistant-file-reference){ border-color:#294c78; background:#102542; color:#8ec5ff; }
:global(html.theme-dark .assistant-markdown .assistant-file-reference:hover){ border-color:#3b6fa8; background:#143052; color:#bfdbfe; }
:global(html.theme-dark .assistant-markdown tbody tr:nth-child(even)){ background:#182235; }
:global(html.theme-dark .assistant-markdown li::marker){ color:#9fb0c8; }

.assistant-markdown-compact {
  font-size: 15px;
  line-height: 2;
}

.assistant-markdown-compact :deep(.assistant-markdown-tree > p) {
  margin-top: 1em;
  margin-bottom: 1em;
  line-height: 2;
}

.assistant-markdown-compact :deep(.assistant-markdown-tree > h1),
.assistant-markdown-compact :deep(.assistant-markdown-tree > h2),
.assistant-markdown-compact :deep(.assistant-markdown-tree > h3),
.assistant-markdown-compact :deep(.assistant-markdown-tree > h4) {
  margin-top: 1.6em;
  margin-bottom: .7em;
  line-height: 1.35;
  letter-spacing: -.015em;
  font-weight: 700;
}

.assistant-markdown-compact :deep(.assistant-markdown-tree > h1) { font-size: 1.4em; }
.assistant-markdown-compact :deep(.assistant-markdown-tree > h2) { font-size: 1.26em; }
.assistant-markdown-compact :deep(.assistant-markdown-tree > h3),
.assistant-markdown-compact :deep(.assistant-markdown-tree > h4) { font-size: 1.12em; }
.assistant-markdown-compact :deep(.assistant-markdown-tree > ul),
.assistant-markdown-compact :deep(.assistant-markdown-tree > ol) { margin-top: .7em; margin-bottom: .7em; padding-left: 1.65em; }
.assistant-markdown-compact :deep(li) { margin-top: .3em; margin-bottom: .3em; padding-left: .15em; }
.assistant-markdown-compact :deep(li > p) { margin: .2em 0; }
.assistant-markdown-compact :deep(.assistant-markdown-tree > :first-child) { margin-top: 0; }
.assistant-markdown-compact :deep(.assistant-markdown-tree > :last-child) { margin-bottom: 0; }
.assistant-markdown-compact :deep(pre) { font-size: .9em; line-height: 1.6; }
</style>
