<script setup lang="ts">
import PasswordLoginForm from './login/PasswordLoginForm.vue'
import InvitationRegistrationForm from './login/InvitationRegistrationForm.vue'
import { ref } from 'vue'
import DesktopLoginServerSwitch from './desktop/DesktopLoginServerSwitch.vue'
import DesktopCompatibilityNotice from './desktop/DesktopCompatibilityNotice.vue'
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
const initialCode = typeof window === 'undefined' ? '' : new URLSearchParams(window.location.search).get('invite_code') || ''
const registering = ref(Boolean(initialCode))
const registeredUsername = ref('')
function completeRegistration(username: string) {
  registeredUsername.value = username
  registering.value = false
  const url = new URL(window.location.href)
  url.searchParams.delete('invite_code')
  url.searchParams.delete('register')
  window.history.replaceState({}, '', `${url.pathname}${url.search}${url.hash}`)
}
</script>

<template>
  <div v-if="open" class="login-modal-backdrop fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4">
    <div class="login-modal-panel max-h-[calc(100vh-2rem)] w-full max-w-md overflow-y-auto rounded-3xl border border-transparent bg-white p-6 shadow-2xl">
      <div class="flex items-start justify-between gap-4">
        <div class="flex items-start gap-3">
          <img src="/movo-logo.png" alt="MOVO" class="mt-0.5 h-10 w-12 shrink-0 object-contain" />
          <div>
            <div class="text-xl font-semibold text-slate-900">{{ registering ? t('invite.title') : t('login.title') }}</div>
            <div class="mt-1 text-sm leading-5 text-slate-500">{{ registering ? t('invite.description') : t('login.password_desc') }}</div>
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

      <InvitationRegistrationForm v-if="registering" :initial-code="initialCode" @success="completeRegistration" />
      <div v-else-if="registeredUsername" class="mt-5 rounded-xl bg-green-50 px-4 py-3 text-sm text-green-800">{{ t('invite.success') }}</div>
      <PasswordLoginForm v-if="!registering"
        class="mt-6"
        :suggested-username="registeredUsername || savedUsers[0]"
        @login-success="emit('login-success', $event)"
      />
      <button type="button" class="mt-4 text-sm text-blue-600 hover:underline" @click="registering = !registering">{{ registering ? t('invite.back_login') : t('invite.open_registration') }}</button>
      <DesktopLoginServerSwitch v-if="!registering" />
      <DesktopCompatibilityNotice v-if="!registering" inline />
    </div>
  </div>
</template>

<style>
html.platform-desktop.theme-dark .login-modal-backdrop {
  background: rgba(2, 6, 15, .74) !important;
  backdrop-filter: blur(3px);
}

html.platform-desktop.theme-dark .login-modal-panel {
  border-color: #3b4b62 !important;
  color: #dbe7f5;
  background: #1b2637 !important;
  box-shadow: 0 28px 80px rgba(0, 0, 0, .56), 0 0 0 1px rgba(148, 163, 184, .08) !important;
}

html.platform-desktop.theme-dark .login-modal-panel input,
html.platform-desktop.theme-dark .login-modal-panel select {
  border-color: #52627a !important;
  color: #f8fafc !important;
  background: #111b2a !important;
}

html.platform-desktop.theme-dark .login-modal-panel input::placeholder {
  color: #8fa0b7 !important;
}

html.platform-desktop.theme-dark .login-modal-panel input:focus,
html.platform-desktop.theme-dark .login-modal-panel select:focus {
  border-color: #7aa7f8 !important;
  box-shadow: 0 0 0 3px rgba(96, 165, 250, .2);
}

html.platform-desktop.theme-dark .login-modal-panel button[type='submit'] {
  color: #fff !important;
  background: #2563eb !important;
}

html.platform-desktop.theme-dark .login-modal-panel button[type='submit']:hover:not(:disabled) {
  background: #3b82f6 !important;
}

html.platform-desktop.theme-dark .login-modal-panel form > p:not([role='alert']),
html.platform-desktop.theme-dark .login-modal-panel #desktop-login-server-settings {
  border-color: #36475e !important;
  background: #152033 !important;
}
</style>
