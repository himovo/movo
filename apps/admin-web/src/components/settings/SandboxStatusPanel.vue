<template>
  <section class="sandbox-panel">
    <header>
      <div><h2>{{ t('sandbox.title') }}</h2><p>{{ t('sandbox.description') }}</p></div>
      <n-space :wrap="false">
        <n-button :loading="loading" :disabled="saving" @click="refresh">{{ t('sandbox.refresh') }}</n-button>
        <n-button type="primary" :loading="saving" :disabled="loading || saving || !canSave" @click="save">{{ t('sandbox.save') }}</n-button>
      </n-space>
    </header>
    <n-alert v-if="error" type="error">{{ t('sandbox.loadingFailed') }}</n-alert>
    <n-alert v-else-if="status && !status.enabled" type="warning">{{ t('sandbox.disabled') }}</n-alert>
    <n-alert v-else-if="status && !status.healthy" type="error">{{ t('sandbox.unhealthy') }}</n-alert>
    <template v-else-if="status">
      <div class="stats">
        <div><strong>{{ status.running }}</strong><span>{{ t('sandbox.running') }}</span></div>
        <div><strong>{{ status.pending }}</strong><span>{{ t('sandbox.pending') }}</span></div>
        <div><strong>{{ status.plugin_runtimes }}</strong><span>{{ t('sandbox.plugins') }}</span></div>
        <div><strong>{{ status.resident_containers ?? 0 }}/{{ status.task_capacity ?? 10 }}</strong><span>{{ t('sandbox.resident') }}</span></div>
      </div>
      <n-form :disabled="saving || loading" label-placement="top" :show-feedback="false" class="settings-grid">
        <n-form-item :label="t('sandbox.runtimeMode')" class="mode-setting">
          <n-radio-group v-model:value="mode">
            <n-radio-button value="on_demand">{{ t('sandbox.onDemand') }}</n-radio-button>
            <n-radio-button value="forced">{{ t('sandbox.forced') }}</n-radio-button>
          </n-radio-group>
        </n-form-item>
        <n-form-item :label="t('sandbox.capacity')">
          <n-input-number v-model:value="capacity" :min="1" :max="100" :precision="0" />
        </n-form-item>
        <n-form-item :label="t('sandbox.maxPending')">
          <n-input-number v-model:value="maxPending" :min="0" :max="100" :precision="0" />
        </n-form-item>
        <n-form-item :label="t('sandbox.idle')">
          <div class="idle-setting">
            <n-input-number v-if="reclaim" v-model:value="idleSeconds" :min="1" :max="604800" :precision="0">
              <template #suffix>{{ t('sandbox.secondUnit') }}</template>
            </n-input-number>
            <n-checkbox :checked="!reclaim" @update:checked="reclaim = !$event">{{ t('sandbox.neverReclaim') }}</n-checkbox>
          </div>
        </n-form-item>
      </n-form>
      <details><summary>{{ t('sandbox.details') }}</summary>
        <p>{{ t('sandbox.modeHint') }}</p>
        <p>{{ t('sandbox.configure') }} {{ t('sandbox.capacityHint') }}</p>
      </details>
    </template>
    <div v-if="accessPanel" :inert="loading || saving">
      <component :is="accessPanel" ref="access" />
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, type Component } from 'vue'
import { NAlert, NButton, NCheckbox, NForm, NFormItem, NInputNumber, NRadioButton, NRadioGroup, NSpace, useMessage } from 'naive-ui'
import { fetchSandboxStatus, saveSandboxSettings, type SandboxRuntimeMode, type SandboxStatus } from '@/api/sandbox-settings'
import { t } from '@/composables/i18n'

defineProps<{ accessPanel?: Component }>()
const access = ref<{ load(): Promise<void>; validate(): boolean; save(): Promise<void> }>()
const status = ref<SandboxStatus | null>(null)
const loading = ref(false)
const saving = ref(false)
const capacity = ref<number | null>(null)
const maxPending = ref<number | null>(null)
const mode = ref<SandboxRuntimeMode>('on_demand')
const idleSeconds = ref<number | null>(900)
const reclaim = ref(true)
const error = ref(false)
const message = useMessage()
let statusRequest = 0
let baseLoaded = false
const canSave = computed(() => {
  if (error.value || !status.value || (status.value.enabled && !status.value.healthy)) return false
  if (!status.value.enabled) return Boolean(access.value)
  return capacity.value !== null && maxPending.value !== null && (!reclaim.value || idleSeconds.value !== null)
})

async function loadStatus(reset: boolean) {
  const request = ++statusRequest
  try {
    const next = await fetchSandboxStatus()
    if (request !== statusRequest) return
    status.value = next
    error.value = false
    if (next.enabled && next.healthy && (reset || !baseLoaded)) {
      baseLoaded = true
      capacity.value = next.capacity ?? null
      maxPending.value = next.max_pending ?? null
      mode.value = next.runtime_mode ?? 'on_demand'
      reclaim.value = next.plugin_idle_seconds !== 0
      idleSeconds.value = next.plugin_idle_seconds || 900
    }
  } catch { if (request === statusRequest) error.value = true }
}
async function refresh() {
  loading.value = true
  try { await Promise.all([loadStatus(true), access.value?.load()]) }
  finally { loading.value = false }
}
async function save() {
  if (loading.value || saving.value || !canSave.value || (access.value && !access.value.validate())) return
  saving.value = true
  let baseSaved = false
  try {
    if (status.value?.enabled && capacity.value !== null && maxPending.value !== null) {
      await saveSandboxSettings({
        capacity: capacity.value, max_pending: maxPending.value,
        runtime_mode: mode.value, plugin_idle_seconds: reclaim.value ? idleSeconds.value! : 0,
      })
      baseSaved = true
    }
    await access.value?.save()
    message.success(t('sandbox.saved'))
  } catch {
    message.error(t(baseSaved ? 'sandbox.accessSaveFailed' : 'sandbox.saveFailed'))
  } finally {
    if (baseSaved) await loadStatus(false)
    saving.value = false
  }
}
let poll: ReturnType<typeof setInterval> | undefined
onMounted(() => {
  void refresh()
  poll = setInterval(() => {
    if (!loading.value && !saving.value) void loadStatus(false)
  }, 5000)
})
onUnmounted(() => clearInterval(poll))
</script>

<style scoped>
.sandbox-panel { display: grid; gap: 14px; }
header { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
h2 { margin: 0; font-size: 20px; }
p { margin: 4px 0; color: #64748b; }
.stats, .settings-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.stats > div { display: grid; gap: 4px; padding: 10px 14px; border: 1px solid #e2e8f0; border-radius: 8px; }
.settings-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.mode-setting { grid-column: 1 / -1; }
.idle-setting { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; }
.idle-setting :deep(.n-input-number) { max-width: 136px; }
strong { font-size: 22px; }
span, summary { color: #64748b; }
summary { cursor: pointer; }
details { font-size: 13px; }
@media (max-width: 800px) { .stats, .settings-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 480px) { .settings-grid { grid-template-columns: 1fr; } }
</style>
