<script setup lang="ts">
import { computed } from 'vue'
import { getLocale } from '../../composables/i18n'
import { useDesktopCompatibility } from '../../composables/desktop/useDesktopCompatibility'
import { desktopCompatibilityMessages } from '../../locales/desktopCompatibilityMessages'

const props = withDefaults(defineProps<{ candidate?: boolean; inline?: boolean }>(), { candidate: false, inline: false })
const state = useDesktopCompatibility()
const assessment = computed(() => props.candidate ? state.value.candidate : state.value.current)
const visible = computed(() => assessment.value?.level === 'server-older' || assessment.value?.level === 'client-older')
const message = computed(() => {
  const level = assessment.value?.level
  if (level !== 'server-older' && level !== 'client-older') return ''
  const locale = getLocale()
  const prefix = props.candidate ? desktopCompatibilityMessages.candidate[locale] : ''
  return `${prefix}${desktopCompatibilityMessages[level][locale]}`
})
</script>

<template>
  <div v-if="visible && !inline" class="desktop-compatibility-notice desktop-compatibility-notice--icon" :aria-label="message" role="status" tabindex="0">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
      <path d="M12 3 2 21h20L12 3Z M12 9v5 M12 18h.01" />
    </svg>
    <span class="desktop-compatibility-notice__tooltip" role="tooltip">{{ message }}</span>
  </div>
  <div v-else-if="visible" class="desktop-compatibility-notice desktop-compatibility-notice--inline" :aria-label="message" role="status">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
      <path d="M12 3 2 21h20L12 3Z M12 9v5 M12 18h.01" />
    </svg>
    <span>{{ message }}</span>
  </div>
</template>

<style scoped>
.desktop-compatibility-notice { display:inline-flex; align-items:center; justify-content:center; min-width:34px; min-height:34px; color:#b45309; cursor:help; -webkit-app-region:no-drag; }
.desktop-compatibility-notice svg { width:18px; height:18px; flex:none; }
.desktop-compatibility-notice--icon { position:relative; }
.desktop-compatibility-notice__tooltip { position:absolute; z-index:100; top:calc(100% + 6px); right:0; width:max-content; max-width:min(360px, calc(100vw - 24px)); padding:8px 10px; border-radius:8px; background:#172033; color:#f8fafc; font-size:12px; line-height:1.5; white-space:normal; box-shadow:0 8px 24px rgb(15 23 42 / 18%); opacity:0; visibility:hidden; pointer-events:none; }
.desktop-compatibility-notice--icon:hover .desktop-compatibility-notice__tooltip, .desktop-compatibility-notice--icon:focus-visible .desktop-compatibility-notice__tooltip { opacity:1; visibility:visible; }
.desktop-compatibility-notice--inline { justify-content:flex-start; gap:8px; width:100%; padding:8px 10px; border-radius:10px; background:#fffbeb; color:#92400e; font-size:12px; line-height:1.5; }
.desktop-compatibility-notice:not(.desktop-compatibility-notice--inline):focus-visible { outline:2px solid currentColor; border-radius:6px; }
:global(html.theme-dark) .desktop-compatibility-notice--inline { background:#422006; color:#fcd34d; }
</style>
