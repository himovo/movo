const CONTEXT_NAME = 'askai:trusted-turn-scope'

function attachments(value) {
  if (!Array.isArray(value)) return []
  return value.slice(0, 20).map(item => {
    if (item === null || typeof item !== 'object' || Array.isArray(item)) return undefined
    const clean = {}
    for (const key of ['object_path', 'filename', 'content_type', 'size']) {
      if (item[key] !== undefined && item[key] !== null && item[key] !== '') clean[key] = item[key]
    }
    return typeof clean.object_path === 'string' && clean.object_path ? Object.freeze(clean) : undefined
  }).filter(Boolean)
}

export function normalizeTurnContext(value) {
  if (value === undefined || value === null) value = {}
  if (typeof value !== 'object' || Array.isArray(value)) throw new TypeError('turnContext must be an object')
  const allowed = new Set(['knowledge_qa_enabled', 'knowledge_base_ids', 'images', 'documents', 'browser_resume', 'writing_style'])
  const unknown = Object.keys(value).filter(key => !allowed.has(key))
  if (unknown.length > 0) throw new TypeError(`turnContext has unknown fields: ${unknown.join(', ')}`)
  const browserResume = value.browser_resume && typeof value.browser_resume === 'object' && !Array.isArray(value.browser_resume)
    ? value.browser_resume : undefined
  const mission = browserResume?.mission && typeof browserResume.mission === 'object' && !Array.isArray(browserResume.mission)
    ? browserResume.mission : {}
  return Object.freeze({
    strictKnowledgeMode: value.knowledge_qa_enabled === true,
    knowledgeBaseCount: Array.isArray(value.knowledge_base_ids) ? value.knowledge_base_ids.length : 0,
    images: Object.freeze(attachments(value.images)),
    documents: Object.freeze(attachments(value.documents)),
    browserResume: browserResume ? Object.freeze({
      objective: String(mission.objective || ''),
      operation: String(mission.operation || 'read'),
      target_name: String(mission.target_name || ''),
      target_url: String(mission.target_url || ''),
    }) : undefined,
    writingStyle: value.writing_style && typeof value.writing_style === 'object'
      ? Object.freeze({
          name: String(value.writing_style.name || ''),
          instructions: String(value.writing_style.instructions || ''),
        })
      : undefined,
  })
}

export function renderTurnContext(value) {
  if (value === undefined) return ''
  const sections = [
    'MOVO interaction language policy: use the language of the user\'s latest message for all user-facing text, including progress notes before tools, retry explanations, questions, and the final answer. If the user explicitly requests another output language, follow that request. Tool commands and source-code identifiers may remain in their technically required language.',
  ]
  if (value.strictKnowledgeMode) {
    const scope = value.knowledgeBaseCount > 0
      ? `${value.knowledgeBaseCount} explicitly selected server-authorized knowledge base(s)`
      : 'the server-authorized tenant knowledge scope'
    sections.push(`MOVO Knowledge QA mode is enabled for ${scope}. You must call knowledge_search before answering, ground the answer only in returned chunks, and state clearly when evidence is insufficient. citation_ref, documentId, chunkId, kb:// addresses, and chunk_* identifiers are private MOVO locators: never include them in the answer or create a raw technical reference list. MOVO renders source evidence separately.`)
  } else {
    sections.push('MOVO retrieval mode is automatic. Choose knowledge_search for enterprise-internal facts, policies, documents, or follow-ups grounded in prior internal knowledge; choose web_search for one bounded public or current lookup; choose progressive_research for multi-source research, comparisons, coverage analysis, or evidence-sufficiency checks; combine internal and public evidence only when the user needs a comparison; and answer directly when retrieval is unnecessary. Internal citation locators are private MOVO metadata and must never appear in the answer. MOVO renders source evidence separately.')
  }
  if (value.documents.length > 0) {
    sections.push(`MOVO document references for this turn:\n${JSON.stringify(value.documents)}\nUse document_parse or document_extract_resources when their contents are needed. Do not invent file contents.`)
  }
  if (value.images.length > 0) {
    sections.push(`MOVO image references for this turn:\n${JSON.stringify(value.images)}\nUse image_extract_facts when image facts are needed. Do not invent unseen image details.`)
  }
  if (value.browserResume) {
    sections.push(`A server-authorized browser checkpoint is ready to resume. Call browser_task exactly once with these mission arguments: ${JSON.stringify(value.browserResume)}. Do not start a different browser mission.`)
  }
  if (value.writingStyle?.instructions) {
    sections.push(`MOVO writing standard selected for this turn: ${value.writingStyle.name}. Apply the following standard only when authoring or rewriting prose or a user-facing content deliverable. It must not change retrieval choices, search queries, tool arguments, calculations, extracted facts, browser actions, approvals, or ordinary factual answers. If the task is not writing, ignore this standard completely.\n\n${value.writingStyle.instructions}`)
  }
  return sections.length === 0 ? '' : `Trusted MOVO turn scope:\n${sections.join('\n\n')}`
}

export class RuntimeTurnContext {
  #bySession = new Map()
  #dispose

  install(ctx) {
    this.#dispose = ctx.systemPrompt.context({
      name: CONTEXT_NAME,
      order: 30,
      text: context => renderTurnContext(this.#bySession.get(context.agent?.id)),
    })
  }

  update(sessionId, value) { this.#bySession.set(sessionId, normalizeTurnContext(value)) }
  remove(sessionId) { this.#bySession.delete(sessionId) }
  dispose() { this.#bySession.clear(); this.#dispose?.(); this.#dispose = undefined }
}
