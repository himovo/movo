import type { Locale } from './messages'

export const collapsibleUserTextLabels: Record<Locale, { more: string; less: string }> = {
  en: { more: 'Show more', less: 'Show less' },
  zh: { more: '显示更多', less: '收起' },
}
