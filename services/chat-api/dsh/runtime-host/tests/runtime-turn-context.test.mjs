import test from 'node:test'
import assert from 'node:assert/strict'

import { normalizeTurnContext, renderTurnContext } from '../src/runtime-turn-context.mjs'

test('missing turn context normalizes to a complete automatic-retrieval scope', () => {
  const context = normalizeTurnContext(undefined)
  assert.deepEqual(context.images, [])
  assert.deepEqual(context.documents, [])
  assert.equal(context.knowledgeBaseCount, 0)
  assert.equal(context.strictKnowledgeMode, false)
  assert.match(renderTurnContext(context), /retrieval mode is automatic/)
  assert.match(renderTurnContext(context), /language of the user's latest message/)
  assert.match(renderTurnContext(context), /including progress notes before tools/)
  assert.match(renderTurnContext(context), /MOVO file delivery policy/)
  assert.match(renderTurnContext(context), /call present with only the completed files/)
  assert.match(renderTurnContext(context), /Do not present probes, drafts, or temporary files/)
  assert.match(renderTurnContext(context), /Do not put object_path, sandbox: paths/)
  assert.match(renderTurnContext(context), /does not restrict ordinary public web links or Markdown image references/)
})

test('trusted turn context exposes governed references but strips signed URLs', () => {
  const context = normalizeTurnContext({
    knowledge_qa_enabled: true,
    knowledge_base_ids: ['kb-secret-id'],
    documents: [{ object_path: 'tenant/file.docx', filename: 'file.docx', signed_url: 'secret' }],
    images: [],
  })
  const prompt = renderTurnContext(context)
  assert.match(prompt, /must call knowledge_search/)
  assert.match(prompt, /private MOVO locators/)
  assert.match(prompt, /never include them in the answer/)
  assert.doesNotMatch(prompt, /preserve citation_ref values/)
  assert.match(prompt, /tenant\/file\.docx/)
  assert.doesNotMatch(prompt, /kb-secret-id|signed_url|secret/)
})

test('trusted turn context rejects unversioned arbitrary fields', () => {
  assert.throws(() => normalizeTurnContext({ tenant_id: 'forged' }), /unknown fields/)
})

test('automatic retrieval lets DSH choose internal, public, both, or neither', () => {
  const prompt = renderTurnContext(normalizeTurnContext({
    knowledge_qa_enabled: false,
    knowledge_base_ids: [],
  }))
  assert.match(prompt, /retrieval mode is automatic/)
  assert.match(prompt, /knowledge_search for enterprise-internal/)
  assert.match(prompt, /web_search for one bounded public/)
  assert.match(prompt, /progressive_research for multi-source/)
  assert.match(prompt, /answer directly when retrieval is unnecessary/)
})

test('runtime persona keeps simple and progressive search execution mutually exclusive', async () => {
  const { ASKAI_RUNTIME_PERSONA } = await import('../src/runtime-persona.mjs')
  assert.match(ASKAI_RUNTIME_PERSONA, /web_search at most once/)
  assert.match(ASKAI_RUNTIME_PERSONA, /never follow it with web_search/)
  assert.match(ASKAI_RUNTIME_PERSONA, /instead of bypassing the research boundary/)
})

test('runtime persona keeps short writing in DSH and uses semantic long-form routing', async () => {
  const { ASKAI_RUNTIME_PERSONA } = await import('../src/runtime-persona.mjs')
  assert.match(ASKAI_RUNTIME_PERSONA, /Write ordinary short content directly/)
  assert.match(ASKAI_RUNTIME_PERSONA, /prefer run_script for steps that require execution/)
  assert.match(ASKAI_RUNTIME_PERSONA, /follow that node's tool binding/)
  assert.match(ASKAI_RUNTIME_PERSONA, /Make this choice semantically/)
  assert.match(ASKAI_RUNTIME_PERSONA, /MOVO carries the accepted evidence forward automatically/)
  assert.match(ASKAI_RUNTIME_PERSONA, /For requested images not directed by a loaded Skill/)
  assert.match(ASKAI_RUNTIME_PERSONA, /For requested images not directed by a loaded Skill, use generate_images/)
  assert.match(ASKAI_RUNTIME_PERSONA, /For a requested presentation not directed by a loaded Skill, use presentation_create once/)
  assert.match(ASKAI_RUNTIME_PERSONA, /A Skill may use presentation_create as part of its own workflow/)
  assert.match(ASKAI_RUNTIME_PERSONA, /Do not independently start a second workflow for the same requested deliverable/)
  assert.match(ASKAI_RUNTIME_PERSONA, /An embedded table or chart does not authorize a separate spreadsheet/)
  assert.match(ASKAI_RUNTIME_PERSONA, /^You are an enterprise AI assistant/)
  assert.match(ASKAI_RUNTIME_PERSONA, /assistant name supplied by the deployment identity section/)
  assert.doesNotMatch(ASKAI_RUNTIME_PERSONA, /You are ASKAI/)
})

test('trusted browser resume reveals only mission arguments', () => {
  const context = normalizeTurnContext({
    browser_resume: {
      suspension_id: 'secret-suspension',
      resume_signal: { resume_token: 'secret-token' },
      mission: { objective: 'finish the form', operation: 'submit', target_name: 'CRM', target_url: 'https://crm.test' },
    },
  })
  const prompt = renderTurnContext(context)
  assert.match(prompt, /Call browser_task exactly once/)
  assert.match(prompt, /finish the form/)
  assert.doesNotMatch(prompt, /secret-suspension|secret-token/)
})
