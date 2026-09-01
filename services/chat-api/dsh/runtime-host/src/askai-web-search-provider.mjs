import { randomUUID } from 'node:crypto'

async function readJson(response) {
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = payload?.detail
    const message = typeof detail === 'string' ? detail : detail?.message
    throw new Error(message || `MOVO Web Search Gateway returned ${response.status}`)
  }
  return payload
}

export function normalizeSearchResult(value, maxResults) {
  const rows = Array.isArray(value?.results) ? value.results : []
  const limit = Math.max(1, Number(maxResults) || 8)
  const seen = new Set()
  const sources = []
  for (const row of rows) {
    const url = String(row?.url ?? row?.source_url ?? row?.source ?? '').trim()
    if (!url || seen.has(url)) continue
    seen.add(url)
    sources.push({
      url,
      ...(String(row?.title ?? '').trim() ? { title: String(row.title).trim() } : {}),
      ...(String(row?.snippet ?? row?.content ?? row?.summary ?? '').trim()
        ? { snippet: String(row?.snippet ?? row?.content ?? row?.summary).trim() }
        : {}),
      ...(String(row?.published_at ?? row?.publishedAt ?? '').trim()
        ? { publishedAt: String(row?.published_at ?? row?.publishedAt).trim() }
        : {}),
    })
    if (sources.length >= limit) break
  }
  return { sources, truncated: rows.length > sources.length }
}

export class AskaiWebSearchProvider {
  id = 'askai-enterprise'
  #ctx
  #config

  constructor(ctx, config) {
    this.#ctx = ctx
    this.#config = Object.freeze(structuredClone(config))
  }

  available() {
    return Boolean(this.#config.gatewayUrl && this.#config.accessToken)
  }

  updateCredential(accessToken) {
    if (typeof accessToken !== 'string' || !accessToken) {
      throw new Error('Web Search Gateway credential is empty')
    }
    this.#config = Object.freeze({ ...this.#config, accessToken })
  }

  async search(request, signal) {
    const agent = this.#ctx.get('agents')?.currentInitiator()
    const sessionId = String(agent?.id ?? '')
    if (!sessionId) throw new Error('MOVO web search requires an initiating DSH session')
    const actionId = `native-web-search:${randomUUID()}`
    const payload = await this.#post('/execute', {
      profileVersion: this.#config.profileVersion,
      sessionId,
      toolName: 'external_search',
      actionId,
      idempotencyKey: `${sessionId}:${actionId}`,
      arguments: {
        queries: [String(request?.query ?? '').trim()],
        max_results_per_query: Math.max(1, Number(request?.maxResults) || 8),
      },
    }, signal)
    return normalizeSearchResult(payload.result, request?.maxResults)
  }

  async #post(path, body, signal) {
    const response = await fetch(`${this.#config.gatewayUrl}${path}`, {
      method: 'POST',
      headers: {
        authorization: `Bearer ${this.#config.accessToken}`,
        'content-type': 'application/json',
      },
      body: JSON.stringify(body),
      signal,
    })
    return readJson(response)
  }
}
