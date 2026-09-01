<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import CheckmarkCircleOutline from '@vicons/ionicons5/es/CheckmarkCircleOutline'
import ChevronDownOutline from '@vicons/ionicons5/es/ChevronDownOutline'
import ChevronUpOutline from '@vicons/ionicons5/es/ChevronUpOutline'
import GitCompareOutline from '@vicons/ionicons5/es/GitCompareOutline'
import RefreshOutline from '@vicons/ionicons5/es/RefreshOutline'
import { undoDshTaskChanges } from '../../platform'
import type { DshTaskChangeSet } from '../../platform/types'

const props = defineProps<{ sessionId: string; changes: DshTaskChangeSet; locale?: 'zh' | 'en' }>()
const emit = defineEmits<{
  (event: 'review', changes: DshTaskChangeSet, path?: string): void
  (event: 'undone', changes: DshTaskChangeSet): void
}>()
const current = ref(props.changes)
const expanded = ref(false)
const confirmUndo = ref(false)
const undoing = ref(false)
const error = ref('')
let confirmTimer: ReturnType<typeof setTimeout> | undefined
watch(() => props.changes, value => { current.value = value }, { deep: true })
const visibleFiles = computed(() => expanded.value ? current.value.files : current.value.files.slice(0, 3))
const remaining = computed(() => Math.max(0, current.value.files.length - visibleFiles.value.length))

function requestUndo() {
  if (!confirmUndo.value) {
    confirmUndo.value = true
    clearTimeout(confirmTimer)
    confirmTimer = setTimeout(() => { confirmUndo.value = false }, 5_000)
    return
  }
  void undo()
}
async function undo() {
  undoing.value = true; error.value = ''; confirmUndo.value = false
  try {
    current.value = await undoDshTaskChanges(props.sessionId, current.value.task_id)
    emit('undone', current.value)
  } catch (value) {
    error.value = value instanceof Error ? value.message : String(value)
  } finally { undoing.value = false }
}
onBeforeUnmount(() => clearTimeout(confirmTimer))
</script>

<template>
  <section class="change-card" :class="{ undone: current.undone }">
    <header>
      <div class="summary-icon"><CheckmarkCircleOutline v-if="current.undone" /><GitCompareOutline v-else /></div>
      <div class="summary-copy">
        <strong>{{ current.undone ? (locale === 'en' ? 'Changes undone' : '已撤销本次变更') : (locale === 'en' ? `Edited ${current.files.length} file(s)` : `已更新 ${current.files.length} 个文件`) }}</strong>
        <span v-if="!current.undone"><b>+{{ current.additions }}</b><i>-{{ current.deletions }}</i></span>
      </div>
      <button v-if="current.undo_available" type="button" class="undo-button" :class="{ confirm: confirmUndo }" :disabled="undoing" @click="requestUndo"><RefreshOutline />{{ undoing ? (locale === 'en' ? 'Undoing…' : '正在撤销…') : confirmUndo ? (locale === 'en' ? 'Confirm undo' : '确认撤销') : (locale === 'en' ? 'Undo' : '撤销') }}</button>
      <button v-if="!current.undone" type="button" class="review-button" @click="emit('review', current)">{{ locale === 'en' ? 'Review' : '评审' }}</button>
    </header>
    <div v-if="!current.undone" class="file-list">
      <button v-for="file in visibleFiles" :key="file.path" type="button" class="file-row" :title="file.path" @click="emit('review', current, file.path)">
        <span>{{ file.path }}</span>
        <code v-if="file.binary">BIN</code>
        <code v-else><b>+{{ file.additions || 0 }}</b><i>-{{ file.deletions || 0 }}</i></code>
      </button>
      <button v-if="remaining || expanded && current.files.length > 3" type="button" class="expand-button" @click="expanded = !expanded">
        {{ expanded ? (locale === 'en' ? 'Show less' : '收起') : (locale === 'en' ? `Show ${remaining} more` : `再显示 ${remaining} 个文件`) }}
        <ChevronUpOutline v-if="expanded" /><ChevronDownOutline v-else />
      </button>
    </div>
    <p v-if="error" class="undo-error">{{ error }}</p>
  </section>
</template>

<style scoped>
.change-card{width:100%;overflow:hidden;border:1px solid #dfe5ed;border-radius:12px;background:#fff;color:#334155;box-shadow:0 1px 2px #0f172a08}.change-card header{display:flex;min-height:54px;align-items:center;gap:9px;border-bottom:1px solid #edf0f4;padding:8px 10px}.summary-icon{display:grid;width:30px;height:30px;flex:none;place-items:center;border-radius:8px;background:#f1f5f9;color:#64748b}.summary-icon svg{width:17px}.summary-copy{display:flex;min-width:0;flex:1;flex-direction:column;gap:2px}.summary-copy strong{font-size:12px;font-weight:650}.summary-copy span{display:flex;gap:7px;font:10px ui-monospace,SFMono-Regular,Menlo,monospace}.summary-copy b,.file-row b{color:#16a34a}.summary-copy i,.file-row i{color:#dc2626;font-style:normal}.undo-button,.review-button{display:flex;height:32px;flex:none;align-items:center;justify-content:center;border-radius:8px;padding:0 10px;font-size:11px;font-weight:600;cursor:pointer}.undo-button{gap:4px;border:0;background:transparent;color:#64748b}.undo-button:hover{background:#f1f5f9;color:#334155}.undo-button.confirm{background:#fff7ed;color:#c2410c}.undo-button svg{width:13px}.review-button{border:1px solid #d5dde8;background:#fff;color:#334155}.review-button:hover{border-color:#93b4f8;background:#eff6ff;color:#1d4ed8}.file-list{padding:4px 0}.file-row{display:flex;width:100%;height:34px;align-items:center;gap:12px;border:0;background:transparent;padding:0 12px;color:#475569;text-align:left;cursor:pointer}.file-row:hover{background:#f8fafc}.file-row>span{min-width:0;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font:11px ui-monospace,SFMono-Regular,Menlo,monospace}.file-row code{display:flex;flex:none;gap:6px;color:#64748b;font:10px ui-monospace,SFMono-Regular,Menlo,monospace}.expand-button{display:flex;height:31px;align-items:center;gap:4px;border:0;background:transparent;padding:0 12px;color:#64748b;font-size:10px;cursor:pointer}.expand-button:hover{color:#1d4ed8}.expand-button svg{width:12px}.undo-error{margin:0;border-top:1px solid #fecaca;background:#fef2f2;padding:8px 12px;color:#b91c1c;font-size:10px;white-space:pre-wrap}.change-card.undone{border-color:#bbf7d0;background:#f0fdf4}.change-card.undone header{border:0}.change-card.undone .summary-icon{background:#dcfce7;color:#15803d}
:global(html.theme-dark) .change-card{border-color:#334155;background:#111827;color:#e2e8f0}:global(html.theme-dark) .change-card header{border-color:#293548}:global(html.theme-dark) .summary-icon{background:#1e293b;color:#94a3b8}:global(html.theme-dark) .file-row{color:#cbd5e1}:global(html.theme-dark) .file-row:hover{background:#172033}:global(html.theme-dark) .undo-button{color:#94a3b8}:global(html.theme-dark) .undo-button:hover{background:#263248;color:#e2e8f0}:global(html.theme-dark) .review-button{border-color:#475569;background:#172033;color:#cbd5e1}:global(html.theme-dark) .change-card.undone{border-color:#166534;background:#052e16}:global(html.theme-dark) .change-card.undone .summary-icon{background:#14532d;color:#bbf7d0}
</style>
