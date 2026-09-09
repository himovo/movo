type BrowserCrypto = {
  randomUUID?: () => string
  getRandomValues?: (values: Uint8Array) => Uint8Array
}

function formatUuid(bytes: Uint8Array): string {
  bytes[6] = (bytes[6] & 0x0f) | 0x40
  bytes[8] = (bytes[8] & 0x3f) | 0x80
  const hex = [...bytes].map(value => value.toString(16).padStart(2, '0')).join('')
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}

/**
 * Generates an RFC 4122 version 4 UUID in browsers served from both secure and
 * non-secure origins. `crypto.randomUUID` is unavailable on plain HTTP origins
 * other than localhost, while `crypto.getRandomValues` remains broadly usable.
 */
export function createClientUuid(
  cryptoSource: BrowserCrypto | null | undefined = typeof globalThis.crypto === 'object'
    ? globalThis.crypto
    : undefined,
): string {
  if (typeof cryptoSource?.randomUUID === 'function') {
    return cryptoSource.randomUUID()
  }

  const bytes = new Uint8Array(16)
  if (typeof cryptoSource?.getRandomValues === 'function') {
    cryptoSource.getRandomValues(bytes)
  } else {
    for (let index = 0; index < bytes.length; index += 1) {
      bytes[index] = Math.floor(Math.random() * 256)
    }
  }
  return formatUuid(bytes)
}
