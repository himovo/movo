<script setup lang="ts">
import { ref, watch } from 'vue'

const props = defineProps<{
  modelValue: string
  disabled?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void
}>()

const digits = ref<string[]>(['', '', '', '', '', ''])
const inputs = ref<HTMLInputElement[]>([])

watch(
  () => props.modelValue,
  (value) => {
    const normalized = (value || '').slice(0, 6).split('')
    digits.value = Array.from({ length: 6 }, (_, idx) => normalized[idx] || '')
  },
  { immediate: true }
)

function setInputRef(el: HTMLInputElement | null, index: number) {
  if (el) inputs.value[index] = el
}

function focusIndex(index: number) {
  const target = inputs.value[index]
  if (target) target.focus()
}

function handleInput(event: Event, index: number) {
  const target = event.target as HTMLInputElement
  const value = target.value.replace(/\D/g, '')
  digits.value[index] = value.slice(0, 1)
  emit('update:modelValue', digits.value.join(''))
  if (value && index < inputs.value.length - 1) {
    focusIndex(index + 1)
  }
}

function handleKeydown(event: KeyboardEvent, index: number) {
  if (event.key === 'Backspace' && !digits.value[index] && index > 0) {
    focusIndex(index - 1)
  }
  if (event.key === 'ArrowLeft' && index > 0) {
    event.preventDefault()
    focusIndex(index - 1)
  }
  if (event.key === 'ArrowRight' && index < inputs.value.length - 1) {
    event.preventDefault()
    focusIndex(index + 1)
  }
}

function handlePaste(event: ClipboardEvent) {
  const text = event.clipboardData?.getData('text') || ''
  const digitsOnly = text.replace(/\D/g, '').slice(0, 6)
  if (!digitsOnly) return
  digits.value = Array.from({ length: 6 }, (_, idx) => digitsOnly[idx] || '')
  emit('update:modelValue', digits.value.join(''))
  if (digitsOnly.length === 6) {
    focusIndex(5)
  }
}
</script>

<template>
  <div class="flex items-center gap-2">
    <input
      v-for="(_, index) in digits"
      :key="index"
      :ref="(el) => setInputRef(el as HTMLInputElement | null, index)"
      type="text"
      inputmode="numeric"
      pattern="[0-9]*"
      maxlength="1"
      :disabled="disabled"
      class="h-11 w-11 rounded-xl border border-slate-200 text-center text-lg font-semibold text-slate-800 outline-none transition focus:border-slate-400"
      :value="digits[index]"
      @input="handleInput($event, index)"
      @keydown="handleKeydown($event, index)"
      @paste.prevent="handlePaste"
    />
  </div>
</template>
