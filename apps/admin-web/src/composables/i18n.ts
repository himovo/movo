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
    return interpolate(key); // 若无对应翻译，优雅地直接返回原 Key (即中文本身)，保证页面不崩且显示原中文
  }
  const template = entry[_locale.value] || entry[DEFAULT_LOCALE] || key;
  return interpolate(template);
}
