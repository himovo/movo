import type { KnowledgeReference } from '../api/knowledgeReferences'
import type { UserProfile } from '../api/auth'
import type { PendingRuntimeDocument } from './useChatRuntimeStore'
import type { useChatRuntimeStore } from './useChatRuntimeStore'
import type { useDshCodeRuntime } from './code/useDshCodeRuntime'
import { t } from './i18n'

type ChatRuntime = ReturnType<typeof useChatRuntimeStore>
type CodeRuntime = ReturnType<typeof useDshCodeRuntime>

export type PaneSendPayload = {
  text: string
  images: File[]
  documents: PendingRuntimeDocument[]
  knowledgeQaEnabled: boolean
  knowledgeReferences?: KnowledgeReference[]
  selectedSkillId?: string
  modelId?: string
  onRejected?: () => void
}

export function usePaneTurnActions(options: {
  chatRuntime: ChatRuntime
  codeRuntime: CodeRuntime
  canUseCode: () => boolean
  authToken: () => string
  userId: () => string | null
  mainId: () => string
  profile: () => UserProfile | null
  locale: () => 'en' | 'zh'
  timezone: () => string
}) {
  async function send(key: string, payload: PaneSendPayload): Promise<void> {
    const codeState = options.codeRuntime.stateFor(key)
    if (options.canUseCode() && (codeState.workspace || codeState.session)) {
      if (payload.knowledgeReferences?.length) {
        codeState.error = t('knowledgeMention.codeUnsupported')
        payload.onRejected?.()
        return
      }
      if (payload.images.length || payload.documents.length) {
        codeState.error = t('app.codeAttachmentHint')
        return
      }
      const existingPane = options.chatRuntime.panes.value.find(pane => pane.key === key)
      let targetKey = key
      if (existingPane?.sessionId && !codeState.session) {
        const derived = options.chatRuntime.startLocalSession()
        options.codeRuntime.transferDraft(key, derived.key)
        targetKey = derived.key
      }
      try {
        await options.codeRuntime.send(targetKey, payload.text, payload.modelId, payload.selectedSkillId)
      } catch {
        // The runtime owns the visible error; preserve the composer draft.
        payload.onRejected?.()
      }
      return
    }

    const profile = options.profile()
    options.chatRuntime.sendMessage(key, {
      ...payload,
      authToken: options.authToken() || null,
      userId: options.userId(),
      mainId: options.mainId(),
      viewerAuthor: profile
        ? {
            user_id: String(profile.userId ?? options.userId() ?? ''),
            display_name: profile.name || profile.username || null,
            avatar_url: profile.avatar || null,
          }
        : null,
      locale: options.locale(),
      timezone: options.timezone(),
    })
  }

  function stop(key: string): void {
    const codeState = options.codeRuntime.stateFor(key)
    if (codeState.session) void options.codeRuntime.stop(key).catch(() => undefined)
    else options.chatRuntime.stopGeneration(key)
  }

  return { send, stop }
}
