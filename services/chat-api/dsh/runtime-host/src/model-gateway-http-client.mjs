import http from 'node:http'
import https from 'node:https'

function abortError(signal) {
  if (signal?.reason instanceof Error) return signal.reason
  const error = new Error('MOVO Model Gateway request aborted')
  error.name = 'AbortError'
  return error
}

/** Open a streaming model response without a transport-level response deadline. */
export function postGatewayNdjson(urlValue, body, { headers = {}, signal } = {}) {
  const url = new URL(urlValue)
  if (url.protocol !== 'http:' && url.protocol !== 'https:') {
    throw new TypeError('MOVO Model Gateway URL must use HTTP or HTTPS')
  }
  const transport = url.protocol === 'https:' ? https : http
  const encoded = Buffer.from(JSON.stringify(body))

  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(abortError(signal))
      return
    }

    let response = null
    let settled = false
    const cleanup = () => signal?.removeEventListener('abort', onAbort)
    const request = transport.request(url, {
      method: 'POST',
      headers: {
        ...headers,
        'content-type': 'application/json',
        'content-length': String(encoded.byteLength),
      },
    }, incoming => {
      response = incoming
      incoming.once('close', cleanup)
      settled = true
      resolve({
        ok: incoming.statusCode >= 200 && incoming.statusCode < 300,
        status: incoming.statusCode ?? 0,
        body: incoming,
        json: async () => {
          const chunks = []
          for await (const chunk of incoming) chunks.push(chunk)
          return JSON.parse(Buffer.concat(chunks).toString('utf8'))
        },
      })
    })
    const onAbort = () => {
      const error = abortError(signal)
      if (response) response.destroy(error)
      request.destroy(error)
    }
    signal?.addEventListener('abort', onAbort, { once: true })
    request.once('error', error => {
      if (settled) return
      settled = true
      cleanup()
      reject(error)
    })
    request.end(encoded)
  })
}
