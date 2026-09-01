import assert from 'node:assert/strict'
import type { EvidenceSourceItem } from '../src/features/execution-v3/domain/delivery'
import { evidenceSourceStats, groupEvidenceSources } from '../src/features/execution-v3/domain/evidenceSourceGroups'

function source(overrides: Partial<EvidenceSourceItem>): EvidenceSourceItem {
  return {
    id: String(overrides.id || overrides.chunk_id || 'source'),
    title: 'Source',
    snippet: '',
    source_type: 'kb',
    ...overrides,
  }
}

const sources = [
  source({ id: '1', document_id: 'document-a', chunk_id: 'chunk-1' }),
  source({ id: '2', document_id: 'document-a', chunk_id: 'chunk-2' }),
  source({ id: '3', document_id: 'document-a', chunk_id: 'chunk-3' }),
  source({ id: '4', document_id: 'document-a', chunk_id: 'chunk-4' }),
]

const groups = groupEvidenceSources(sources)
assert.equal(groups.length, 1)
assert.equal(groups[0].sources.length, 4)
assert.deepEqual(evidenceSourceStats(sources), {
  groups,
  total: 1,
  web: 0,
  internal: 1,
  fragments: 4,
})

const mixed = evidenceSourceStats([
  ...sources,
  source({ id: 'web-1', source_type: 'web', source_url: 'https://example.com/a' }),
  source({ id: 'web-2', source_type: 'web', source_url: 'https://example.com/b' }),
])
assert.equal(mixed.total, 3)
assert.equal(mixed.web, 2)
assert.equal(mixed.internal, 1)
assert.equal(mixed.fragments, 4)

console.log('evidence source grouping tests passed')
