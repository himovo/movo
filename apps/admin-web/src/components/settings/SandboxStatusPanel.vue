<template>
  <section class="sandbox-panel">
    <header>
      <div><h2>{{ t('sandbox.title') }}</h2><p>{{ t('sandbox.description') }}</p></div>
      <n-button :loading="loading" :disabled="saving" @click="refresh">{{ t('sandbox.refresh') }}</n-button>
    </header>
    <n-alert v-if="error" type="error">{{ t('sandbox.loadingFailed') }}</n-alert>
    <n-alert v-else-if="status && !status.enabled" type="warning">{{ t('sandbox.disabled') }}</n-alert>
    <n-alert v-else-if="status && !status.healthy" type="error">{{ t('sandbox.unhealthy') }}</n-alert>
    <template v-else-if="status">
      <n-alert type="success">{{ t('sandbox.healthy') }}</n-alert>
      <div class="stats">
        <div><strong>{{ status.running }}</strong><span>{{ t('sandbox.running') }}</span></div>
        <div><strong>{{ status.pending }}</strong><span>{{ t('sandbox.pending') }}</span></div>
        <div><strong>{{ status.capacity }}</strong><span>{{ t('sandbox.capacity') }}</span></div>
        <div><strong>{{ status.plugin_runtimes }}</strong><span>{{ t('sandbox.plugins') }}</span></div>
      </div>
      <div class="queue-setting">
        <span>{{ t('sandbox.capacity') }}</span>
        <n-input-number v-model:value="capacity" :min="1" :max="100" :precision="0" :disabled="saving" />
      </div>
      <div class="queue-setting">
        <span>{{ t('sandbox.maxPending') }}</span>
        <n-input-number v-model:value="maxPending" :min="0" :max="100" :precision="0" :disabled="saving" />
        <n-button type="primary" :loading="saving" :disabled="capacity === null || maxPending === null || (capacity === status.capacity && maxPending === status.max_pending)" @click="save">{{ t('sandbox.save') }}</n-button>
      </div>
      <p>{{ t('sandbox.idle') }}: {{ t('sandbox.seconds', { count: status.plugin_idle_seconds ?? 900 }) }}</p>
      <p>{{ t('sandbox.configure') }}</p>
      <p>{{ t('sandbox.taskCapacity', { count: status.task_capacity ?? 10, used: status.resident_containers ?? 0 }) }}</p>
    </template>
  </section>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { NAlert, NButton, NInputNumber, useMessage } from 'naive-ui'
import { fetchSandboxStatus, saveSandboxLimits, type SandboxStatus } from '@/api/sandbox-settings'
import { t } from '@/composables/i18n'

const status = ref<SandboxStatus | null>(null)
const loading = ref(false)
const saving = ref(false)
const capacity = ref<number | null>(null)
const maxPending = ref<number | null>(null)
const error = ref(false)
const message = useMessage()
async function refresh() {
  loading.value = true
  error.value = false
  try {
    status.value = await fetchSandboxStatus()
    capacity.value = status.value.capacity ?? null
    maxPending.value = status.value.max_pending ?? null
  }
  catch { error.value = true }
  finally { loading.value = false }
}
async function save() {
  if (capacity.value === null || maxPending.value === null) return
  saving.value = true
  try {
    await saveSandboxLimits(capacity.value, maxPending.value)
    await refresh()
    message.success(t('sandbox.saved'))
  } catch { message.error(t('sandbox.saveFailed')) }
  finally { saving.value = false }
}
let poll: ReturnType<typeof setInterval> | undefined
onMounted(() => {
  void refresh()
  poll = setInterval(async () => {
    if (loading.value || saving.value) return
    try { status.value = await fetchSandboxStatus(); error.value = false }
    catch { error.value = true }
  }, 5000)
})
onUnmounted(() => clearInterval(poll))
</script>

<style scoped>
.sandbox-panel { display: grid; gap: 18px; }
header { display: flex; align-items: flex-start; justify-content: space-between; }
h2 { margin: 0; font-size: 20px; }
p { margin: 5px 0; color: #64748b; }
.stats { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.stats > div { display: grid; gap: 8px; padding: 18px; border: 1px solid #e2e8f0; border-radius: 10px; }
.queue-setting { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; }
strong { font-size: 24px; }
span { color: #64748b; }
@media (max-width: 800px) { .stats { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
</style>
