import type { ComputedRef, InjectionKey } from 'vue'
import type { ChatMessage } from './chatMessage'
import type { DocumentInfo } from './types'
import { upsertDocumentEverywhere } from './documentArtifacts'

export interface ImageEditingContext {
  sessionId: string
  messageId: string
  onEdited: (document: DocumentInfo) => void
}

export const imageEditingKey: InjectionKey<ComputedRef<ImageEditingContext | undefined>> = Symbol('image-editing')

export function imageEditingContext(sessionId: string | undefined, message?: ChatMessage): ImageEditingContext | undefined {
  const conversationId = sessionId || message?._backendSid
  if (!conversationId || !message?.message_id) return undefined
  return {
    sessionId: conversationId, messageId: message.message_id,
    onEdited: document => upsertDocumentEverywhere(message, null, document),
  }
}
