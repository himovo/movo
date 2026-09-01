<script setup lang="ts">
import { t } from '../../composables/i18n'

export type LoginMethod = 'password' | 'sms'

defineProps<{ modelValue: LoginMethod }>()

const emit = defineEmits<{
  (event: 'update:modelValue', value: LoginMethod): void
}>()
</script>

<template>
  <div class="grid grid-cols-2 gap-1 rounded-2xl bg-slate-100 p-1" role="tablist" :aria-label="t('login.method_label')">
    <button
      v-for="method in (['password', 'sms'] as LoginMethod[])"
      :key="method"
      type="button"
      role="tab"
      class="min-h-[44px] rounded-xl px-3 text-sm font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400"
      :class="modelValue === method ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-700'"
      :aria-selected="modelValue === method"
      @click="emit('update:modelValue', method)"
    >
      {{ t(`login.method.${method}`) }}
    </button>
  </div>
</template>
