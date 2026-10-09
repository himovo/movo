<script setup lang="ts">
import { t } from '../../composables/i18n'
</script>

<template>
  <div class="mx-auto flex w-full max-w-4xl items-center gap-2 px-4 pb-3 text-xs text-slate-500 md:px-6" role="status" aria-live="polite">
    <span class="h-3.5 w-3.5 animate-spin rounded-full border-2 border-slate-300 border-t-blue-500" aria-hidden="true" />
    {{ t('code.history_restoring') }}
  </div>
</template>
