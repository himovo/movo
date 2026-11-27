<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { Locale } from '../../composables/i18n'
import { collapsibleUserTextLabels as labels } from '../../locales/collapsibleUserTextMessages'

const props = defineProps<{ text: string; locale: Locale }>()
const content = ref<HTMLElement | null>(null)
const container = ref<HTMLElement | null>(null)
const expanded = ref(false)
const overflowing = ref(false)
let observer: ResizeObserver | undefined
function measure() {
  overflowing.value = (content.value?.getBoundingClientRect().height ?? 0) > 336 + 1
}
watch(() => props.text, async () => {
  expanded.value = false
  await nextTick()
  measure()
})
onMounted(() => {
  observer = new ResizeObserver(measure)
  if (content.value) observer.observe(content.value)
  measure()
})
onBeforeUnmount(() => observer?.disconnect())
async function toggle() {
  expanded.value = !expanded.value
  await nextTick()
  if (!expanded.value && (container.value?.getBoundingClientRect().top ?? 0) < 0) {
    container.value?.scrollIntoView({ block: 'start' })
  }
}
</script>

<template>
  <div ref="container">
    <div class="user-text-viewport" :class="{ 'user-text-collapsed': overflowing && !expanded }">
      <div ref="content" class="user-text-copy">{{ text }}</div>
    </div>
    <button v-if="overflowing" type="button" class="user-text-toggle" :aria-expanded="expanded" @click="toggle">
      {{ labels[locale][expanded ? 'less' : 'more'] }}
      <svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true" :class="{ 'user-text-chevron-up': expanded }"><path d="m4 6 4 4 4-4" /></svg>
    </button>
  </div>
</template>

<style scoped>
.user-text-copy { white-space: pre-wrap; overflow-wrap: anywhere; line-height: 1.75rem; }
.user-text-collapsed { max-height: 336px; overflow: hidden; mask-image: linear-gradient(to bottom, #000 calc(100% - 24px), transparent); }
.user-text-toggle { display: flex; align-items: center; gap: 6px; margin-top: 12px; border-radius: 4px; font-size: 14px; font-weight: 500; color: inherit; }
.user-text-toggle:hover { opacity: .7; }
.user-text-toggle:focus-visible { outline: 2px solid currentColor; outline-offset: 4px; }
.user-text-chevron-up { transform: rotate(180deg); }
</style>
