<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { getDshTaskFileDiff, getDshWorkspaceFileDiff } from '../../platform'
import type { DshTaskChangeSet } from '../../platform/types'
import CodeFileTypeIcon from './CodeFileTypeIcon.vue'
import UnifiedDiffView from './UnifiedDiffView.vue'

const props = defineProps<{ sessionId: string; path: string; taskChanges?: DshTaskChangeSet; locale?: 'zh' | 'en' }>()
const diff = ref('')
const truncated = ref(false)
const loading = ref(false)
const error = ref('')
const name = computed(() => props.path.split('/').pop() || props.path)
const directory = computed(() => props.path.includes('/') ? props.path.slice(0, props.path.lastIndexOf('/')) : '')

async function load(): Promise<void> {
  loading.value = true; error.value = ''; diff.value = ''; truncated.value = false
  try {
    if (props.taskChanges) {
      const result = await getDshTaskFileDiff(props.sessionId, props.taskChanges.task_id, props.path)
      diff.value = result.diff
    } else {
      const result = await getDshWorkspaceFileDiff(props.sessionId, props.path)
      diff.value = result.diff; truncated.value = result.truncated
    }
  } catch (value) { error.value = value instanceof Error ? value.message : String(value) }
  finally { loading.value = false }
}

watch(() => [props.sessionId, props.path, props.taskChanges?.task_id] as const, load)
onMounted(load)
</script>

<template>
  <section class="diff-preview">
    <div class="diff-heading"><CodeFileTypeIcon :path="path" /><div><strong>{{ name }}</strong><span v-if="directory">{{ directory }}</span></div></div>
    <div v-if="error" class="state error">{{ error }}</div>
    <div v-else-if="loading" class="state">{{ locale === 'en' ? 'Loading diff…' : '正在读取变更…' }}</div>
    <UnifiedDiffView v-else-if="diff" :diff="diff" :path="path" />
    <div v-else class="state">{{ locale === 'en' ? 'No diff is available.' : '暂无可显示的变更。' }}</div>
    <div v-if="truncated" class="notice">{{ locale === 'en' ? 'Diff truncated for safety.' : '变更较大，仅显示安全范围内的内容。' }}</div>
  </section>
</template>

<style scoped>
.diff-preview{height:100%;min-width:0;overflow:auto;background:#fff}.diff-heading{position:sticky;z-index:3;top:0;display:flex;height:52px;align-items:center;gap:9px;border-bottom:1px solid #e2e8f0;background:#fff;padding:0 14px}.diff-heading>div{display:flex;min-width:0;flex-direction:column;gap:2px}.diff-heading strong,.diff-heading span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.diff-heading strong{color:#1e293b;font-size:12px}.diff-heading span{color:#94a3b8;font:9px ui-monospace,SFMono-Regular,Menlo,monospace}.state{display:grid;min-height:120px;place-items:center;padding:20px;color:#94a3b8;font-size:12px}.state.error{color:#dc2626}.notice{position:sticky;bottom:0;background:#fff7ed;padding:7px 12px;color:#9a3412;font-size:11px}:global(html.theme-dark) .diff-preview{background:#0b1220}:global(html.theme-dark) .diff-heading{border-color:#263248;background:#111a2a}:global(html.theme-dark) .diff-heading strong{color:#e2e8f0}:global(html.theme-dark) .state.error{color:#fca5a5}
</style>
