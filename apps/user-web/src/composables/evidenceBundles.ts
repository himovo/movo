import type { EvidenceBundleItem, EvidenceSourceItem } from '../features/execution-v3/domain/delivery'

function hasSourceContent(source: EvidenceSourceItem): boolean {
  return Boolean(
    String(source.title || '').trim() ||
    String(source.snippet || '').trim() ||
    String(source.content || '').trim() ||
    String(source.source_url || '').trim() ||
    (source.document_id && source.chunk_id),
  )
}

function isEmptyKbSource(source: EvidenceSourceItem): boolean {
  const type = String(source.source_type || '').toLowerCase()
  if (type !== 'kb' && type !== 'internal') return false
  const title = String(source.title || source.source_name || '').trim().toLowerCase()
  const hasEvidenceLocator = Boolean(source.source_url || (source.document_id && source.chunk_id))
  const hasEvidenceText = Boolean(String(source.snippet || '').trim() || String(source.content || '').trim())
  const content = String(source.content || '').trim()
  if (content.startsWith('{') || content.startsWith('[')) {
    try {
      const parsed = JSON.parse(content)
      const evidenceBundle = parsed && typeof parsed === 'object' ? parsed.evidenceBundle : null
      const sources = evidenceBundle && typeof evidenceBundle === 'object' ? evidenceBundle.sources : []
      const usedCount = Number(parsed?.usedCount || parsed?.used_count || 0)
      const retrievedCount = Number(parsed?.retrievedCount || parsed?.retrieved_count || 0)
      const provider = String(parsed?.provider || '').toLowerCase()
      if (provider.includes('knowledge') && usedCount === 0 && retrievedCount === 0 && Array.isArray(sources) && !sources.length) {
        return true
      }
    } catch {
      // Fall back to the plain empty-source check below.
    }
  }
  return !hasEvidenceLocator && !hasEvidenceText && ['kb_search', 'knowledge_search'].includes(title)
}

function sourceSignature(source: EvidenceSourceItem): string {
  const url = String(source.source_url || '').trim()
  if (url) return `url:${url}`
  if (source.document_id && source.chunk_id) return `doc:${source.document_id}:${source.chunk_id}`
  return [
    'text',
    String(source.source_type || '').trim(),
    String(source.title || '').trim(),
    String(source.snippet || '').trim().slice(0, 120),
  ].join(':')
}

export function mergeEvidenceBundles(bundles: EvidenceBundleItem[]): EvidenceBundleItem | null {
  if (!bundles.length) return null

  const sources: EvidenceSourceItem[] = []
  const seenSources = new Set<string>()
  const confirmedFacts: string[] = []
  const seenFacts = new Set<string>()
  const openQuestions: string[] = []
  const seenQuestions = new Set<string>()

  for (const bundle of bundles) {
    for (const source of bundle.sources || []) {
      if (!hasSourceContent(source) || isEmptyKbSource(source)) continue
      const key = sourceSignature(source)
      if (seenSources.has(key)) continue
      seenSources.add(key)
      sources.push(source)
    }
    for (const fact of bundle.confirmed_facts || []) {
      const text = String(fact || '').trim()
      if (!text || seenFacts.has(text)) continue
      seenFacts.add(text)
      confirmedFacts.push(text)
    }
    for (const question of bundle.open_questions || []) {
      const text = String(question || '').trim()
      if (!text || seenQuestions.has(text)) continue
      seenQuestions.add(text)
      openQuestions.push(text)
    }
  }

  if (!sources.length && !confirmedFacts.length && !openQuestions.length) return null
  return {
    id: `merged_${bundles.map((bundle) => bundle.id).join('_')}`,
    ts: bundles[bundles.length - 1]?.ts || Date.now(),
    summary: '',
    sources,
    confirmed_facts: confirmedFacts,
    open_questions: openQuestions,
  }
}
