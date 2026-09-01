<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { NAlert, NButton, NInput } from 'naive-ui'
import { connectEnterpriseServer, getSettings } from '../../platform'
import { t } from '../../composables/i18n'

const emit = defineEmits<{ connected: [] }>()
const address = ref('')
const connecting = ref(false)
const error = ref('')

onMounted(async () => {
  const settings = await getSettings().catch(() => null)
  address.value = settings?.service_url || ''
})

async function connect() {
  if (connecting.value) return
  connecting.value = true
  error.value = ''
  try {
    await connectEnterpriseServer(address.value)
    emit('connected')
  } catch (reason: any) {
    error.value = String(reason?.message || reason)
  } finally {
    connecting.value = false
  }
}
</script>

<template>
  <main class="min-h-screen bg-slate-50 px-6 py-16 text-slate-900">
    <div class="fixed inset-x-0 top-0 h-12" style="-webkit-app-region: drag" aria-hidden="true"></div>
    <section class="mx-auto grid w-full max-w-5xl overflow-hidden rounded-[28px] border border-slate-200 bg-white shadow-[0_24px_80px_rgba(15,23,42,0.12)] md:grid-cols-[0.9fr_1.1fr]">
      <div class="flex flex-col justify-between bg-[#173f9f] p-10 text-white md:p-12">
        <div>
          <div class="mb-10 flex h-14 w-16 items-center justify-center rounded-2xl border border-white/25 bg-white/10" aria-hidden="true">
            <img src="/movo-logo.png" alt="" class="h-10 w-12 object-contain" />
          </div>
          <p class="text-xs font-semibold uppercase tracking-[0.22em] text-blue-100">MOVO Desktop</p>
          <h1 class="mt-4 text-3xl font-semibold leading-tight">{{ t('desktop.server.title') }}</h1>
          <p class="mt-4 max-w-sm text-sm leading-6 text-blue-100">{{ t('desktop.server.description') }}</p>
        </div>
        <div class="mt-12 flex items-start gap-3 border-t border-white/15 pt-6 text-xs leading-5 text-blue-100">
          <svg class="mt-0.5 h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z"/><path d="m9 12 2 2 4-4"/></svg>
          <span>{{ t('desktop.server.privacy') }}</span>
        </div>
      </div>

      <form class="flex flex-col justify-center p-10 md:p-14" @submit.prevent="connect">
        <p class="text-xs font-semibold uppercase tracking-[0.18em] text-blue-600">{{ t('desktop.server.first_use') }}</p>
        <h2 class="mt-3 text-2xl font-semibold">{{ t('desktop.server.connect_heading') }}</h2>
        <p class="mt-2 text-sm leading-6 text-slate-500">{{ t('desktop.server.hint') }}</p>

        <label for="enterprise-service-url" class="mt-8 text-sm font-medium text-slate-700">{{ t('desktop.server.address') }}</label>
        <n-input
          id="enterprise-service-url"
          v-model:value="address"
          size="large"
          class="mt-2"
          placeholder="https://movo.company.com"
          :disabled="connecting"
          :input-props="{ spellcheck: false, autocomplete: 'url', inputmode: 'url' }"
        />
        <p class="mt-2 text-xs leading-5 text-slate-400">{{ t('desktop.server.example') }}</p>
        <n-alert v-if="error" class="mt-5" type="error" :show-icon="true">{{ error }}</n-alert>

        <n-button
          attr-type="submit"
          type="primary"
          size="large"
          class="mt-7 !h-12 !rounded-xl"
          :loading="connecting"
          :disabled="connecting || !address.trim()"
          block
        >
          {{ connecting ? t('desktop.server.validating') : t('desktop.server.connect') }}
        </n-button>
        <p class="mt-4 text-center text-xs text-slate-400">{{ t('desktop.server.saved') }}</p>
      </form>
    </section>
  </main>
</template>
