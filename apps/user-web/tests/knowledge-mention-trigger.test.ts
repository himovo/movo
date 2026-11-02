import assert from 'node:assert/strict'
import { knowledgeMentionAt } from '../src/components/chat/knowledge/mentionTrigger'
const text = 'Summarize @annual report'
assert.deepEqual(knowledgeMentionAt(text, text.length), { start: text.indexOf('@'), end: text.length, query: 'annual report' })
assert.equal(knowledgeMentionAt('someone@example.com', 19), null)
assert.equal(knowledgeMentionAt('Read @「Report」 ', 15), null)
assert.equal(knowledgeMentionAt('@report\nnext', 12), null)
assert.deepEqual(knowledgeMentionAt('@', 1), { start: 0, end: 1, query: '' })
const middle = 'Compare @report with another'
const caret = middle.indexOf(' with')
assert.equal(knowledgeMentionAt(middle, caret)?.query, 'report')
assert.equal(knowledgeMentionAt('Prefix /skill', 13), null)
console.log('Knowledge mention trigger checks passed')
