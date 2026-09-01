<script setup lang="ts">
import { ref, watch } from 'vue'
import { useLocale } from '../../composables/i18n'

const props = defineProps<{ url: string }>()
const emit = defineEmits<{ (event: 'navigate', url: string): void }>()
const value = ref('')
const focused = ref(false)
const { locale } = useLocale()

watch(
  () => props.url,
  (url) => {
    if (!focused.value) value.value = /^about:blank(?:#.*)?$/i.test(url || '') ? '' : url
  },
  { immediate: true },
)

function submit() {
  const raw = value.value.trim()
  if (!raw) return
  const url = /^[a-z][a-z\d+.-]*:/i.test(raw) ? raw : `https://${raw}`
  value.value = url
  emit('navigate', url)
}

function focusAddress(event: FocusEvent) {
  focused.value = true
  const input = event.currentTarget as HTMLInputElement
  if (/^about:blank(?:#.*)?$/i.test(value.value)) value.value = ''
  else input.select()
}
</script>

<template>
  <form class="address-form" @submit.prevent="submit">
    <input
      v-model="value"
      class="address-input"
      aria-label="浏览器地址"
      :placeholder="locale === 'zh' ? '输入 URL' : 'Enter URL'"
      autocomplete="off"
      spellcheck="false"
      @focus="focusAddress"
      @blur="focused = false"
    />
  </form>
</template>

<style scoped>
.address-form { min-width: 0; width: 100%; }
.address-input { box-sizing: border-box; width: 100%; height: 32px; border: 1px solid transparent; border-radius: 7px; outline: none; background: #f1f5f9; padding: 0 11px; color: #334155; font-size: 12px; letter-spacing: 0; }
.address-input:hover { background: #eaf0f6; }
.address-input:focus { border-color: #93c5fd; background: white; box-shadow: 0 0 0 1px #bfdbfe; }
</style>
