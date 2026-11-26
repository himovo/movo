/** Expand DSH V3's compact assistant stream into MOVO's stable native events. */
export function compatibleSessionEvents(event, commands = new Set()) {
  if (event?.type === 'command/run' && event.data?.name === 'compact') {
    commands.add(event.data.commandId)
    return [event, { type: 'turn/start', data: { commandId: event.data.commandId } }]
  }
  if (event?.type === 'command/done' && commands.delete(event.data?.commandId)) {
    return [
      event,
      { type: 'assistant/message', data: { message: { content: [{ type: 'text', text: event.data.text || '' }] } } },
      { type: 'turn/end', data: { reason: { kind: event.data.kind === 'error' ? 'error' : 'stop' } } },
    ]
  }
  if (!['assistant/message', 'assistant/attempt'].includes(event?.type)
      || !Array.isArray(event.data?.stream)) return [event]
  const envelope = { turn: event.data.turn, step: event.data.step }
  const expanded = []
  for (const item of event.data.stream) {
    if (item?.type === 'chunk' && item.chunk !== undefined) {
      expanded.push({ type: 'assistant/chunk', data: { ...envelope, chunk: item.chunk } })
      continue
    }
    if (item?.type !== 'text-chunks' || !Array.isArray(item.texts)) continue
    for (const text of item.texts) {
      expanded.push({
        type: 'assistant/chunk',
        data: { ...envelope, chunk: { type: 'text-delta', index: item.index, text } },
      })
    }
  }
  return [...expanded, event]
}
