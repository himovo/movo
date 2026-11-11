import { computed, ref, watch, type Ref } from 'vue'
import productUiExtension from '@movo-product-extension'
import { t, type Locale } from '../../composables/i18n'
import type { AgentPresentation } from '../../product/contracts'

export function useAgentPresentation(options: {
  token: () => string | undefined
  tenantId: () => string | undefined
  sessionId: () => string | undefined
  locale: Ref<Locale>
}) {
  const presentation = ref<AgentPresentation | null>(null)
  const selectedIndex = ref(0)
  let requestId = 0

  function chooseGreeting() {
    const count = presentation.value?.greetings.length || 0
    selectedIndex.value = count ? Math.floor(Math.random() * count) : 0
  }

  watch([options.token, options.tenantId, options.sessionId], async ([token, tenantId]) => {
    const current = ++requestId
    presentation.value = null
    if (!token || !tenantId || !productUiExtension.loadAgentPresentation) return
    try {
      const result = await productUiExtension.loadAgentPresentation(token, tenantId)
      if (current !== requestId) return
      presentation.value = result
      chooseGreeting()
    } catch {
      if (current === requestId) presentation.value = null
    }
  }, { immediate: true })

  const welcomeTitle = computed(() => {
    const greeting = presentation.value?.greetings[selectedIndex.value]
    return (options.locale.value === 'en' ? greeting?.en || greeting?.zh : greeting?.zh || greeting?.en)
      || t('chat.welcome_title')
  })
  return { welcomeTitle }
}
