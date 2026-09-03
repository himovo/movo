<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { capabilities, connectEnterpriseServer, getSettings } from '../../platform'
import { t } from '../../composables/i18n'

const expanded = ref(false)
const currentAddress = ref('')
const address = ref('')
const connecting = ref(false)
const error = ref('')

const normalizeAddress = (value: string) => value.trim().replace(/\/+$/, '')
const addressChanged = computed(() => normalizeAddress(address.value) !== normalizeAddress(currentAddress.value))

onMounted(async () => {
  if (!capabilities.isDesktop) return
  const settings = await getSettings().catch(() => null)
  currentAddress.value = settings?.service_url || ''
  address.value = currentAddress.value
})

async function switchServer() {
  if (connecting.value || !address.value.trim() || !addressChanged.value) return
  connecting.value = true
  error.value = ''
  try {
    await connectEnterpriseServer(address.value)
    for (const key of ['auth_token', 'auth_account', 'auth_users', 'auth_user_profile']) {
      localStorage.removeItem(key)
    }
    window.location.reload()
  } catch (reason: any) {
    error.value = String(reason?.message || reason)
  } finally {
    connecting.value = false
  }
}
</script>

<template>
  <section v-if="capabilities.isDesktop" class="mt-5 border-t border-slate-100 pt-4">
    <button
      type="button"
      class="flex min-h-[44px] w-full cursor-pointer items-center justify-between gap-3 rounded-xl px-2 text-left transition-colors hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2"
      :aria-expanded="expanded"
      aria-controls="desktop-login-server-settings"
      @click="expanded = !expanded"
    >
      <span class="min-w-0">
        <span class="block text-xs font-medium text-slate-500">{{ t('login.server.current') }}</span>
        <span class="block truncate text-xs text-slate-400">
          {{ currentAddress || t('login.server.not_configured') }}
        </span>
      </span>
      <span class="flex shrink-0 items-center gap-1 text-xs font-medium text-slate-500">
        {{ t('login.server.change') }}
        <svg
          class="h-4 w-4 transition-transform duration-200"
          :class="expanded ? 'rotate-180' : ''"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          aria-hidden="true"
        >
          <path d="m6 9 6 6 6-6" />
        </svg>
      </span>
    </button>

    <form
      v-if="expanded"
      id="desktop-login-server-settings"
      class="mt-3 rounded-2xl border border-slate-200 bg-slate-50 p-4"
      @submit.prevent="switchServer"
    >
      <label for="desktop-login-service-url" class="text-sm font-medium text-slate-700">
        {{ t('settings.service_url') }}
      </label>
      <input
        id="desktop-login-service-url"
        v-model.trim="address"
        type="text"
        inputmode="url"
        autocomplete="url"
        spellcheck="false"
        class="mt-2 min-h-[44px] w-full rounded-xl border border-slate-200 bg-white px-3 font-mono text-xs text-slate-900 outline-none transition-colors focus:border-blue-500 focus:ring-2 focus:ring-blue-100 disabled:cursor-not-allowed disabled:opacity-60"
        placeholder="https://movo.company.com"
        :disabled="connecting"
        @input="error = ''"
      />
      <p class="mt-2 text-xs leading-5 text-slate-500">{{ t('login.server.help') }}</p>
      <p v-if="error" role="alert" class="mt-2 text-xs leading-5 text-red-600">{{ error }}</p>
      <button
        type="submit"
        class="mt-3 min-h-[44px] w-full cursor-pointer rounded-xl bg-slate-900 px-4 text-sm font-semibold text-white transition-colors hover:bg-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
        :disabled="connecting || !address.trim() || !addressChanged"
      >
        {{ connecting ? t('desktop.server.validating') : t('login.server.switch') }}
      </button>
    </form>
  </section>
</template>
