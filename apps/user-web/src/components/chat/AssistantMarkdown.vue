<script setup lang="ts">
import { computed } from 'vue'
import { useMessage } from 'naive-ui'
import { renderAssistantMarkdown } from '../../utils/assistantMarkdown'
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

const html = computed(() => renderAssistantMarkdown(props.content, { workspaceFileReferences: props.fileReferences, artifactPaths: props.artifactPaths }))
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
        copyButton.setAttribute('aria-label', 'Copy code')
        copyButton.title = 'Copy code'
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
    class="assistant-markdown prose prose-slate max-w-none prose-p:leading-7 prose-headings:font-semibold prose-headings:text-slate-900 prose-a:text-blue-600 hover:prose-a:text-blue-500"
    :class="{ 'assistant-markdown-compact': compact }"
    v-html="html"
    @click="handleClick"
    @keydown="openFileByKeyboard"
  ></div>
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
  line-height: 1.75rem;
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
.assistant-markdown :deep(table) { display: block; max-width: 100%; overflow-x: auto; border-color: var(--assistant-rule); font-size: .94em; }
.assistant-markdown :deep(th), .assistant-markdown :deep(td) { border-color: var(--assistant-rule); }
.assistant-markdown :deep(th) { background: var(--assistant-code-header-bg); color: inherit; }
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

.assistant-markdown-compact {
  font-size: 14px;
  line-height: 1.72;
}

.assistant-markdown-compact :deep(p) {
  margin-top: .65em;
  margin-bottom: .65em;
  line-height: 1.72;
}

.assistant-markdown-compact :deep(h1),
.assistant-markdown-compact :deep(h2),
.assistant-markdown-compact :deep(h3),
.assistant-markdown-compact :deep(h4) {
  margin-top: 1.25em;
  margin-bottom: .55em;
  line-height: 1.35;
}

.assistant-markdown-compact :deep(h1) { font-size: 1.18em; }
.assistant-markdown-compact :deep(h2) { font-size: 1.12em; }
.assistant-markdown-compact :deep(h3),
.assistant-markdown-compact :deep(h4) { font-size: 1.06em; }
.assistant-markdown-compact :deep(ul),
.assistant-markdown-compact :deep(ol) { margin-top: .55em; margin-bottom: .55em; }
.assistant-markdown-compact :deep(li) { margin-top: .2em; margin-bottom: .2em; }
.assistant-markdown-compact :deep(pre) { font-size: .9em; line-height: 1.6; }
</style>
