<script setup lang="ts">
import { computed } from 'vue'
import { getLocale } from '../../composables/i18n'
import { useDesktopCompatibility } from '../../composables/desktop/useDesktopCompatibility'
import { desktopCompatibilityMessages } from '../../locales/desktopCompatibilityMessages'

const props = withDefaults(defineProps<{ candidate?: boolean; inline?: boolean }>(), { candidate: false, inline: false })
const state = useDesktopCompatibility()
const assessment = computed(() => props.candidate ? state.value.candidate : state.value.current)
const visible = computed(() => assessment.value && !['aligned', 'unconfigured'].includes(assessment.value.level))
const warning = computed(() => assessment.value?.level !== 'unavailable')
const message = computed(() => {
  const level = assessment.value?.level
  if (!level || level === 'aligned' || level === 'unconfigured') return ''
  const locale = getLocale()
  const prefix = props.candidate ? desktopCompatibilityMessages.candidate[locale] : ''
  return `${prefix}${desktopCompatibilityMessages[level][locale]}`
})
</script>

<template>
  <div v-if="visible" class="desktop-compatibility-notice" :class="{ 'desktop-compatibility-notice--inline': inline }" :title="message" :aria-label="message" role="status" tabindex="0">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
      <path v-if="warning" d="M12 3 2 21h20L12 3Z M12 9v5 M12 18h.01" />
      <template v-else><circle cx="12" cy="12" r="10" /><path d="M12 11v5 M12 7h.01" /></template>
    </svg>
    <span v-if="inline">{{ message }}</span>
  </div>
</template>

<style scoped>
.desktop-compatibility-notice { display:inline-flex; align-items:center; justify-content:center; min-width:34px; min-height:34px; color:#b45309; cursor:help; -webkit-app-region:no-drag; }
.desktop-compatibility-notice svg { width:18px; height:18px; flex:none; }
.desktop-compatibility-notice--inline { justify-content:flex-start; gap:8px; width:100%; padding:8px 10px; border-radius:10px; background:#fffbeb; color:#92400e; font-size:12px; line-height:1.5; }
.desktop-compatibility-notice:not(.desktop-compatibility-notice--inline):focus-visible { outline:2px solid currentColor; border-radius:6px; }
:global(html.theme-dark) .desktop-compatibility-notice--inline { background:#422006; color:#fcd34d; }
</style>
