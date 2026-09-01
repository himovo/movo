<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue'
import { t } from '../../composables/i18n'

const props = defineProps<{ text: string; time?: string; scheduleDisabled?: boolean }>()
const emit = defineEmits<{ (e: 'schedule'): void }>()
const copied = ref(false)
let copiedTimer: ReturnType<typeof setTimeout> | null = null

async function copyMessage() {
  try {
    await navigator.clipboard.writeText(props.text)
  } catch {
    const input = document.createElement('textarea')
    input.value = props.text
    input.style.position = 'fixed'
    input.style.opacity = '0'
    document.body.appendChild(input)
    input.select()
    document.execCommand('copy')
    input.remove()
  }
  copied.value = true
  if (copiedTimer) clearTimeout(copiedTimer)
  copiedTimer = setTimeout(() => { copied.value = false }, 1500)
}

onBeforeUnmount(() => { if (copiedTimer) clearTimeout(copiedTimer) })
</script>

<template>
  <div class="flex items-center justify-end gap-0.5 text-slate-500" role="group" :aria-label="t('消息操作')">
    <time v-if="time" class="mr-1 whitespace-nowrap text-[11px] text-slate-400">{{ time }}</time>
    <button
      type="button"
      class="inline-flex h-7 w-7 cursor-pointer items-center justify-center rounded-md transition-colors duration-150 hover:bg-slate-100 hover:text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-500"
      :aria-label="copied ? t('已复制') : t('复制消息')"
      :title="copied ? t('已复制') : t('复制')"
      @click="copyMessage"
    >
      <svg v-if="copied" viewBox="0 0 24 24" class="h-4 w-4 text-emerald-600" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m5 12 4 4L19 6" /></svg>
      <svg v-else viewBox="0 0 24 24" class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="8" y="8" width="11" height="11" rx="2"/><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3"/></svg>
    </button>
    <button
      type="button"
      class="inline-flex h-7 w-7 cursor-pointer items-center justify-center rounded-md transition-colors duration-150 hover:bg-blue-50 hover:text-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:cursor-not-allowed disabled:opacity-50"
      :disabled="scheduleDisabled"
      :aria-label="t('创建定时任务')"
      :title="t('创建定时任务')"
      @click="emit('schedule')"
    >
      <svg viewBox="0 0 24 24" class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>
    </button>
  </div>
</template>
