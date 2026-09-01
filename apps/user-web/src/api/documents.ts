import { createApiClient } from './client'

export type RenderDocumentRequest = {
  user_id: string
  content: string
  format: 'pdf' | 'docx' | 'ppt' | 'pptx' | 'md' | 'markdown'
  filename?: string
  title?: string
}

export type RenderDocumentResponse = {
  type: 'pdf' | 'docx' | 'ppt' | 'pptx' | 'md' | 'markdown'
  url: string
  filename?: string
  title?: string
  object_path?: string
}

const client = createApiClient({
  timeout: 180000,
})

export async function renderDocument(payload: RenderDocumentRequest): Promise<RenderDocumentResponse> {
  const response = await client.post('/askai-api/api/documents/render', payload)
  return response.data?.data
}

export type RenderPresentationPptxRequest = {
  user_id: string
  blueprint_object_path: string
  filename?: string
  title?: string
}

export async function renderPresentationPptx(payload: RenderPresentationPptxRequest): Promise<RenderDocumentResponse> {
  const response = await client.post('/askai-api/api/documents/render-presentation-pptx', payload)
  return response.data?.data
}

export async function fetchBlueprintJson(userId: string, objectPath: string): Promise<any> {
  const response = await client.post('/askai-api/api/documents/fetch', {
    user_id: userId,
    object_path: objectPath,
  })
  return typeof response.data === 'string' ? JSON.parse(response.data) : response.data
}

export async function saveBlueprint(payload: {
  user_id: string
  blueprint_object_path: string
  blueprint: any
}): Promise<{ object_path: string; url: string }> {
  const response = await client.post('/askai-api/api/documents/save-blueprint', payload)
  return response.data?.data
}

export async function signDocument(payload: { user_id: string; object_path: string; expires?: number }): Promise<{ url: string }> {
  const response = await client.post('/askai-api/api/documents/sign', payload)
  return response.data?.data
}
