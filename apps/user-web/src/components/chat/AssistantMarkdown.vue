<script setup lang="ts">
import { computed } from 'vue'
import { renderAssistantMarkdown } from '../../utils/assistantMarkdown'

const props = withDefaults(defineProps<{ content: string; compact?: boolean; fileReferences?: boolean }>(), {
  compact: true,
  fileReferences: false,
})
const emit = defineEmits<{ (event: 'open-file', path: string): void }>()

const html = computed(() => renderAssistantMarkdown(props.content, { workspaceFileReferences: props.fileReferences }))

function fileReference(target: EventTarget | null): HTMLElement | null {
  return target instanceof Element ? target.closest<HTMLElement>('[data-workspace-file]') : null
}
function openFile(event: Event) {
  const reference = fileReference(event.target)
  const path = reference?.dataset.workspaceFile
  if (path) emit('open-file', path)
}
function openFileByKeyboard(event: KeyboardEvent) {
  if (!['Enter', ' '].includes(event.key)) return
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
    @click="openFile"
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
  color: #111827;
  line-height: 1.75rem;
  overflow-wrap: anywhere;
}

.assistant-markdown :deep(.assistant-code-block) {
  border: 1px solid var(--assistant-code-border);
  background: var(--assistant-code-bg);
  box-shadow: 0 1px 2px rgba(15, 23, 42, .05);
}

.assistant-markdown :deep(.assistant-code-header) {
  border-bottom: 1px solid var(--assistant-code-divider);
  background: var(--assistant-code-header-bg);
}

.assistant-markdown :deep(.assistant-code-language) { color: var(--assistant-code-label); }
.assistant-markdown :deep(.assistant-code-scroll) { background: var(--assistant-code-bg); }
.assistant-markdown :deep(.assistant-code-content) {
  margin: 0;
  border: 0;
  background: transparent;
  padding: 0;
  color: var(--assistant-code-text);
  text-shadow: none;
}

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

:global(html.theme-dark) .assistant-markdown {
  --assistant-code-bg: #0f172a;
  --assistant-code-header-bg: #182235;
  --assistant-code-border: #2a3850;
  --assistant-code-divider: #334155;
  --assistant-code-label: #94a3b8;
  --assistant-code-text: #e2e8f0;
}
:global(html.theme-dark) .assistant-markdown :deep(.assistant-inline-code) { border-color:#334155; background:#172033; color:#cbd5e1; }
:global(html.theme-dark) .assistant-markdown :deep(.assistant-file-reference) { border-color:#294c78; background:#102542; color:#8ec5ff; }
:global(html.theme-dark) .assistant-markdown :deep(.assistant-file-reference:hover) { border-color:#3b6fa8; background:#143052; color:#bfdbfe; }

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
