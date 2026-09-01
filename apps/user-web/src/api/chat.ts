import axios from 'axios'
import { installAuthExpiryInterceptor } from './authExpiry'

export type UploadedImage = {
  object_path?: string
  url?: string
  signed_url?: string
  filename?: string
  content_type?: string
  size?: number
}

export type UploadedDocument = {
  object_path?: string
  url?: string
  signed_url?: string
  filename?: string
  content_type?: string
  size?: number
}

const client = axios.create({
  baseURL: '/askai-api/api',
  timeout: 120000,
})
installAuthExpiryInterceptor(client)

export async function uploadChatImage(userId: string, file: File, authToken?: string | null): Promise<UploadedImage> {
  const form = new FormData()
  form.append('user_id', userId)
  form.append('file', file)
  const res = await client.post('/chat/upload-image', form, {
    headers: {
      'Content-Type': 'multipart/form-data',
      ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
    },
  })
  return res.data?.data || {}
}

export async function uploadChatDocument(userId: string, file: File, authToken?: string | null): Promise<UploadedDocument> {
  const form = new FormData()
  form.append('user_id', userId)
  form.append('file', file)
  const res = await client.post('/chat/upload-document', form, {
    headers: {
      'Content-Type': 'multipart/form-data',
      ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
    },
  })
  return res.data?.data || {}
}
