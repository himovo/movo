<script setup lang="ts">
import { computed, reactive, watch } from 'vue'
import { NButton, NCard, NDatePicker, NForm, NFormItem, NInput, NModal, NSelect, NSwitch } from 'naive-ui'
import type { SessionSummary } from '../../api/sessions'
import type { ScheduledJob, ScheduledJobDraft } from '../../api/scheduledTasks'
import { t } from '../../composables/i18n'
import { defaultPickerValue, instantToPickerValue, pickerValueToWallDateTime } from './scheduledTaskTime'

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

const form = reactive({
  name: '', prompt: '', scheduleKind: 'daily', timezone: 'Asia/Shanghai', runAt: defaultPickerValue('Asia/Shanghai'),
  weekdays: [0] as number[], sessionMode: 'fixed', sessionId: null as string | null,
  sessionTitleTemplate: '{name} · {date}', enabled: true,
})

const scheduleOptions = computed(() => [
  { label: t('legacy.once_0984db4'), value: 'once' }, { label: t('legacy.daily'), value: 'daily' }, { label: t('legacy.weekly'), value: 'weekly' },
])
const sessionModeOptions = computed(() => [
  { label: t('legacy.write_to_a_specific_chat'), value: 'fixed' }, { label: t('legacy.create_a_new_chat_each_run'), value: 'new_per_run' },
])
const weekdayOptions = computed(() => [
  { label: t('legacy.mon'), value: 0 }, { label: t('legacy.tue'), value: 1 }, { label: t('legacy.wed'), value: 2 },
  { label: t('legacy.thu'), value: 3 }, { label: t('legacy.fri'), value: 4 }, { label: t('legacy.sat'), value: 5 }, { label: t('legacy.sun'), value: 6 },
])
const sessionOptions = computed(() => props.sessions.map((item) => ({ label: item.title || t('legacy.new_chat'), value: item.id })))
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
  form.name = job?.name || (props.initialPrompt ? props.initialPrompt.trim().slice(0, 30) : t('legacy.new_scheduled_task'))
  form.prompt = job?.prompt || props.initialPrompt || ''
  form.scheduleKind = job?.schedule_kind || 'daily'
  form.timezone = job?.timezone || props.timezone || 'Asia/Shanghai'
  const parsedRunAt = job?.run_at ? instantToPickerValue(job.run_at, form.timezone) : null
  form.runAt = parsedRunAt ?? defaultPickerValue(form.timezone)
  const defaultDay = new Date(form.runAt).getDay()
  form.weekdays = job?.weekdays?.length ? [...job.weekdays] : [defaultDay === 0 ? 6 : defaultDay - 1]
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
    run_at: pickerValueToWallDateTime(form.runAt),
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
      <template #header>{{ job ? t('legacy.edit_scheduled_task') : t('legacy.create_scheduled_task') }}</template>
      <n-form label-placement="top" class="max-h-[72vh] overflow-y-auto pr-2">
        <n-form-item :label="t('legacy.task_name')" required><n-input v-model:value="form.name" maxlength="120" show-count /></n-form-item>
        <n-form-item :label="t('legacy.prompt_to_send_automatically')" required><n-input v-model:value="form.prompt" type="textarea" :autosize="{ minRows: 4, maxRows: 10 }" maxlength="20000" show-count /></n-form-item>
        <div class="grid grid-cols-1 gap-x-4 md:grid-cols-2">
          <n-form-item :label="t('legacy.frequency')" required><n-select v-model:value="form.scheduleKind" :options="scheduleOptions" /></n-form-item>
          <n-form-item :label="t('legacy.first_next_run')" required><n-date-picker v-model:value="form.runAt" type="datetime" class="w-full" :is-date-disabled="isPastDate" /></n-form-item>
        </div>
        <div class="-mt-3 mb-3 text-xs text-slate-500">{{ t('legacy.execution_timezone') }}：{{ form.timezone }}</div>
        <n-form-item v-if="form.scheduleKind === 'weekly'" :label="t('legacy.days_of_week')" required>
          <n-select v-model:value="form.weekdays" multiple :options="weekdayOptions" />
        </n-form-item>
        <n-form-item :label="t('legacy.result_destination')" required><n-select v-model:value="form.sessionMode" :options="sessionModeOptions" /></n-form-item>
        <n-form-item v-if="form.sessionMode === 'fixed'" :label="t('legacy.target_chat')" required>
          <n-select v-model:value="form.sessionId" filterable :options="sessionOptions" :placeholder="t('legacy.select_one_of_your_chats')" />
        </n-form-item>
        <n-form-item v-else :label="t('legacy.new_chat_title_template')">
          <n-input v-model:value="form.sessionTitleTemplate" placeholder="{name} · {date}" />
        </n-form-item>
        <div class="flex min-h-11 items-center justify-between rounded-xl border border-slate-200 px-4">
          <div><div class="text-sm font-medium text-slate-800">{{ t('legacy.enable_after_creation') }}</div><div class="text-xs text-slate-500">{{ t('legacy.when_off_the_configuration_is_saved_but_will_not') }}</div></div>
          <n-switch v-model:value="form.enabled" />
        </div>
      </n-form>
      <template #footer>
        <div class="flex justify-end gap-3">
          <n-button :disabled="saving" @click="emit('close')">{{ t('legacy.cancel') }}</n-button>
          <n-button type="primary" :loading="saving" :disabled="!canSave" @click="submit">{{ job ? t('legacy.save_changes') : t('legacy.create_task') }}</n-button>
        </div>
      </template>
    </n-card>
  </n-modal>
</template>
