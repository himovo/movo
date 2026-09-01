<script setup lang="ts">
import { ref, watch } from 'vue'
import { createNewOrg, type UserProfile } from '../api/auth'
import { t, useLocale } from '../composables/i18n'

const props = defineProps<{
  open: boolean
  token: string
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'created', payload: { token: string; username: string; profile: UserProfile }): void
}>()

const orgName = ref('')
const errorMessage = ref('')
const isSubmitting = ref(false)
const { locale } = useLocale()

watch(
  () => props.open,
  (open) => {
    if (!open) return
    orgName.value = ''
    errorMessage.value = ''
    isSubmitting.value = false
  },
)

async function handleSubmit() {
  const name = orgName.value.trim()
  if (!name) {
    errorMessage.value = t('org_create.name_empty')
    return
  }

  errorMessage.value = ''
  isSubmitting.value = true
  const result = await createNewOrg(name, props.token)
  isSubmitting.value = false

  if (!result.ok || !result.token || !result.profile) {
    errorMessage.value = result.message || t('org_create.create_failed')
    return
  }

  emit('created', {
    token: result.token,
    username: result.profile.username || '',
    profile: result.profile,
  })
  emit('close')
}
</script>

<template>
  <div
    v-if="open"
    class="fixed inset-0 z-[100] flex items-center justify-center bg-slate-900/40 p-4 backdrop-blur-[2px]"
    @click.self="emit('close')"
  >
    <div class="w-full max-w-sm rounded-2xl border border-slate-200 bg-white p-6 shadow-2xl">
      <div class="flex items-start justify-between gap-4">
        <div>
          <h2 class="text-lg font-semibold text-slate-900">{{ t('org_create.title') }}</h2>
          <p class="mt-1 text-sm leading-6 text-slate-500">{{ t('org_create.desc') }}</p>
        </div>
        <button
          type="button"
          class="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-700"
          :aria-label="t('ui.close')"
          @click="emit('close')"
        >
          <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <path d="M18 6 6 18M6 6l12 12"/>
          </svg>
        </button>
      </div>

      <form class="mt-6 space-y-4" @submit.prevent="handleSubmit">
        <div class="space-y-2">
          <label for="create-organization-name" class="text-sm font-medium text-slate-700">{{ t('org_create.name_label') }}</label>
          <div class="relative">
            <svg class="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
              <path d="M3 21h18M6 21V5a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v16M9 7h2M13 7h2M9 11h2M13 11h2M9 15h2M13 15h2"/>
            </svg>
            <input
              id="create-organization-name"
              v-model.trim="orgName"
              type="text"
              maxlength="64"
              autofocus
              class="min-h-[44px] w-full rounded-xl border border-slate-200 bg-white py-2 pl-10 pr-3 text-slate-900 outline-none transition-colors placeholder:text-slate-400 focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
              :placeholder="t('org_create.name_placeholder')"
              @input="errorMessage = ''"
            />
          </div>
        </div>

        <p class="rounded-xl bg-slate-50 px-3 py-2.5 text-xs leading-5 text-slate-500">
          {{ t('org_create.notice') }}
        </p>

        <p v-if="errorMessage" class="rounded-xl bg-rose-50 px-3 py-2 text-sm text-rose-600">{{ errorMessage }}</p>

        <button
          type="submit"
          class="min-h-[44px] w-full rounded-xl bg-blue-600 px-4 text-sm font-semibold text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
          :disabled="isSubmitting"
        >
          {{ isSubmitting ? t('org_create.btn_creating') : t('org_create.btn_submit') }}
        </button>
      </form>
    </div>
  </div>
</template>
