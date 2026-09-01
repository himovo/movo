<script setup lang="ts">
import { computed } from 'vue'
import { highlightCode } from './codeSyntax'
import { parseUnifiedDiff } from './unifiedDiff'

const props = defineProps<{ diff: string; path: string }>()
const lines = computed(() => parseUnifiedDiff(props.diff))
const lineNumber = (line: { oldLine: number | null; newLine: number | null }) => line.newLine ?? line.oldLine ?? ''
const highlightedLine = (line: { content: string; kind: string }) => {
  if (!['add', 'delete', 'context'].includes(line.kind)) return line.content.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  const marker = line.content[0] || ''
  return `<span class="diff-marker">${marker}</span>${highlightCode(line.content.slice(1), props.path)}`
}
</script>

<template>
  <div class="diff-table" role="table" aria-label="Code diff">
    <div v-for="line in lines" :key="line.id" class="diff-row" :class="line.kind" role="row">
      <span class="line-number" role="cell">{{ lineNumber(line) }}</span>
      <code role="cell" v-html="highlightedLine(line) || ' '"></code>
    </div>
  </div>
</template>

<style scoped>
.diff-table{width:max-content;min-width:100%;padding:10px 0 18px;color:#334155;font:11px/1.65 ui-monospace,SFMono-Regular,Menlo,monospace}.diff-row{display:grid;min-height:18px;grid-template-columns:44px minmax(max-content,1fr)}.line-number{position:sticky;z-index:1;left:0;display:block;box-sizing:border-box;background:#fff;padding:0 9px 0 4px;border-right:1px solid #e2e8f0;color:#94a3b8;text-align:right;user-select:none}.diff-row code{display:block;padding:0 14px;white-space:pre}.diff-row.add{background:#ecfdf3;color:#166534}.diff-row.delete{background:#fff1f2;color:#b42318}.diff-row.hunk{margin:5px 0;background:#eff6ff;color:#2563eb}.diff-row.hunk .line-number{background:#eff6ff}.diff-row.add .line-number{background:#dcfce7;color:#4d8064}.diff-row.delete .line-number{background:#ffe4e6;color:#a65660}.diff-row :deep(.diff-marker){display:inline-block;width:10px;color:inherit}.diff-row :deep(.hljs-comment),.diff-row :deep(.hljs-quote){color:#64748b}.diff-row :deep(.hljs-keyword),.diff-row :deep(.hljs-literal){color:#7c3aed}.diff-row :deep(.hljs-string),.diff-row :deep(.hljs-attr){color:#15803d}.diff-row :deep(.hljs-number),.diff-row :deep(.hljs-attribute){color:#c2410c}.diff-row.meta{color:#64748b}:global(html.theme-dark) .diff-table{color:#d7e0ee}:global(html.theme-dark) .line-number{background:#0b1220;border-color:#263348;color:#526077}:global(html.theme-dark) .diff-row.add{background:#063420;color:#bbf7d0}:global(html.theme-dark) .diff-row.delete{background:#45151c;color:#fecaca}:global(html.theme-dark) .diff-row.hunk{background:#10233d;color:#8ec5ff}:global(html.theme-dark) .diff-row.hunk .line-number{background:#10233d}:global(html.theme-dark) .diff-row.add .line-number{background:#092a1d;color:#4d8064}:global(html.theme-dark) .diff-row.delete .line-number{background:#34171d;color:#8e5660}:global(html.theme-dark) .diff-row :deep(.hljs-comment),:global(html.theme-dark) .diff-row :deep(.hljs-quote){color:#8a9bb4}:global(html.theme-dark) .diff-row :deep(.hljs-keyword),:global(html.theme-dark) .diff-row :deep(.hljs-literal){color:#e0aaff}:global(html.theme-dark) .diff-row :deep(.hljs-string),:global(html.theme-dark) .diff-row :deep(.hljs-attr){color:#d0eaa2}:global(html.theme-dark) .diff-row :deep(.hljs-number),:global(html.theme-dark) .diff-row :deep(.hljs-attribute){color:#f7b38c}:global(html.theme-dark) .diff-row.meta{color:#8795aa}
</style>
