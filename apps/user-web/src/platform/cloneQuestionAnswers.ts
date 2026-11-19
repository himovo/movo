import type { DshQuestionAnswer } from './types'

/** Strip Vue proxies before sending answers through Electron IPC. */
export function cloneQuestionAnswers(answers: DshQuestionAnswer[]): DshQuestionAnswer[] {
  return answers.map(answer => ({
    id: answer.id,
    selected: Array.from(answer.selected),
    ...(answer.custom === undefined ? {} : { custom: answer.custom }),
  }))
}
