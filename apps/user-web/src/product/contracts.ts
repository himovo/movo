import type { Component } from 'vue'

export type ProductLocaleMessages = Record<string, { zh: string; en: string }>

export type ProductUiExtension = {
  extensionId: string
  loginModal: Component
  billingModal?: Component
  createOrganizationModal?: Component
  messages?: ProductLocaleMessages
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
