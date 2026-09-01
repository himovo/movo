<script setup lang="ts">
import { computed } from 'vue'
import { highlightCode } from './codeSyntax'

const props = defineProps<{ content: string; path: string; language?: string }>()
const highlighted = computed(() => highlightCode(props.content, props.path, props.language))
</script>

<template>
  <pre class="code-preview"><code v-html="highlighted"></code></pre>
</template>

<style scoped>
.code-preview{box-sizing:border-box;min-height:100%;margin:0;padding:15px 16px;background:#fff;color:#334155;font:12px/1.7 ui-monospace,SFMono-Regular,Menlo,monospace;tab-size:2;white-space:pre;overflow:auto}.code-preview :deep(.hljs-comment),.code-preview :deep(.hljs-quote){color:#94a3b8}.code-preview :deep(.hljs-keyword),.code-preview :deep(.hljs-selector-tag),.code-preview :deep(.hljs-literal){color:#7c3aed}.code-preview :deep(.hljs-string),.code-preview :deep(.hljs-attr){color:#15803d}.code-preview :deep(.hljs-number),.code-preview :deep(.hljs-attribute){color:#c2410c}.code-preview :deep(.hljs-title),.code-preview :deep(.hljs-function){color:#2563eb}.code-preview :deep(.hljs-built_in),.code-preview :deep(.hljs-type){color:#a16207}.code-preview :deep(.hljs-meta),.code-preview :deep(.hljs-tag){color:#0891b2}:global(html.theme-dark) .code-preview{background:#0b1220;color:#d7e0ee}:global(html.theme-dark) .code-preview :deep(.hljs-comment),:global(html.theme-dark) .code-preview :deep(.hljs-quote){color:#718096}:global(html.theme-dark) .code-preview :deep(.hljs-keyword),:global(html.theme-dark) .code-preview :deep(.hljs-selector-tag),:global(html.theme-dark) .code-preview :deep(.hljs-literal){color:#c792ea}:global(html.theme-dark) .code-preview :deep(.hljs-string),:global(html.theme-dark) .code-preview :deep(.hljs-attr){color:#c3e88d}:global(html.theme-dark) .code-preview :deep(.hljs-number),:global(html.theme-dark) .code-preview :deep(.hljs-attribute){color:#f78c6c}:global(html.theme-dark) .code-preview :deep(.hljs-title),:global(html.theme-dark) .code-preview :deep(.hljs-function){color:#82aaff}:global(html.theme-dark) .code-preview :deep(.hljs-built_in),:global(html.theme-dark) .code-preview :deep(.hljs-type){color:#ffcb6b}:global(html.theme-dark) .code-preview :deep(.hljs-meta),:global(html.theme-dark) .code-preview :deep(.hljs-tag){color:#89ddff}
</style>
