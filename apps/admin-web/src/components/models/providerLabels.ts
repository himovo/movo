import { t } from '@/composables/i18n'

type ProviderLike = {
  code?: string
  name?: string
  providerType?: string
}

const providerMessageKeys: Record<string, string> = {
  openai: 'provider.openai',
  azure_openai: 'provider.azureOpenAI',
  qwen: 'legacy.qwen',
  tongyi: 'legacy.qwen',
  dashscope: 'legacy.qwen',
  aliyun: 'legacy.qwen',
  deepseek: 'provider.deepseek',
  custom: 'legacy.custom_compatible_api',
  custom_compatible: 'legacy.custom_compatible_api',
  custom_openai: 'legacy.custom_compatible_api',
}

export function providerLabel(provider?: Partial<ProviderLike> | null): string {
  if (!provider) return t('legacy.not_selected')
  const code = String(provider.code || '').toLowerCase()
  const name = String(provider.name || '').toLowerCase()
  const key = providerMessageKeys[code]
  if (key) return t(key)
  if (name.includes('qwen') || name.includes('通义') || name.includes('dashscope')) return t('legacy.qwen')
  if (name.includes('deepseek')) return t('provider.deepseek')
  if (name.includes('azure')) return t('provider.azureOpenAI')
  if (name.includes('custom') || name.includes('自定义')) return t('legacy.custom_compatible_api')
  if (provider.providerType === 'azure_openai') return t('provider.azureOpenAI')
  return provider.name || t('legacy.custom')
}
