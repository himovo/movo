<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { previewDshWorkspaceFile } from '../../platform'
import type { DshFilePreview } from '../../platform/types'
import CodeFileTypeIcon from './CodeFileTypeIcon.vue'
import CodeSyntaxPreview from './CodeSyntaxPreview.vue'

const props = defineProps<{ sessionId: string; path: string; locale?: 'zh' | 'en' }>()
const preview = ref<DshFilePreview | null>(null)
const loading = ref(false)
const error = ref('')

async function load(): Promise<void> {
  if (!props.path) { preview.value = null; return }
  loading.value = true; error.value = ''
  try { preview.value = await previewDshWorkspaceFile(props.sessionId, props.path) }
  catch (value) { error.value = value instanceof Error ? value.message : String(value); preview.value = null }
  finally { loading.value = false }
}

watch(() => [props.sessionId, props.path] as const, load)
onMounted(load)
</script>

<template>
  <section class="file-preview">
    <div v-if="preview" class="preview-heading"><div class="preview-file"><CodeFileTypeIcon :path="preview.path" /><strong>{{ preview.name }}</strong></div><span>{{ preview.language || preview.mime_type }} · {{ preview.size }} B</span></div>
    <div v-if="error" class="state error">{{ error }}</div>
    <div v-else-if="loading" class="state">{{ locale === 'en' ? 'Loading…' : '正在读取…' }}</div>
    <img v-else-if="preview?.kind === 'image'" :src="preview.content" :alt="preview.name" class="image-preview" />
    <CodeSyntaxPreview v-else-if="preview?.kind === 'text'" :content="preview.content" :path="preview.path" :language="preview.language" />
    <div v-else-if="preview?.kind === 'binary'" class="state">{{ locale === 'en' ? 'Binary files cannot be previewed.' : '该二进制文件暂不支持预览。' }}</div>
    <div v-else class="state">{{ locale === 'en' ? 'Select a file to preview it.' : '选择文件后在此预览。' }}</div>
    <div v-if="preview?.truncated" class="truncated">{{ locale === 'en' ? 'Preview truncated for safety.' : '文件较大，仅显示安全范围内的内容。' }}</div>
  </section>
</template>

<style scoped>
.file-preview{min-width:0;height:100%;overflow:auto;background:#fff}.preview-heading{position:sticky;z-index:2;top:0;display:flex;min-height:48px;align-items:center;justify-content:space-between;gap:12px;border-bottom:1px solid #e2e8f0;background:#fff;padding:0 14px;color:#1e293b}.preview-file{display:flex;min-width:0;align-items:center;gap:7px}.preview-file strong{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:12px}.preview-heading>span{flex:none;color:#94a3b8;font:10px ui-monospace,SFMono-Regular,Menlo,monospace}.state{display:grid;height:100%;place-items:center;padding:24px;color:#94a3b8;font-size:12px}.state.error{color:#dc2626}.image-preview{display:block;max-width:100%;max-height:calc(100% - 48px);margin:auto;padding:18px;object-fit:contain}.truncated{position:sticky;bottom:0;background:#fff7ed;padding:7px 12px;color:#9a3412;font-size:11px}:global(html.theme-dark) .file-preview{background:#0b1220}:global(html.theme-dark) .preview-heading{border-color:#263248;background:#111a2a;color:#e2e8f0}:global(html.theme-dark) .preview-heading>span{color:#8491a5}:global(html.theme-dark) .state.error{color:#fca5a5}:global(html.theme-dark) .truncated{background:#7c2d12;color:#ffedd5}
</style>
