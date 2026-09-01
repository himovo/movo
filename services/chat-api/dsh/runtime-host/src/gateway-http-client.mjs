import http from 'node:http'
import https from 'node:https'

function abortError(signal) {
  if (signal?.reason instanceof Error) return signal.reason
  const error = new Error('MOVO Tool Gateway request aborted')
  error.name = 'AbortError'
  return error
}

/**
 * POST JSON to the ASKAI gateway without Undici's implicit response-header
 * deadline. Capability total/inactivity deadlines are owned by ASKAI; this
 * transport only follows the DSH cancellation signal.
 */
export function postGatewayJson(urlValue, body, { headers = {}, signal } = {}) {
  const url = new URL(urlValue)
  const transport = url.protocol === 'https:' ? https : http
  const encoded = Buffer.from(JSON.stringify(body))

  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(abortError(signal))
      return
    }

    let settled = false
    const finish = (callback, value) => {
      if (settled) return
      settled = true
      signal?.removeEventListener('abort', onAbort)
      callback(value)
    }
    const request = transport.request(url, {
      method: 'POST',
      headers: {
        ...headers,
        'content-type': 'application/json',
        'content-length': String(encoded.byteLength),
      },
    }, response => {
      const chunks = []
      response.on('data', chunk => chunks.push(chunk))
      response.on('error', error => finish(reject, error))
      response.on('end', () => {
        const text = Buffer.concat(chunks).toString('utf8')
        let payload = {}
        try {
          payload = text ? JSON.parse(text) : {}
        } catch {
          finish(reject, new Error('MOVO Tool Gateway returned invalid JSON'))
          return
        }
        finish(resolve, {
          ok: response.statusCode >= 200 && response.statusCode < 300,
          status: response.statusCode ?? 0,
          payload,
        })
      })
    })
    const onAbort = () => request.destroy(abortError(signal))
    signal?.addEventListener('abort', onAbort, { once: true })
    request.on('error', error => finish(reject, error))
    request.end(encoded)
  })
}
