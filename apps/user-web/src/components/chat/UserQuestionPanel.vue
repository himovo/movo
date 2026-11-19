<script setup lang="ts">
import { reactive, watch } from 'vue'
import { t } from '../../composables/i18n'
import type { DshPendingQuestion, DshQuestionAnswer, DshUserQuestion } from '../../platform/types'

const props = defineProps<{ item: DshPendingQuestion; busy?: boolean; error?: string }>()
const emit = defineEmits<{ submit: [answers: DshQuestionAnswer[]] }>()
const selected = reactive<Record<string, string[]>>({})
const custom = reactive<Record<string, string>>({})
const useCustom = reactive<Record<string, boolean>>({})

watch(() => props.item.id, () => {
  for (const key of Object.keys(selected)) delete selected[key]
  for (const key of Object.keys(custom)) delete custom[key]
  for (const key of Object.keys(useCustom)) delete useCustom[key]
}, { immediate: true })

function choices(question: DshUserQuestion) {
  return Array.isArray(question.options) ? question.options : []
}

function choose(question: DshUserQuestion, label: string) {
  if (!question.multiSelect) {
    useCustom[question.id] = false
    selected[question.id] = [label]
    return
  }
  const current = selected[question.id] || []
  selected[question.id] = current.includes(label)
    ? current.filter(item => item !== label) : [...current, label]
}

function valid(question: DshUserQuestion) {
  if (useCustom[question.id] && !question.multiSelect) return Boolean(custom[question.id]?.trim())
  return Boolean(selected[question.id]?.length || (useCustom[question.id] && custom[question.id]?.trim()))
}

function submit() {
  if (props.busy || !props.item.questions.every(valid)) return
  emit('submit', props.item.questions.map(question => ({
    id: question.id,
    selected: useCustom[question.id] && !question.multiSelect ? [] : [...(selected[question.id] || [])],
    ...(useCustom[question.id] && custom[question.id]?.trim() ? { custom: custom[question.id].trim() } : {}),
  })))
}
</script>

<template>
  <section class="mb-2 overflow-hidden rounded-xl border border-blue-200 bg-white shadow-[0_8px_24px_rgba(28,75,151,0.10)]" aria-live="polite">
    <div class="flex items-center gap-2.5 border-b border-blue-100 bg-blue-50/70 px-4 py-2">
      <div class="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-blue-100 text-blue-700" aria-hidden="true">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.5 2.5 0 1 1 4.3 1.7c-1.1 1-1.8 1.4-1.8 2.8"/><path d="M12 17h.01"/></svg>
      </div>
      <div>
        <h3 class="text-sm font-semibold text-slate-900">{{ t('chat.question.title') }}</h3>
      </div>
    </div>
    <div class="max-h-[min(45vh,400px)] space-y-2 overflow-y-auto px-4 py-2.5">
      <fieldset v-for="(question, index) in item.questions" :key="question.id" class="space-y-1.5">
        <p v-if="question.header && item.questions.length > 1" class="text-xs font-semibold uppercase tracking-wide text-blue-600">{{ question.header }}</p>
        <legend class="text-sm font-medium leading-5 text-slate-900">
          <span v-if="item.questions.length > 1" class="mr-1 text-blue-600">{{ index + 1 }}.</span>{{ question.question }}
        </legend>
        <p v-if="question.detail" class="whitespace-pre-wrap text-xs leading-5 text-slate-500">{{ question.detail }}</p>
        <div v-if="choices(question).length" class="grid gap-2 sm:grid-cols-2">
          <button v-for="option in choices(question)" :key="option.label" type="button"
            class="flex min-h-9 items-start gap-2 rounded-lg border px-3 py-1.5 text-left transition-colors"
            :class="(!useCustom[question.id] || question.multiSelect) && selected[question.id]?.includes(option.label)
              ? 'border-blue-500 bg-blue-50 text-blue-800' : 'border-slate-200 bg-white text-slate-700 hover:border-blue-300 hover:bg-slate-50'"
            :aria-pressed="(!useCustom[question.id] || question.multiSelect) && selected[question.id]?.includes(option.label)"
            @click="choose(question, option.label)">
            <span class="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border text-[10px]" :class="selected[question.id]?.includes(option.label) && (!useCustom[question.id] || question.multiSelect) ? 'border-blue-600 bg-blue-600 text-white' : 'border-slate-300'">{{ selected[question.id]?.includes(option.label) && (!useCustom[question.id] || question.multiSelect) ? '✓' : '' }}</span>
            <span><span class="block text-sm font-medium">{{ option.label }}</span><span v-if="option.description" class="block text-xs leading-4 text-slate-500">{{ option.description }}</span></span>
          </button>
        </div>
        <button v-if="choices(question).length" type="button" class="text-xs font-medium text-blue-600 hover:text-blue-800" @click="useCustom[question.id] = true">{{ t('chat.question.other') }}</button>
        <textarea v-if="!choices(question).length || useCustom[question.id]" v-model="custom[question.id]" rows="2"
          class="block w-full resize-y rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-800 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
          :placeholder="t('chat.question.placeholder')" @input="useCustom[question.id] = true" />
      </fieldset>
      <p v-if="error" class="text-xs text-red-600" role="alert">{{ error }}</p>
    </div>
    <div class="flex justify-end border-t border-slate-100 px-4 py-1.5">
      <button type="button" class="rounded-lg bg-blue-600 px-4 py-1.5 text-sm font-medium text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-blue-300" :disabled="busy || !item.questions.every(valid)" @click="submit">
        {{ busy ? t('chat.question.submitting') : t('chat.question.submit') }}
      </button>
    </div>
  </section>
</template>
