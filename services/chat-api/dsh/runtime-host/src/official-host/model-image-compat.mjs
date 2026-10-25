/** Convert DSH durable image references to provider-ready blocks at dispatch. */
export async function materializeModelImages(messages, attachments, allowImages = false) {
  const output = []
  for (const message of messages) {
    if (!Array.isArray(message?.content) || !message.content.some(block => block?.type === 'image')) {
      output.push(message)
      continue
    }
    if (!allowImages) throw new Error('selected model is not configured for visual input')
    if (!attachments) throw new Error('DSH image storage is unavailable')
    const content = []
    for (const block of message.content) {
      if (block?.type !== 'image') {
        content.push(block)
        continue
      }
      const stored = await attachments.readImage(block.attachment)
      const mediaType = stored.ref.mediaType
      content.push({
        type: 'image_url',
        image_url: { url: `data:${mediaType};base64,${Buffer.from(stored.data).toString('base64')}` },
      })
    }
    output.push({ ...message, content })
  }
  return output
}
