import { computed, ref } from 'vue';
import { messages, type Locale, type MessageKey, type LabelMap } from '../locales/messages';

const DEFAULT_LOCALE: Locale = 'zh-CN';
const SUPPORTED_LOCALES: readonly Locale[] = ['zh-CN', 'en-US'];
const STORAGE_KEY = 'askai-admin-locale';

export function isLocale(value: unknown): value is Locale {
  return SUPPORTED_LOCALES.includes(value as Locale);
}

function detectSystemLocale(): Locale {
  if (typeof navigator === 'undefined') return DEFAULT_LOCALE;
  const language = navigator.languages?.[0] || navigator.language || '';
  return String(language).toLowerCase().startsWith('zh') ? 'zh-CN' : 'en-US';
}

const storedLocale = localStorage.getItem(STORAGE_KEY);
const _locale = ref<Locale>(isLocale(storedLocale) ? storedLocale : detectSystemLocale());

export function useLocale() {
  return {
    locale: computed(() => _locale.value),
    setLocale(locale: Locale) {
      if (!isLocale(locale)) return;
      _locale.value = locale;
      localStorage.setItem(STORAGE_KEY, locale);
    },
  };
}

export function t(key: string, params?: Record<string, string | number>): string {
  if (!key) return '';
  const entry = messages[key as MessageKey] as LabelMap | undefined;
  const interpolate = (template: string) => {
    if (!params) return template;
    return template.replace(/\{(\w+)\}/g, (_, name) => String(params[name] ?? `{${name}}`));
  };
  if (!entry) {
    return interpolate(key); // Preserve unknown server-provided text without breaking the page.
  }
  const template = entry[_locale.value] || entry[DEFAULT_LOCALE] || key;
  return interpolate(template);
}

// Server responses can still contain human-readable labels from older releases.
// Resolve those labels by their translated value; catalog identifiers stay language-neutral.
const sourceTextKeys = new Map<string, MessageKey>();
for (const [key, value] of Object.entries(messages)) {
  const label = (value as LabelMap)['zh-CN'];
  if (label && !sourceTextKeys.has(label)) sourceTextKeys.set(label, key as MessageKey);
}

export function translateSourceText(value: string): string {
  if (!value) return '';
  const key = sourceTextKeys.get(value);
  return t(key || value);
}
