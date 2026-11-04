<script setup lang="ts">
import { t } from '../../../composables/i18n'

defineProps<{ error: string }>()
</script>

<template>
  <details class="tool-error-details">
    <summary :aria-label="t('execution.v3.tool_attempt_details')" :title="t('execution.v3.tool_attempt_details')">
      <svg viewBox="0 0 16 16" aria-hidden="true"><path d="m5 3 5 5-5 5" /></svg>
      <span class="sr-only">{{ t('execution.v3.tool_attempt_details') }}</span>
    </summary>
    <pre>{{ error }}</pre>
  </details>
</template>

<style scoped>
.tool-error-details { flex: none; color: #64748b; }
.tool-error-details summary { display: flex; width: 24px; height: 24px; align-items: center; justify-content: center; border-radius: 6px; cursor: pointer; list-style: none; }
.tool-error-details summary::-webkit-details-marker { display: none; }
.tool-error-details summary:hover { background: #f1f5f9; }
.tool-error-details summary:focus-visible { outline: 2px solid #2563eb; outline-offset: 2px; }
.tool-error-details svg { width: 14px; height: 14px; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; transition: transform .16s ease; }
.tool-error-details[open] svg { transform: rotate(90deg); }
.tool-error-details pre { max-height: 220px; margin: 6px 0; overflow: auto; padding: 10px 12px; border-radius: 8px; background: #f8fafc; color: #475569; font: 11px/1.5 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; white-space: pre-wrap; overflow-wrap: anywhere; }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
</style>
