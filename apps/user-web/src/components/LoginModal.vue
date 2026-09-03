<script setup lang="ts">
import PasswordLoginForm from './login/PasswordLoginForm.vue'
import DesktopLoginServerSwitch from './desktop/DesktopLoginServerSwitch.vue'
import { t } from '../composables/i18n'
import type { UserProfile } from '../api/auth'

defineProps<{
  open: boolean
  savedUsers: string[]
}>()

const emit = defineEmits<{
  (event: 'close'): void
  (event: 'login-success', payload: { token: string; username: string; profile?: UserProfile }): void
}>()
</script>

<template>
  <div v-if="open" class="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4">
    <div class="max-h-[calc(100vh-2rem)] w-full max-w-md overflow-y-auto rounded-3xl bg-white p-6 shadow-2xl">
      <div class="flex items-start justify-between gap-4">
        <div class="flex items-start gap-3">
          <img src="/movo-logo.png" alt="MOVO" class="mt-0.5 h-10 w-12 shrink-0 object-contain" />
          <div>
            <div class="text-xl font-semibold text-slate-900">{{ t('login.title') }}</div>
            <div class="mt-1 text-sm leading-5 text-slate-500">{{ t('login.password_desc') }}</div>
          </div>
        </div>
        <button
          class="rounded-full p-2 text-slate-400 transition-colors hover:bg-slate-100"
          :aria-label="t('login.close_aria')"
          @click="emit('close')"
        >
          <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <path d="M18 6 6 18" />
            <path d="m6 6 12 12" />
          </svg>
        </button>
      </div>

      <PasswordLoginForm
        class="mt-6"
        :suggested-username="savedUsers[0]"
        @login-success="emit('login-success', $event)"
      />
      <DesktopLoginServerSwitch />
    </div>
  </div>
</template>
