<template>
  <div class="flex h-full items-center justify-center bg-white px-6 text-center text-slate-600">
    <div>
      <p>{{ english ? 'The chat view could not load.' : '对话界面加载失败。' }}</p>
      <button class="mt-3 rounded-lg bg-blue-600 px-4 py-2 text-white" @click="reload">
        {{ english ? 'Reload' : '刷新重试' }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useLocale } from '../composables/i18n'

const { locale } = useLocale()
const english = locale.value === 'en'
function reload() { window.location.reload() }
</script>
