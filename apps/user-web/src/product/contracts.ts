import type { Component, Ref } from 'vue'

export type ProductLocaleMessages = Record<string, { zh: string; en: string }>

export type UserEntry = 'knowledge' | 'plugins' | 'skills' | 'tools' | 'scheduled'
export type EntryVisibility = { ready: boolean; entries: Partial<Record<UserEntry, boolean>> }
export type AgentPresentation = { name: string; greetings: Array<{ zh: string; en: string }> }

export type ProductUiExtension = {
  entryVisibility?: Ref<EntryVisibility>
  refreshEntryVisibility?: () => void
  extensionId: string
  loginModal: Component
  billingModal?: Component
  createOrganizationModal?: Component
  knowledgeSourceActions?: Component
  messages?: ProductLocaleMessages
  loadAgentPresentation?: (token: string, tenantId: string) => Promise<AgentPresentation>
}

export type ProductCapabilities = {
  edition: string
  extensionId: string
  features: {
    passwordLogin: boolean
    smsLogin: boolean
    emailVerification: boolean
    selfRegistration: boolean
    organizationSelfService: boolean
    billing: boolean
    onlinePayment: boolean
    [key: string]: boolean
  }
}
