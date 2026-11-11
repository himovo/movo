import { authenticatedJsonHeaders } from './authHeaders'

export type ChatFilePreviewState = {
  kind: 'pdf' | 'office' | 'text' | 'html' | 'unsupported'
  status: 'ready' | 'queued' | 'failed' | 'unsupported'
  filename: string
  url?: string
  error?: string
}

export async function prepareChatFilePreview(sessionId: string, objectPath: string, retry = false): Promise<ChatFilePreviewState> {
  const response = await fetch('/askai-api/api/chat/file-previews', {
    method: 'POST',
    headers: authenticatedJsonHeaders(),
    body: JSON.stringify({ session_id: sessionId, object_path: objectPath, retry }),
  })
  if (!response.ok) throw new Error(`Preview request failed (${response.status})`)
  return await response.json() as ChatFilePreviewState
}

export async function prepareDraftFilePreview(objectPath: string, retry = false): Promise<ChatFilePreviewState> {
  const response = await fetch('/askai-api/api/chat/file-previews/drafts', {
    method: 'POST', headers: authenticatedJsonHeaders(),
    body: JSON.stringify({ object_path: objectPath, retry }),
  })
  if (!response.ok) throw new Error(`Preview request failed (${response.status})`)
  return await response.json() as ChatFilePreviewState
}

export async function fetchChatFilePreviewText(url: string): Promise<string> {
  const response = await fetch(url, { headers: authenticatedJsonHeaders() })
  if (!response.ok) throw new Error(`Preview request failed (${response.status})`)
  return response.text()
}
