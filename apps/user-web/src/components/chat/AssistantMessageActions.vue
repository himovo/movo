<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import type { ChatMessage } from './chatMessage'
import type { Locale } from '../../locales/messages'
import { copyTextToClipboard } from '../../utils/copyTextToClipboard'
import { assistantMessageTime, formatConversationClock, formatFullConversationTime } from '../../utils/conversationTime'
import { t } from '../../composables/i18n'

const props = defineProps<{ message: ChatMessage; locale: Locale; live: boolean }>()
const copied = ref(false)
let timer: ReturnType<typeof setTimeout> | undefined
const time = computed(() => props.live ? null : assistantMessageTime(props.message))
const clock = computed(() => time.value ? formatConversationClock(time.value.value, props.locale) : '')
const fullTime = computed(() => time.value ? formatFullConversationTime(time.value.value, props.locale) : '')
async function copy() {
  try {
    await copyTextToClipboard(props.message.content)
    copied.value = true
    if (timer) clearTimeout(timer)
    timer = setTimeout(() => { copied.value = false }, 1500)
  } catch {
    copied.value = false
  }
}
onBeforeUnmount(() => { if (timer) clearTimeout(timer) })
</script>

<template>
  <div v-if="message.content && !live" class="assistant-actions" role="group" :aria-label="t('legacy.message_actions')">
    <button type="button" class="assistant-actions__copy" :aria-label="copied ? t('legacy.copied') : t('legacy.copy_message')" :title="copied ? t('legacy.copied') : t('legacy.copy')" @click="copy">
      <svg v-if="copied" viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12 4 4L19 6" /></svg>
      <svg v-else viewBox="0 0 24 24" aria-hidden="true"><rect x="8" y="8" width="11" height="11" rx="2"/><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3"/></svg>
    </button>
    <time v-if="clock" :title="fullTime" :datetime="typeof time?.value === 'number' ? new Date(time.value).toISOString() : time?.value">{{ clock }}</time>
  </div>
</template>

<style scoped>
.assistant-actions{display:flex;align-items:center;gap:8px;margin-top:10px;color:#94a3b8;font-size:11px}.assistant-actions__copy{display:grid;place-items:center;width:28px;height:28px;border:0;border-radius:7px;background:transparent;color:#64748b;cursor:pointer}.assistant-actions__copy:hover{background:#f1f5f9;color:#334155}.assistant-actions__copy:focus-visible{outline:2px solid #3b82f6;outline-offset:2px}.assistant-actions__copy svg{width:16px;height:16px;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}
</style>
