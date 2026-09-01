<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { NAlert, NButton, NCheckbox, NSpace } from 'naive-ui'
import { t } from '../../composables/i18n'
import { useEmbeddedBrowserState } from '../../composables/browser/embeddedBrowserState'
import type { BrowserAssistanceHandoff } from '../../composables/browser/useBrowserWorkspace'
import type { BrowserAgentReturnSignal } from '../../composables/browser/browserAgentReturn'

const props = defineProps<{
  category: string
  domain?: string
  reason?: string
  handoff?: BrowserAssistanceHandoff
}>()

const emit = defineEmits<{
  (e: 'confirm', signal?: BrowserAgentReturnSignal): void
  (e: 'skip'): void
  (e: 'show-browser'): void
}>()

const confirming = ref(false)
const browserState = useEmbeddedBrowserState()
const completedImages = ref<string[]>([])
const copied = ref('')

const isAuth = computed(() => ['login', 'registration', 'authentication'].includes(String(props.category || '').toLowerCase()))
const isRegistration = computed(() => String(props.category || '').toLowerCase() === 'registration')
const browserVisible = computed(() => browserState.value.active && browserState.value.visible)
const title = computed(() => {
  if (isRegistration.value) return t('execution.registration_required', { domain: props.domain || '' })
  if (isAuth.value) return t('execution.login_required', { domain: props.domain || '' })
  return t('intervention.title')
})
const description = computed(() => {
  if (isAuth.value) {
    return browserVisible.value ? t('execution.auth_in_browser') : t('execution.btn_login')
  }
  return props.reason || t('intervention.default_desc')
})
const primaryAction = computed(() => (isAuth.value ? t('execution.btn_open_browser') : t('execution.btn_preview')))
const confirmLabel = computed(() => (isAuth.value ? t('execution.btn_resume_agent') : t('intervention.btn_continue')))
const isMediaUpload = computed(() => String(props.category || '').toLowerCase() === 'media_upload' && Boolean(props.handoff))
const hasContentHandoff = computed(() => Boolean(
  props.handoff?.article?.title
  || props.handoff?.article?.body
  || props.handoff?.images?.length,
))
const assistanceContract = computed(() => props.handoff?.contract)
const contractKind = computed(() => String(assistanceContract.value?.kind || ''))
const isFormAssistance = computed(() => contractKind.value.startsWith('form_'))
const fieldPayload = computed(() => assistanceContract.value?.payload || {})
const imageKey = (candidateId: string, sourceIndex: number) => `${candidateId}:${sourceIndex}`
const completedCandidateIds = computed(() => {
  const selected = new Set(completedImages.value)
  const groups = new Map<string, string[]>()
  for (const image of props.handoff?.images || []) {
    const keys = groups.get(image.candidate_id) || []
    keys.push(imageKey(image.candidate_id, image.source_index))
    groups.set(image.candidate_id, keys)
  }
  return [...groups.entries()]
    .filter(([, keys]) => keys.length > 0 && keys.every((key) => selected.has(key)))
    .map(([candidateId]) => candidateId)
})

watch(() => props.handoff, () => {
  completedImages.value = []
  copied.value = ''
}, { deep: true })

function onConfirm() {
  confirming.value = true
  const positiveOutcome = contractKind.value === 'form_effect_verify'
    ? 'succeeded'
    : contractKind.value === 'form_task_completion'
      ? 'task_completed'
      : 'completed'
  emit('confirm', isFormAssistance.value
    ? {
        human_outcome: positiveOutcome,
        assistance_contract: assistanceContract.value as unknown as Record<string, unknown>,
        ...(isMediaUpload.value ? { media_completed_candidate_ids: completedCandidateIds.value } : {}),
      }
    : isMediaUpload.value
      ? { media_completed_candidate_ids: completedCandidateIds.value }
      : undefined)
}

function reportOutcome(outcome: BrowserAgentReturnSignal['human_outcome']) {
  confirming.value = true
  emit('confirm', {
    human_outcome: outcome,
    assistance_contract: assistanceContract.value as unknown as Record<string, unknown>,
  })
}

async function copyText(kind: 'title' | 'body', value: string) {
  await navigator.clipboard.writeText(value || '')
  copied.value = kind
  window.setTimeout(() => { if (copied.value === kind) copied.value = '' }, 1500)
}

function downloadAllImages() {
  for (const [index, image] of (props.handoff?.images || []).entries()) {
    const downloadUrl = image.signed_url || image.download_url || image.url
    if (!downloadUrl) continue
    window.setTimeout(() => {
      const link = document.createElement('a')
      link.href = downloadUrl
      link.download = image.filename || `image-${index + 1}`
      link.rel = 'noopener'
      link.click()
    }, index * 120)
  }
}

function setImageCompleted(key: string, checked: boolean) {
  const selected = new Set(completedImages.value)
  if (checked) selected.add(key)
  else selected.delete(key)
  completedImages.value = [...selected]
}
</script>

<template>
  <n-alert type="warning" :show-icon="true" class="animate-login-appear">
    <template #header>
      <span class="font-semibold">{{ title }}</span>
    </template>
    <div class="flex items-start gap-3">
      <div class="flex-1 min-w-0 text-[12px] leading-relaxed">
        {{ description }}
      </div>
    </div>
    <div v-if="hasContentHandoff && handoff" class="mt-3 space-y-3">
      <section v-if="handoff.article?.title || handoff.article?.body" class="rounded-lg border border-amber-200 bg-white/80 p-3">
        <div class="mb-2 flex items-center justify-between gap-2">
          <strong class="text-xs">{{ t('intervention.article_preview') }}</strong>
          <n-space :size="6">
            <n-button size="tiny" quaternary @click="copyText('title', handoff.article?.title || '')">
              {{ copied === 'title' ? t('intervention.copied') : t('intervention.copy_title') }}
            </n-button>
            <n-button size="tiny" quaternary @click="copyText('body', handoff.article?.body || '')">
              {{ copied === 'body' ? t('intervention.copied') : t('intervention.copy_body') }}
            </n-button>
          </n-space>
        </div>
        <div class="font-medium text-slate-900">{{ handoff.article?.title || t('intervention.untitled') }}</div>
        <div class="mt-2 max-h-52 overflow-auto whitespace-pre-wrap text-xs leading-6 text-slate-700">{{ handoff.article?.body }}</div>
      </section>

      <section v-if="handoff.images?.length" class="rounded-lg border border-amber-200 bg-white/80 p-3">
        <div class="mb-2 flex items-center justify-between gap-2">
          <strong class="text-xs">{{ t(isMediaUpload ? 'intervention.pending_images' : 'intervention.images', { count: handoff.images?.length || 0 }) }}</strong>
          <n-button size="tiny" quaternary :disabled="!handoff.images?.some(image => image.download_url)" @click="downloadAllImages">
            {{ t('intervention.download_all') }}
          </n-button>
        </div>
        <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div v-for="(image, index) in handoff.images || []" :key="imageKey(image.candidate_id, image.source_index)" class="overflow-hidden rounded-md border border-slate-200 bg-white">
            <img v-if="image.signed_url || image.url" :src="image.signed_url || image.url" :alt="image.filename || `image-${index + 1}`" class="h-32 w-full bg-slate-50 object-contain" />
            <div v-else class="flex h-20 items-center justify-center bg-slate-50 text-xs text-slate-400">{{ t('intervention.preview_unavailable') }}</div>
            <div class="space-y-2 p-2">
              <div class="truncate text-xs font-medium">{{ t('intervention.image_index', { index: index + 1 }) }} · {{ image.filename }}</div>
              <div class="flex items-center justify-between gap-2">
                <a v-if="image.signed_url || image.download_url || image.url" :href="image.signed_url || image.download_url || image.url" :download="image.filename" class="text-xs text-blue-600 hover:text-blue-700">{{ t('ui.download') }}</a>
                <n-checkbox v-if="isMediaUpload"
                  :checked="completedImages.includes(imageKey(image.candidate_id, image.source_index))"
                  size="small"
                  @update:checked="(checked: boolean) => setImageCompleted(imageKey(image.candidate_id, image.source_index), checked)"
                >
                  {{ t('intervention.uploaded_manually') }}
                </n-checkbox>
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>
    <section v-else-if="isFormAssistance && assistanceContract" class="mt-3 rounded-lg border border-amber-200 bg-white/80 p-3 text-xs">
      <div v-if="fieldPayload.field_label" class="font-medium text-slate-900">{{ fieldPayload.field_label }}</div>
      <div v-if="fieldPayload.field_value" class="mt-2 whitespace-pre-wrap rounded bg-slate-50 p-2 text-slate-700">{{ fieldPayload.field_value }}</div>
      <div v-if="fieldPayload.action_name" class="font-medium text-slate-900">{{ fieldPayload.action_name }}</div>
      <div v-if="fieldPayload.entity" class="mt-1 text-slate-600">{{ fieldPayload.entity }}</div>
    </section>
    <n-space :size="8" class="mt-3">
      <n-button v-if="!browserVisible" type="warning" size="small" @click="emit('show-browser')">
        {{ primaryAction }}
      </n-button>
      <n-button size="small" :loading="confirming" :disabled="confirming || (isMediaUpload && completedCandidateIds.length === 0)" @click="onConfirm">
        {{ contractKind === 'form_effect_verify'
          ? t('intervention.operation_succeeded')
          : contractKind === 'form_task_completion'
            ? t('intervention.task_completed')
            : confirmLabel }}
      </n-button>
      <n-button v-if="contractKind === 'form_effect_verify'" size="small" :disabled="confirming" @click="reportOutcome('failed')">{{ t('intervention.operation_failed') }}</n-button>
      <n-button v-if="contractKind === 'form_effect_verify'" size="small" quaternary :disabled="confirming" @click="reportOutcome('uncertain')">{{ t('intervention.operation_uncertain') }}</n-button>
      <n-button v-if="contractKind === 'form_task_completion'" size="small" :disabled="confirming" @click="reportOutcome('continue_agent')">{{ t('intervention.continue_agent') }}</n-button>
      <n-button v-if="contractKind === 'form_task_completion'" size="small" quaternary :disabled="confirming" @click="reportOutcome('uncertain')">{{ t('intervention.operation_uncertain') }}</n-button>
      <n-button v-if="isFormAssistance && !isMediaUpload && !['form_effect_verify', 'form_task_completion'].includes(contractKind)" size="small" quaternary :disabled="confirming" @click="reportOutcome('unable')">{{ t('intervention.unable_to_complete') }}</n-button>
      <n-button v-if="!isFormAssistance && !isMediaUpload" size="small" quaternary @click="emit('skip')">
        {{ t('ui.skip') }}
      </n-button>
    </n-space>
  </n-alert>
</template>

<style scoped>
@keyframes login-appear {
  from { opacity: 0; transform: translateY(-4px); }
  to   { opacity: 1; transform: translateY(0); }
}
.animate-login-appear { animation: login-appear 0.3s ease-out; }
</style>
