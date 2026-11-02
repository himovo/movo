export function knowledgeMentionAt(text: string, caret: number) {
  const prefix = text.slice(0, caret)
  const match = /(?:^|[\s(（,，。:：])@([^@\n「」]{0,120})$/.exec(prefix)
  if (!match) return null
  return { start: caret - match[1].length - 1, end: caret, query: match[1] }
}
