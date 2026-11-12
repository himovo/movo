import { onBeforeUnmount, ref, watch } from 'vue'
import { answerUserQuestion, listUserQuestions } from '../api/userQuestions'
import { answerDshCodeQuestion, listDshCodeQuestions } from '../platform'
import type { DshPendingQuestion, DshQuestionAnswer } from '../platform/types'
import type { QuestionAnswerEntry } from '../components/chat/questionAnswerHistory'

interface Options {
  active: () => boolean
  conversationId: () => string | undefined
  codeSessionId: () => string | undefined
  token: () => string | undefined
  running: () => boolean
  assistantMessageId: () => string | undefined
}

export function useUserQuestions(options: Options) {
  const pending = ref<DshPendingQuestion[]>([])
  const busy = ref(false)
  const error = ref('')
  const submitted = ref<QuestionAnswerEntry[]>([])
  let timer: ReturnType<typeof setTimeout> | undefined
  let epoch = 0

  async function refresh() {
    const currentEpoch = epoch
    if (!options.active() || (!options.running() && !pending.value.length)) return
    const codeId = options.codeSessionId()
    const conversationId = options.conversationId()
    const token = options.token()
    if (!codeId && (!conversationId || !token)) {
      pending.value = []
      return
    }
    try {
      const rows = codeId ? await listDshCodeQuestions(codeId) : await listUserQuestions(conversationId!, token!)
      if (currentEpoch === epoch) pending.value = rows
    } catch {
      if (currentEpoch === epoch) pending.value = []
    }
  }

  async function answer(item: DshPendingQuestion, answers: DshQuestionAnswer[]) {
    if (busy.value) return
    busy.value = true
    error.value = ''
    try {
      const codeId = options.codeSessionId()
      if (codeId) await answerDshCodeQuestion(codeId, item.id, answers)
      else await answerUserQuestion(options.conversationId()!, item.id, answers, options.token()!)
      submitted.value = [...submitted.value, {
        id: item.id, message_id: options.assistantMessageId(),
        questions: item.questions, answers, created_at: new Date().toISOString(),
      }]
      pending.value = pending.value.filter(row => row.id !== item.id)
      await refresh()
    } catch (reason: any) {
      error.value = String(reason?.message || reason)
    } finally {
      busy.value = false
    }
  }

  function schedule() {
    if (timer) clearTimeout(timer)
    if (!options.active() || (!options.running() && !pending.value.length)) return
    const generation = epoch
    timer = setTimeout(async () => {
      await refresh()
      if (generation === epoch) schedule()
    }, 1500)
  }

  watch(() => [options.active(), options.conversationId(), options.codeSessionId(), options.token(), options.running()], (next, previous) => {
    if (previous && (next[1] !== previous[1] || next[2] !== previous[2])) submitted.value = []
    epoch += 1
    if (timer) clearTimeout(timer)
    pending.value = []
    error.value = ''
    void refresh()
    schedule()
  }, { immediate: true })
  onBeforeUnmount(() => { epoch += 1; if (timer) clearTimeout(timer) })

  return { pending, busy, error, submitted, answer, refresh }
}
