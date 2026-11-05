import { createHash } from 'node:crypto'

export function personalSpaceKey(tenantId, userId) {
  if (!tenantId || !userId) return undefined
  return createHash('sha256').update(`${tenantId}\0${userId}`).digest('hex')
}

export function validConversationSpaceKey(value) {
  return typeof value === 'string' && /^[0-9a-f]{64}$/.test(value)
}
