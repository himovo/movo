import { computed, ref } from 'vue'
import { messages, type Locale, type MessageKey } from '../locales/messages'
import type { ProductLocaleMessages } from '../product/contracts'

export type { Locale } from '../locales/messages'

export type LabelMap = Record<Locale, string>
export type LabelKey = MessageKey

function normalizeLocale(value: string | null | undefined): Locale {
  return value === 'en' ? 'en' : 'zh'
}

export function detectSystemLocale(): Locale {
  if (typeof navigator === 'undefined') return 'zh'
  const language = navigator.languages?.[0] || navigator.language || ''
  return String(language).toLowerCase().startsWith('zh') ? 'zh' : 'en'
}

const _locale = ref<Locale>(detectSystemLocale())
const productMessages: ProductLocaleMessages = {}

export function registerProductMessages(catalog?: ProductLocaleMessages) {
  Object.keys(productMessages).forEach(key => delete productMessages[key])
  if (catalog) Object.assign(productMessages, catalog)
}

export function useLocale() {
  return {
    locale: computed(() => _locale.value),
    setLocale(locale: Locale) {
      _locale.value = locale
    },
  }
}

export function setLocale(locale: Locale | string) {
  _locale.value = normalizeLocale(locale)
}

export function getLocale(): Locale {
  return _locale.value
}

export function t(key: string, params?: Record<string, string | number>): string {
  const entry = productMessages[key] || messages[key as MessageKey] as LabelMap | undefined
  const template = entry?.[_locale.value] || entry?.zh || key
  if (!params) return template
  return template.replace(/\{(\w+)\}/g, (_, name) => String(params[name] ?? `{${name}}`))
}
