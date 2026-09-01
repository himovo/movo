<script setup lang="ts">
import { ref, watch } from 'vue'
import { updateUserProfile, uploadUserAvatar, type UserProfile } from '../api/auth'
import { t } from '../composables/i18n'

const props = defineProps<{
  open: boolean
  token: string
  profile: UserProfile | null
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'updated', profile: UserProfile): void
}>()

const name = ref('')
const errorMessage = ref('')
const isSaving = ref(false)
const isUploading = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)

watch(
  () => props.open,
  (open) => {
    if (!open) return
    name.value = String(props.profile?.name || '').replace(/^1[3-9]\d{9}$/, '')
    errorMessage.value = ''
  },
)

function maskedPhone() {
  const phone = String(props.profile?.phone || '').replace(/\D/g, '')
  return /^1[3-9]\d{9}$/.test(phone) ? `${phone.slice(0, 3)}****${phone.slice(-4)}` : ''
}

function avatarText() {
  return name.value.trim().slice(0, 1) || t('profile.default_avatar_char')
}

function chooseAvatar() {
  fileInput.value?.click()
}

async function handleAvatarChange(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  errorMessage.value = ''
  isUploading.value = true
  const result = await uploadUserAvatar(props.token, file)
  isUploading.value = false
  if (!result.ok || !result.data) {
    errorMessage.value = result.message || t('api.auth.upload_avatar_failed')
    return
  }
  emit('updated', result.data)
}

async function handleSave() {
  const value = name.value.trim()
  if (!value) {
    errorMessage.value = t('profile.name_empty')
    return
  }
  errorMessage.value = ''
  isSaving.value = true
  const result = await updateUserProfile(props.token, value)
  isSaving.value = false
  if (!result.ok || !result.data) {
    errorMessage.value = result.message || t('api.auth.update_profile_failed')
    return
  }
  emit('updated', result.data)
  emit('close')
}
</script>

<template>
  <div v-if="open" class="fixed inset-0 z-[100] flex items-center justify-center bg-slate-900/40 p-4" @click.self="emit('close')">
    <div class="w-full max-w-sm rounded-2xl bg-white p-6 shadow-2xl">
      <div class="flex items-center justify-between">
        <div>
          <h2 class="text-lg font-semibold text-slate-900">{{ t('profile.modal_title') }}</h2>
          <p class="mt-1 text-sm text-slate-500">{{ t('profile.subtitle') }}</p>
        </div>
        <button type="button" class="rounded-lg p-2 text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-700" :aria-label="t('ui.close')" @click="emit('close')">
          <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <path d="M18 6 6 18M6 6l12 12"/>
          </svg>
        </button>
      </div>

      <div class="mt-6 flex flex-col items-center">
        <button type="button" class="group relative h-20 w-20 overflow-hidden rounded-2xl bg-blue-600 text-2xl font-bold text-white" :disabled="isUploading" @click="chooseAvatar">
          <img v-if="profile?.avatar" :src="profile.avatar" :alt="t('profile.avatar_alt')" class="h-full w-full object-cover" />
          <span v-else>{{ avatarText() }}</span>
          <span class="absolute inset-x-0 bottom-0 flex h-7 items-center justify-center bg-slate-900/65 text-white transition-colors group-hover:bg-slate-900/80">
            <svg v-if="!isUploading" class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
              <path d="M14.5 4h-5L8 6H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-3l-1.5-2z"/>
              <circle cx="12" cy="13" r="3"/>
            </svg>
            <span v-else class="text-xs">{{ t('profile.uploading') }}</span>
          </span>
        </button>
        <input ref="fileInput" type="file" accept="image/jpeg,image/png,image/webp" class="hidden" @change="handleAvatarChange" />
        <p class="mt-2 text-xs text-slate-400">{{ t('profile.avatar_hint') }}</p>
      </div>

      <form class="mt-6 space-y-4" @submit.prevent="handleSave">
        <div class="space-y-2">
          <label class="text-sm font-medium text-slate-700">{{ t('profile.username_label') }}</label>
          <div class="relative">
            <svg class="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
              <path d="M20 21a8 8 0 0 0-16 0"/>
              <circle cx="12" cy="7" r="4"/>
            </svg>
            <input v-model="name" type="text" maxlength="64" class="min-h-[44px] w-full rounded-xl border border-slate-200 py-2 pl-10 pr-3 text-slate-900 outline-none transition-colors focus:border-slate-400" :placeholder="t('profile.username_placeholder')" />
          </div>
        </div>

        <div v-if="maskedPhone()" class="space-y-2">
          <label class="text-sm font-medium text-slate-700">{{ t('profile.phone_label') }}</label>
          <div class="min-h-[44px] rounded-xl bg-slate-50 px-3 py-3 text-sm text-slate-500">{{ maskedPhone() }}</div>
        </div>

        <p v-if="errorMessage" class="rounded-xl bg-rose-50 px-3 py-2 text-sm text-rose-600">{{ errorMessage }}</p>

        <button type="submit" class="min-h-[44px] w-full rounded-xl bg-slate-900 px-4 text-sm font-semibold text-white transition-colors hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60" :disabled="isSaving || isUploading">
          {{ isSaving ? t('profile.saving') : t('profile.save_btn') }}
        </button>
      </form>
    </div>
  </div>
</template>
