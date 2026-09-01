import assert from 'node:assert/strict'
import test from 'node:test'

import { AskaiWebSearchProvider, normalizeSearchResult } from '../src/askai-web-search-provider.mjs'

test('native web provider maps and deduplicates ASKAI provider results', () => {
  assert.deepEqual(normalizeSearchResult({ results: [
    { title: 'A', url: 'https://a.test', snippet: 'one' },
    { title: 'A duplicate', url: 'https://a.test', snippet: 'two' },
    { title: 'B', url: 'https://b.test', content: 'three' },
  ] }, 2), {
    sources: [
      { title: 'A', url: 'https://a.test', snippet: 'one' },
      { title: 'B', url: 'https://b.test', snippet: 'three' },
    ],
    truncated: true,
  })
})

test('native web provider executes the hidden enterprise search primitive', async () => {
  const ctx = { get: name => name === 'agents' ? { currentInitiator: () => ({ id: 'session-a' }) } : undefined }
  const originalFetch = globalThis.fetch
  let request
  globalThis.fetch = async (url, init) => {
    request = { url, body: JSON.parse(init.body), authorization: init.headers.authorization }
    return new Response(JSON.stringify({ result: {
      results: [{ title: 'Result', url: 'https://result.test', snippet: 'fact' }],
    } }), { status: 200, headers: { 'content-type': 'application/json' } })
  }
  try {
    const provider = new AskaiWebSearchProvider(ctx, {
      gatewayUrl: 'http://gateway.test', accessToken: 'secret', profileVersion: 'profile-a',
    })
    const result = await provider.search({ query: 'current fact', maxResults: 5 })
    assert.equal(request.url, 'http://gateway.test/execute')
    assert.equal(request.body.toolName, 'external_search')
    assert.deepEqual(request.body.arguments, { queries: ['current fact'], max_results_per_query: 5 })
    assert.equal(request.authorization, 'Bearer secret')
    assert.equal(result.sources[0].url, 'https://result.test')
  } finally {
    globalThis.fetch = originalFetch
  }
})
