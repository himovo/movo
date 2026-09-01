import type { ExecutionEventV3 } from './protocol'

export type AssistantContentTarget = {
  content: string
}

/**
 * Commit only classified final-answer text to the answer body.
 *
 * Native provisional deltas remain in ExecutionStoreV3, where they are
 * rendered in their stable event-order position. Once DSH classifies the
 * message, the same item either becomes Timeline commentary in place or is
 * committed here as the final answer. This avoids re-parenting visible text
 * between the answer body and Timeline during a tool loop.
 */
export function applyAssistantContentEvent(
  message: AssistantContentTarget,
  event: ExecutionEventV3,
): void {
  if (event.item_kind === 'final_answer' && event.type === 'item.delta') {
    // The Execution Store already accumulated and exposed this native delta.
    // Its semantic destination is unknown until message completion.
    return
  }
  if (event.item_kind === 'final_answer' && event.type === 'item.completed') {
    message.content = String(event.payload?.text ?? message.content)
  }
}
