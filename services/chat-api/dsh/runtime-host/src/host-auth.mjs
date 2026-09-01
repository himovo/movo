import { timingSafeEqual } from 'node:crypto'

export function assertLoopbackHost(host) {
  if (!['127.0.0.1', '::1', 'localhost'].includes(host)) {
    throw new Error(`DSH Runtime Host must listen on loopback, received ${JSON.stringify(host)}`)
  }
}

export function assertSecureHost(host, authToken) {
  if (['127.0.0.1', '::1', 'localhost'].includes(host)) return
  if (typeof authToken !== 'string' || authToken.length < 32) {
    throw new Error(`DSH Runtime Host network binding requires an authentication token, received ${JSON.stringify(host)}`)
  }
}

export function validBearerToken(header, expectedToken) {
  if (!expectedToken) return true
  if (typeof header !== 'string' || !header.startsWith('Bearer ')) return false
  const actual = Buffer.from(header.slice('Bearer '.length), 'utf8')
  const expected = Buffer.from(expectedToken, 'utf8')
  return actual.length === expected.length && timingSafeEqual(actual, expected)
}
