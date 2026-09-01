<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import {
  fetchCaptchaConfig,
  loginWithPhoneCode,
  selectTenantAndLogin,
  sendSmsCode,
  type CaptchaValidate,
  type TenantCandidate,
} from '../api/auth'
import { t } from '../composables/i18n'
import LoginMethodTabs, { type LoginMethod } from './login/LoginMethodTabs.vue'
import PasswordLoginForm from './login/PasswordLoginForm.vue'

const props = defineProps<{
  open: boolean
  savedUsers: string[]
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'login-success', payload: { token: string; username: string; profile?: import('../api/auth').UserProfile }): void
}>()

type OrgMode = 'personal' | 'create' | 'join'
type CaptchaInstance = {
  onNextReady: (callback: () => void) => CaptchaInstance
  onSuccess: (callback: () => void) => CaptchaInstance
  onError: (callback: () => void) => CaptchaInstance
  onClose: (callback: () => void) => CaptchaInstance
  getValidate: () => CaptchaValidate | null
  showCaptcha: () => void
  reset: () => void
  destroy?: () => void
}

let ct4ScriptPromise: Promise<void> | null = null

function loadCaptchaScript() {
  if ((window as any).initAlicom4) return Promise.resolve()
  if (ct4ScriptPromise) return ct4ScriptPromise
  ct4ScriptPromise = new Promise<void>((resolve, reject) => {
    const script = document.createElement('script')
    script.src = '/ct4.js'
    script.async = true
    script.onload = () => resolve()
    script.onerror = () => reject(new Error(t('login.captcha_load_failed')))
    document.head.appendChild(script)
  })
  return ct4ScriptPromise
}

const phone = ref('')
const loginMethod = ref<LoginMethod>('password')
const smsCode = ref('')
const orgMode = ref<OrgMode>('personal')
const orgName = ref('')
const inviteCode = ref('')
const errorMessage = ref('')
const successMessage = ref('')
const isSubmitting = ref(false)
const isSendingCode = ref(false)
const remainingSeconds = ref(0)
const challengeToken = ref('')
const tenantCandidates = ref<TenantCandidate[]>([])
const selectedMainId = ref('')
const captchaInstance = ref<CaptchaInstance | null>(null)
const captchaReady = ref(false)
const pendingShowCaptcha = ref(false)
let countdownTimer: ReturnType<typeof setInterval> | null = null

const pendingSelection = computed(() => tenantCandidates.value.length > 0 && !!challengeToken.value)
const submitDisabled = computed(() => isSubmitting.value)
const sendButtonDisabled = computed(() => isSendingCode.value || remainingSeconds.value > 0)
const sendButtonText = computed(() => {
  if (isSendingCode.value) return t('phase.verifying')
  if (remainingSeconds.value > 0) return t('login.remaining_seconds', { seconds: remainingSeconds.value })
  return t('login.send_code')
})
const submitText = computed(() => {
  if (pendingSelection.value) return t('login.btn_enter_org')
  if (orgMode.value === 'create') return t('login.btn_login_create')
  if (orgMode.value === 'join') return t('login.btn_login_join')
  return t('login.btn_login')
})
const helperText = computed(() => {
  if (pendingSelection.value) return t('login.multiple_org_notice')
  if (orgMode.value === 'create') return t('login.create_org_notice')
  if (orgMode.value === 'join') return t('login.join_org_notice')
  return t('login.register_notice')
})

watch(
  () => props.open,
  (value) => {
    if (!value) {
      if (countdownTimer) {
        clearInterval(countdownTimer)
        countdownTimer = null
      }
      remainingSeconds.value = 0
      isSendingCode.value = false
      pendingShowCaptcha.value = false
      captchaReady.value = false
      captchaInstance.value?.destroy?.()
      captchaInstance.value = null
      return
    }
    errorMessage.value = ''
    successMessage.value = ''
    challengeToken.value = ''
    tenantCandidates.value = []
    selectedMainId.value = ''
    phone.value = ''
    smsCode.value = ''
    orgMode.value = 'personal'
    orgName.value = ''
    inviteCode.value = ''
    loginMethod.value = 'password'

    const params = new URLSearchParams(window.location.search)
    const invitedPhone = params.get('phone') || params.get('mobile') || params.get('username') || params.get('loginName')
    const invitedCode = params.get('invite_code') || params.get('inviteCode') || ''
    if (invitedPhone) {
      phone.value = invitedPhone
      loginMethod.value = 'sms'
    }
    if (invitedCode) {
      orgMode.value = 'join'
      inviteCode.value = invitedCode
      loginMethod.value = 'sms'
    }
  }
)

function resetErrors() {
  errorMessage.value = ''
  successMessage.value = ''
}

function selectOrgMode(mode: OrgMode) {
  orgMode.value = mode
  if (mode !== 'create') orgName.value = ''
  if (mode !== 'join') inviteCode.value = ''
  resetErrors()
}

function close() {
  emit('close')
}

function startCountdown() {
  remainingSeconds.value = 60
  if (countdownTimer) clearInterval(countdownTimer)
  countdownTimer = setInterval(() => {
    remainingSeconds.value -= 1
    if (remainingSeconds.value <= 0 && countdownTimer) {
      clearInterval(countdownTimer)
      countdownTimer = null
    }
  }, 1000)
}

async function sendSmsAfterCaptcha(validate?: CaptchaValidate) {
  const result = await sendSmsCode(phone.value.trim(), 'login', validate)
  isSendingCode.value = false
  if (!result.ok) {
    errorMessage.value = result.message || t('api.auth.send_code_failed')
    return
  }
  successMessage.value = result.message || t('api.auth.code_sent')
  startCountdown()
}

async function ensureCaptcha(captchaId: string): Promise<CaptchaInstance> {
  if (captchaInstance.value) return captchaInstance.value
  await loadCaptchaScript()
  return await new Promise<CaptchaInstance>((resolve, reject) => {
    const initAlicom4 = (window as any).initAlicom4
    if (typeof initAlicom4 !== 'function') {
      reject(new Error(t('login.captcha_init_failed')))
      return
    }
    initAlicom4(
      { captchaId, product: 'bind' },
      (instance: CaptchaInstance) => {
        if (!instance) {
          reject(new Error(t('login.captcha_init_failed')))
          return
        }
        captchaInstance.value = instance
        instance
          .onNextReady(() => {
            captchaReady.value = true
            if (pendingShowCaptcha.value) {
              pendingShowCaptcha.value = false
              instance.showCaptcha()
            }
          })
          .onSuccess(() => {
            const validate = instance.getValidate()
            if (!validate) {
              isSendingCode.value = false
              errorMessage.value = t('login.complete_captcha')
              return
            }
            void sendSmsAfterCaptcha(validate)
            instance.reset()
          })
          .onError(() => {
            isSendingCode.value = false
            captchaReady.value = false
            errorMessage.value = t('login.verify_captcha_failed')
          })
          .onClose(() => {
            isSendingCode.value = false
          })
        resolve(instance)
      },
    )
  })
}

async function handleSendSmsCode() {
  resetErrors()
  if (sendButtonDisabled.value) return
  if (!phone.value.trim()) {
    errorMessage.value = t('login.phone_empty')
    return
  }
  isSendingCode.value = true
  const config = await fetchCaptchaConfig()
  if (!config.ok) {
    isSendingCode.value = false
    errorMessage.value = config.message || t('api.auth.get_captcha_failed')
    return
  }
  if (!config.enabled) {
    await sendSmsAfterCaptcha()
    return
  }
  if (!config.captchaId) {
    isSendingCode.value = false
    errorMessage.value = t('login.captcha_config_invalid')
    return
  }
  try {
    const instance = await ensureCaptcha(config.captchaId)
    if (captchaReady.value) {
      instance.showCaptcha()
    } else {
      pendingShowCaptcha.value = true
    }
  } catch (error: any) {
    isSendingCode.value = false
    errorMessage.value = error?.message || t('login.captcha_error_retry')
  }
}

async function handleSubmit() {
  resetErrors()
  if (pendingSelection.value) {
    if (!selectedMainId.value) {
      errorMessage.value = t('api.auth.select_org')
      return
    }
    isSubmitting.value = true
    const selectResult = await selectTenantAndLogin(challengeToken.value, selectedMainId.value)
    isSubmitting.value = false
    if (!selectResult.ok || !selectResult.token) {
      errorMessage.value = selectResult.message || t('api.auth.login_failed')
      return
    }
    emit('login-success', { token: selectResult.token, username: phone.value.trim(), profile: selectResult.profile })
    return
  }

  if (!phone.value.trim()) {
    errorMessage.value = t('login.phone_empty')
    return
  }
  if (!smsCode.value.trim()) {
    errorMessage.value = t('login.code_empty')
    return
  }
  if (orgMode.value === 'create' && !orgName.value.trim()) {
    errorMessage.value = t('login.org_name_empty')
    return
  }
  if (orgMode.value === 'join' && !inviteCode.value.trim()) {
    errorMessage.value = t('login.invite_code_empty')
    return
  }

  isSubmitting.value = true
  const loginResult = await loginWithPhoneCode(
    phone.value.trim(),
    smsCode.value.trim(),
    orgMode.value === 'join' ? inviteCode.value.trim() : '',
    orgMode.value === 'create' ? orgName.value.trim() : '',
  )
  if (loginResult.requiresTenantSelection) {
    isSubmitting.value = false
    challengeToken.value = loginResult.challengeToken || ''
    tenantCandidates.value = loginResult.tenantCandidates || []
    selectedMainId.value = tenantCandidates.value[0]?.mainId || ''
    errorMessage.value = loginResult.message || t('api.auth.select_org')
    return
  }
  if (!loginResult.ok || !loginResult.token) {
    isSubmitting.value = false
    errorMessage.value = loginResult.message || t('api.auth.login_failed')
    return
  }

  isSubmitting.value = false
  emit('login-success', { token: loginResult.token, username: phone.value.trim(), profile: loginResult.profile })
}

onBeforeUnmount(() => {
  if (countdownTimer) {
    clearInterval(countdownTimer)
    countdownTimer = null
  }
  captchaInstance.value?.destroy?.()
  captchaInstance.value = null
})
</script>

<template>
  <div v-if="open" class="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4">
    <div class="w-full max-w-md rounded-3xl bg-white p-6 shadow-2xl">
      <div class="flex items-start justify-between gap-4">
        <div class="flex items-start gap-3">
          <img src="/movo-logo.png" alt="MOVO" class="mt-0.5 h-10 w-12 shrink-0 object-contain" />
          <div>
            <div class="text-xl font-semibold text-slate-900">{{ t('login.title') }}</div>
            <div class="mt-1 text-sm leading-5 text-slate-500">{{ loginMethod === 'password' ? t('login.password_desc') : t('login.desc') }}</div>
          </div>
        </div>
        <button class="rounded-full p-2 text-slate-400 transition-colors hover:bg-slate-100" :aria-label="t('login.close_aria')" @click="close">
          <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M18 6 6 18" />
            <path d="m6 6 12 12" />
          </svg>
        </button>
      </div>

      <LoginMethodTabs v-model="loginMethod" class="mt-6" />

      <PasswordLoginForm
        v-if="loginMethod === 'password'"
        class="mt-4"
        :suggested-username="savedUsers[0]"
        @login-success="emit('login-success', $event)"
      />

      <form v-else class="mt-4 space-y-4" @submit.prevent="handleSubmit">
        <div class="space-y-2">
          <label class="text-sm font-medium text-slate-700">{{ t('login.phone_label') }}</label>
          <input
            v-model.trim="phone"
            type="tel"
            inputmode="tel"
            class="w-full rounded-2xl border border-slate-200 px-4 py-2.5 text-slate-900 outline-none transition-colors focus:border-slate-400"
            :placeholder="t('login.phone_placeholder')"
            @input="resetErrors"
          />
        </div>

        <div class="space-y-2">
          <label class="text-sm font-medium text-slate-700">{{ t('login.code_label') }}</label>
          <div class="flex gap-2">
            <input
              v-model.trim="smsCode"
              type="text"
              inputmode="numeric"
              class="min-w-0 flex-1 rounded-2xl border border-slate-200 px-4 py-2.5 text-slate-900 outline-none transition-colors focus:border-slate-400"
              :placeholder="t('login.code_placeholder')"
              @input="resetErrors"
            />
            <button
              type="button"
              class="min-h-[44px] shrink-0 rounded-2xl border border-slate-200 px-4 text-sm font-semibold text-slate-700 transition-colors hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
              :disabled="sendButtonDisabled"
              @click="handleSendSmsCode"
            >
              {{ sendButtonText }}
            </button>
          </div>
        </div>

        <div v-if="!pendingSelection" class="space-y-3">
          <div class="grid grid-cols-3 gap-2 rounded-2xl bg-slate-100 p-1">
            <button
              type="button"
              class="min-h-[44px] rounded-xl px-2 text-sm font-semibold transition-colors"
              :class="orgMode === 'personal' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-700'"
              @click="selectOrgMode('personal')"
            >
              {{ t('login.personal_use') }}
            </button>
            <button
              type="button"
              class="min-h-[44px] rounded-xl px-2 text-sm font-semibold transition-colors"
              :class="orgMode === 'create' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-700'"
              @click="selectOrgMode('create')"
            >
              {{ t('login.create_org') }}
            </button>
            <button
              type="button"
              class="min-h-[44px] rounded-xl px-2 text-sm font-semibold transition-colors"
              :class="orgMode === 'join' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-700'"
              @click="selectOrgMode('join')"
            >
              {{ t('login.join_org') }}
            </button>
          </div>

          <div v-if="orgMode === 'create'" class="space-y-2">
            <label class="text-sm font-medium text-slate-700">{{ t('org_create.name_label') }}</label>
            <input
              v-model.trim="orgName"
              type="text"
              class="w-full rounded-2xl border border-slate-200 bg-white px-4 py-2.5 text-slate-900 outline-none transition-colors focus:border-slate-400"
              :placeholder="t('org_create.name_placeholder')"
              @input="resetErrors"
            />
            <p class="text-xs leading-5 text-slate-500">{{ t('login.create_org_desc') }}</p>
          </div>

          <div v-else-if="orgMode === 'join'" class="space-y-2">
            <label class="text-sm font-medium text-slate-700">{{ t('login.invite_code_label') }}</label>
            <input
              v-model.trim="inviteCode"
              type="text"
              class="w-full rounded-2xl border border-slate-200 bg-white px-4 py-2.5 text-slate-900 outline-none transition-colors focus:border-slate-400"
              :placeholder="t('login.invite_code_placeholder')"
              @input="resetErrors"
            />
          </div>
        </div>

        <div v-if="pendingSelection" class="space-y-2">
          <label class="text-sm font-medium text-slate-700">{{ t('login.select_org_label') }}</label>
          <select
            v-model="selectedMainId"
            class="w-full rounded-2xl border border-slate-200 px-4 py-2.5 text-slate-900 outline-none focus:border-slate-400"
            @change="resetErrors"
          >
            <option v-for="tenant in tenantCandidates" :key="tenant.mainId" :value="tenant.mainId">
              {{ tenant.orgName || tenant.mainId }}
            </option>
          </select>
        </div>

        <p v-if="errorMessage" class="rounded-2xl bg-rose-50 px-3 py-2 text-sm text-rose-600">
          {{ errorMessage }}
        </p>
        <p v-if="successMessage" class="rounded-2xl bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
          {{ successMessage }}
        </p>

        <button
          type="submit"
          class="w-full rounded-2xl bg-slate-900 py-3 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-70"
          :disabled="submitDisabled"
        >
          {{ submitText }}
        </button>
      </form>

      <div class="mt-4 rounded-2xl bg-slate-50 px-3 py-2 text-xs leading-5 text-slate-500">
        {{ helperText }}
      </div>
    </div>
  </div>
</template>
