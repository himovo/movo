<script setup lang="ts">
import { computed, reactive, watch } from 'vue'
import { NButton, NCard, NDatePicker, NForm, NFormItem, NInput, NModal, NSelect, NSwitch } from 'naive-ui'
import type { SessionSummary } from '../../api/sessions'
import type { ScheduledJob, ScheduledJobDraft } from '../../api/scheduledTasks'
import { parseAppDate } from '../../composables/appTimezone'
import { t } from '../../composables/i18n'

const props = defineProps<{
  open: boolean
  saving?: boolean
  job?: ScheduledJob | null
  sessions: SessionSummary[]
  initialPrompt?: string
  initialSessionId?: string | null
  timezone: string
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'save', value: ScheduledJobDraft): void
}>()

const tomorrow = () => Date.now() + 24 * 60 * 60 * 1000
const form = reactive({
  name: '', prompt: '', scheduleKind: 'daily', timezone: 'Asia/Shanghai', runAt: tomorrow(),
  weekdays: [0] as number[], sessionMode: 'fixed', sessionId: null as string | null,
  sessionTitleTemplate: '{name} · {date}', enabled: true,
})

const scheduleOptions = computed(() => [
  { label: t('仅执行一次'), value: 'once' }, { label: t('每天'), value: 'daily' }, { label: t('每周'), value: 'weekly' },
])
const sessionModeOptions = computed(() => [
  { label: t('写入指定会话'), value: 'fixed' }, { label: t('每次执行新建会话'), value: 'new_per_run' },
])
const weekdayOptions = computed(() => [
  { label: t('周一'), value: 0 }, { label: t('周二'), value: 1 }, { label: t('周三'), value: 2 },
  { label: t('周四'), value: 3 }, { label: t('周五'), value: 4 }, { label: t('周六'), value: 5 }, { label: t('周日'), value: 6 },
])
const sessionOptions = computed(() => props.sessions.map((item) => ({ label: item.title || t('新对话'), value: item.id })))
const startOfToday = () => {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  return today.getTime()
}
const isPastDate = (timestamp: number) => timestamp < startOfToday()
const canSave = computed(() => Boolean(
  form.name.trim() && form.prompt.trim() && form.runAt &&
  (form.sessionMode !== 'fixed' || form.sessionId) &&
  (form.scheduleKind !== 'weekly' || form.weekdays.length),
))

watch(() => props.open, (open) => {
  if (!open) return
  const job = props.job
  form.name = job?.name || (props.initialPrompt ? props.initialPrompt.trim().slice(0, 30) : t('新的定时任务'))
  form.prompt = job?.prompt || props.initialPrompt || ''
  form.scheduleKind = job?.schedule_kind || 'daily'
  form.timezone = job?.timezone || props.timezone || 'Asia/Shanghai'
  const parsedRunAt = parseAppDate(job?.run_at)
  form.runAt = parsedRunAt ? parsedRunAt.getTime() : tomorrow()
  form.weekdays = job?.weekdays?.length ? [...job.weekdays] : [new Date().getDay() === 0 ? 6 : new Date().getDay() - 1]
  form.sessionMode = job?.session_mode || (props.initialSessionId ? 'fixed' : 'new_per_run')
  form.sessionId = job?.session_id || props.initialSessionId || null
  form.sessionTitleTemplate = job?.session_title_template || '{name} · {date}'
  form.enabled = job?.enabled ?? true
}, { immediate: true })

function submit() {
  if (!canSave.value) return
  emit('save', {
    name: form.name.trim(),
    prompt: form.prompt.trim(),
    schedule_kind: form.scheduleKind as ScheduledJobDraft['schedule_kind'],
    timezone: form.timezone,
    run_at: new Date(form.runAt).toISOString(),
    weekdays: form.scheduleKind === 'weekly' ? [...form.weekdays].sort() : [],
    session_mode: form.sessionMode as ScheduledJobDraft['session_mode'],
    session_id: form.sessionMode === 'fixed' ? form.sessionId : null,
    session_title_template: form.sessionTitleTemplate.trim() || '{name} · {date}',
    enabled: form.enabled,
    output_spec: props.job?.output_spec || {},
  })
}
</script>

<template>
  <n-modal :show="open" :mask-closable="!saving" @update:show="(value) => !value && emit('close')">
    <n-card class="w-[680px] max-w-[calc(100vw-32px)]" :bordered="false" role="dialog" aria-modal="true">
      <template #header>{{ job ? t('编辑定时任务') : t('创建定时任务') }}</template>
      <n-form label-placement="top" class="max-h-[72vh] overflow-y-auto pr-2">
        <n-form-item :label="t('任务名称')" required><n-input v-model:value="form.name" maxlength="120" show-count /></n-form-item>
        <n-form-item :label="t('自动发送的提示词')" required><n-input v-model:value="form.prompt" type="textarea" :autosize="{ minRows: 4, maxRows: 10 }" maxlength="20000" show-count /></n-form-item>
        <div class="grid grid-cols-1 gap-x-4 md:grid-cols-2">
          <n-form-item :label="t('执行频率')" required><n-select v-model:value="form.scheduleKind" :options="scheduleOptions" /></n-form-item>
          <n-form-item :label="t('首次/下次执行时间')" required><n-date-picker v-model:value="form.runAt" type="datetime" class="w-full" :is-date-disabled="isPastDate" /></n-form-item>
        </div>
        <n-form-item v-if="form.scheduleKind === 'weekly'" :label="t('执行星期')" required>
          <n-select v-model:value="form.weekdays" multiple :options="weekdayOptions" />
        </n-form-item>
        <n-form-item :label="t('结果写入方式')" required><n-select v-model:value="form.sessionMode" :options="sessionModeOptions" /></n-form-item>
        <n-form-item v-if="form.sessionMode === 'fixed'" :label="t('目标会话')" required>
          <n-select v-model:value="form.sessionId" filterable :options="sessionOptions" :placeholder="t('选择一个属于你的会话')" />
        </n-form-item>
        <n-form-item v-else :label="t('新会话标题模板')">
          <n-input v-model:value="form.sessionTitleTemplate" placeholder="{name} · {date}" />
        </n-form-item>
        <div class="flex min-h-11 items-center justify-between rounded-xl border border-slate-200 px-4">
          <div><div class="text-sm font-medium text-slate-800">{{ t('创建后启用') }}</div><div class="text-xs text-slate-500">{{ t('关闭时仅保存配置，不会自动执行') }}</div></div>
          <n-switch v-model:value="form.enabled" />
        </div>
      </n-form>
      <template #footer>
        <div class="flex justify-end gap-3">
          <n-button :disabled="saving" @click="emit('close')">{{ t('取消') }}</n-button>
          <n-button type="primary" :loading="saving" :disabled="!canSave" @click="submit">{{ job ? t('保存修改') : t('创建任务') }}</n-button>
        </div>
      </template>
    </n-card>
  </n-modal>
</template>
