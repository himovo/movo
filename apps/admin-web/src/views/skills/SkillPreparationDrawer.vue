<template>
  <n-drawer :show="show" :width="900" placement="right" @update:show="emit('update:show', $event)">
    <n-drawer-content :title="`${t('skillDeps.records.title')} · ${skillName}`" closable>
      <n-spin :show="loading">
        <div v-if="loadError" class="load-error">{{ loadError }} <n-button text type="primary" @click="refresh(true)">{{ t('skillDeps.records.refresh') }}</n-button></div>
        <n-empty v-else-if="!records.length" :description="t('skillDeps.records.empty')" />
        <div v-else class="records-layout">
          <nav class="records-list" :aria-label="t('skillDeps.records.title')">
            <button v-for="record in records" :key="record.id" class="record-choice" :class="{ selected: record.id === selectedId }" type="button" @click="select(record.id)">
              <span>{{ formatTime(record.startedAt) }}</span>
              <n-tag size="tiny" :type="statusType(record.status)">{{ statusText(record.status) }}</n-tag>
              <small>{{ record.id.slice(0, 12) }}</small>
            </button>
          </nav>
          <section class="record-content">
            <template v-if="selected">
              <div class="record-meta">
                <div><span>{{ t('skillDeps.records.startedAt') }}</span><strong>{{ formatTime(selected.startedAt) }}</strong></div>
                <div><span>{{ t('skillDeps.records.finishedAt') }}</span><strong>{{ formatTime(selected.finishedAt) }}</strong></div>
                <div><span>{{ t('skillDeps.records.status') }}</span><strong>{{ statusText(selected.status) }}</strong></div>
                <div><span>{{ t('skillDeps.records.id') }}</span><code>{{ selected.id }}</code></div>
                <div><span>{{ t('skillDeps.records.digest') }}</span><code :title="selected.digest">{{ selected.digest.slice(0, 16) }}</code></div>
                <div><span>{{ t('skillDeps.records.baseImage') }}</span><code :title="selected.baseImageId">{{ selected.baseImageId.slice(0, 20) || '—' }}</code></div>
              </div>
              <div class="log-head"><strong>{{ t('skillDeps.records.log') }}</strong><div class="log-actions"><n-button size="small" secondary @click="refresh(true)">{{ t('skillDeps.records.refresh') }}</n-button><n-button size="small" secondary :loading="downloading" @click="downloadSelected">{{ t('skillDeps.records.download') }}</n-button></div></div>
              <p v-if="selected.truncated" class="log-note">{{ t('skillDeps.records.truncated') }}</p>
              <pre class="log-view" role="log"><code>{{ selected.log || t('skillDeps.records.logPending') }}</code></pre>
            </template>
          </section>
        </div>
      </n-spin>
    </n-drawer-content>
  </n-drawer>
</template>

<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { NButton, NDrawer, NDrawerContent, NEmpty, NSpin, NTag, useMessage } from 'naive-ui'
import { fetchSkillPreparationRecord, fetchSkillPreparationRecords, type SkillPreparationRecord } from '@/api/skills'
import { t } from '@/composables/i18n'
import { downloadPreparationLog } from './downloadPreparationLog'

const props = defineProps<{ show: boolean; skillId: string; skillName: string }>()
const emit = defineEmits<{ 'update:show': [value: boolean] }>()
const message = useMessage()
const records = ref<SkillPreparationRecord[]>([])
const selected = ref<SkillPreparationRecord | null>(null)
const selectedId = ref('')
const loading = ref(false)
const loadError = ref('')
const downloading = ref(false)
let timer: ReturnType<typeof setInterval> | null = null

function formatTime(value: string): string { return value ? new Date(value).toLocaleString() : '—' }
function statusText(value: SkillPreparationRecord['status']): string { return t(`skillDeps.records.status.${value}`) }
function statusType(value: SkillPreparationRecord['status']): 'success' | 'error' | 'warning' { return value === 'ready' ? 'success' : value === 'failed' ? 'error' : 'warning' }
async function downloadSelected(): Promise<void> {
  const recordId = selectedId.value
  if (!recordId || downloading.value) return
  downloading.value = true
  try {
    const record = await fetchSkillPreparationRecord(props.skillId, recordId)
    if (!record.log) {
      message.warning(t('skillDeps.records.noLog'))
      return
    }
    if (selectedId.value === recordId) selected.value = record
    downloadPreparationLog(record, props.skillName)
  } catch {
    message.error(t('skillDeps.records.downloadFailed'))
  } finally {
    downloading.value = false
  }
}
async function select(recordId: string): Promise<void> {
  selectedId.value = recordId
  try {
    const result = await fetchSkillPreparationRecord(props.skillId, recordId)
    if (selectedId.value === recordId) selected.value = result
  } catch { loadError.value = t('skillDeps.records.loadFailed') }
}
async function refresh(force = false): Promise<void> {
  if (!props.show || !props.skillId) return
  loadError.value = ''
  try {
    const previous = records.value.find(item => item.id === selectedId.value)
    records.value = await fetchSkillPreparationRecords(props.skillId)
    const next = selectedId.value && records.value.some(item => item.id === selectedId.value) ? selectedId.value : records.value[0]?.id || ''
    const current = records.value.find(item => item.id === next)
    if (next) {
      if (force || !selected.value || next !== selectedId.value || current?.status === 'preparing' || previous?.status !== current?.status || previous?.attempts.length !== current?.attempts.length) await select(next)
    } else { selectedId.value = ''; selected.value = null }
  } catch { loadError.value = t('skillDeps.records.loadFailed') }
}
watch(() => [props.show, props.skillId], async () => {
  if (timer) clearInterval(timer)
  timer = null
  if (!props.show || !props.skillId) return
  selectedId.value = ''
  selected.value = null
  loading.value = true
  try { await refresh() } finally { loading.value = false }
  timer = setInterval(() => { if (!records.value.length || records.value.some(item => item.status === 'preparing')) void refresh() }, 3000)
}, { immediate: true })
onBeforeUnmount(() => { if (timer) clearInterval(timer) })
</script>

<style scoped>
.records-layout { display:grid;grid-template-columns:210px minmax(0,1fr);gap:18px;min-height:600px; }
.records-list { display:flex;flex-direction:column;gap:6px;max-height:calc(100vh - 130px);overflow:auto; }
.record-choice { display:flex;align-items:flex-start;flex-direction:column;gap:6px;width:100%;padding:10px;border:1px solid #e2e8f0;border-radius:8px;background:#fff;text-align:left;cursor:pointer; }
.record-choice.selected { border-color:#3b70e8;background:#eff5ff; }
.record-choice small { color:#64748b;font-family:ui-monospace,SFMono-Regular,Menlo,monospace; }
.record-content { min-width:0; }
.record-meta { display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;padding:14px;background:#f7f9fc;border-radius:10px; }
.record-meta div { min-width:0;display:flex;flex-direction:column;gap:4px; }
.record-meta span { color:#64748b;font-size:12px; }
.record-meta strong,.record-meta code { overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:12px; }
.log-head { display:flex;align-items:center;justify-content:space-between;margin:18px 0 8px; }
.log-actions { display:flex;gap:8px; }
.log-note,.load-error { color:#a23b32; }
.log-view { margin:0;padding:16px;min-height:340px;max-height:calc(100vh - 380px);overflow:auto;border-radius:10px;background:#111827;color:#d1e7da;font:12px/1.6 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;white-space:pre-wrap;overflow-wrap:anywhere; }
@media(max-width:700px){.records-layout{grid-template-columns:1fr}.records-list{max-height:180px}.record-meta{grid-template-columns:1fr}}
</style>
