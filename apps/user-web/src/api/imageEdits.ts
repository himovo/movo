import { createApiClient } from './client'
import type { DocumentInfo } from '../components/chat/types'

const api = createApiClient({ baseURL: '/askai-api/api', timeout: 900000 })

export async function editMessageImage(sessionId: string, messageId: string, payload: {
  prompt: string; object_path?: string; source_url: string; image_model_id?: string
}): Promise<DocumentInfo> {
  const { data } = await api.post(`/sessions/${encodeURIComponent(sessionId)}/messages/${encodeURIComponent(messageId)}/image-edits`, payload)
  return data
}
