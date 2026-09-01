<template>
  <div class="flex h-full w-full flex-col rounded-lg border border-gray-300 bg-white px-2 py-2 focus-within:ring-2 focus-within:ring-blue-200">
    <div v-if="suggestionsToShow.length" class="mb-2 flex-1 overflow-y-auto pr-1 custom-scrollbar">
      <div class="flex flex-wrap gap-2">
        <button
          v-for="item in suggestionsToShow"
          :key="item"
          type="button"
          class="rounded-full border border-gray-200 bg-gray-50 px-2 py-1 text-xs text-gray-600 transition-colors hover:border-blue-200 hover:bg-blue-50 hover:text-blue-700"
          @click="addSuggestion(item)"
        >
          {{ item }}
        </button>
      </div>
    </div>
    <div class="mt-auto flex flex-wrap gap-2">
      <span
        v-for="token in modelValue"
        :key="token"
        class="inline-flex items-center gap-1 rounded-full bg-blue-50 px-2 py-1 text-xs font-medium text-blue-700"
      >
        {{ token }}
        <button type="button" class="text-blue-500 hover:text-blue-700" @click="removeToken(token)">×</button>
      </span>
      <input
        v-model="draft"
        type="text"
        class="min-w-[140px] flex-1 border-0 p-0 text-sm focus:outline-none"
        :placeholder="placeholder"
        @keydown.enter.prevent="commitDraft"
        @blur="commitDraft"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'

const props = defineProps<{
  modelValue: string[]
  placeholder?: string
  suggestions?: string[]
}>()

const emit = defineEmits(['update:modelValue'])
const draft = ref('')

function commitDraft() {
  const next = draft.value.trim().replace(/,$/, '')
  if (!next) {
    draft.value = ''
    return
  }
  const values = [...props.modelValue]
  if (!values.some((item) => item.toLowerCase() === next.toLowerCase())) {
    values.push(next)
    emit('update:modelValue', values)
  }
  draft.value = ''
}

function removeToken(token: string) {
  emit(
    'update:modelValue',
    props.modelValue.filter((item) => item !== token),
  )
}

function addSuggestion(value: string) {
  const next = String(value || '').trim()
  if (!next) return
  if (!props.modelValue.some((item) => item.toLowerCase() === next.toLowerCase())) {
    emit('update:modelValue', [...props.modelValue, next])
  }
}

const suggestionsToShow = computed(() =>
  (props.suggestions || []).filter(
    (item) => !props.modelValue.some((token) => token.toLowerCase() === item.toLowerCase()),
  ),
)
</script>

<style scoped>
.custom-scrollbar::-webkit-scrollbar {
  width: 4px;
}

.custom-scrollbar::-webkit-scrollbar-track {
  background: transparent;
}

.custom-scrollbar::-webkit-scrollbar-thumb {
  background: #d1d5db;
  border-radius: 999px;
}
</style>
