import assert from 'node:assert/strict'
import { test } from 'node:test'
import { UserQuestionBroker } from '../src/user-question-broker.mjs'

function fixture() {
  let handler
  const broker = new UserQuestionBroker({ on(name, callback, options) {
    assert.equal(name, 'user-questions/request')
    assert.equal(options.global, true)
    assert.equal(options.prepend, true)
    handler = callback
    return () => {}
  } })
  return { broker, request: (value, next) => handler(value, next) }
}

test('returns a structured choice batch to the owning session only', async () => {
  const { broker, request } = fixture()
  const result = request({ agent: { id: 'one', session: { id: 'one' } }, questions: [
    { id: 'q1', question: 'Which?', options: [{ label: 'A' }, { label: 'B' }] },
    { id: 'q2', question: 'Why?' },
  ] })
  assert.equal(broker.list('two').length, 0)
  const [item] = broker.list('one')
  assert.equal(item.questions.length, 2)
  assert.throws(() => broker.answer('two', item.id, [{ id: 'q1', selected: ['A'] }]))
  assert.throws(() => broker.answer('one', item.id, [{ id: 'q1', selected: ['A'] }]))
  assert.throws(() => broker.answer('one', item.id, [
    { id: 'q1', selected: ['C'] }, { id: 'q2', selected: [], custom: 'Because' },
  ]), /invalid user question choice/)
  assert.throws(() => broker.answer('one', item.id, [
    { id: 'q1', selected: [] }, { id: 'q2', selected: [], custom: 'Because' },
  ]), /invalid user question choice/)
  const receipt = broker.answer('one', item.id, [
    { id: 'q1', selected: ['A'] }, { id: 'q2', selected: [], custom: 'Because' },
  ])
  assert.deepEqual(receipt.questions, item.questions)
  assert.deepEqual(broker.answer('one', item.id, receipt.answers), receipt)
  assert.deepEqual(await result, { answers: [
    { id: 'q1', selected: ['A'] }, { id: 'q2', selected: [], custom: 'Because' },
  ] })
  assert.deepEqual(broker.list('one'), [])
  broker.dispose()
})

test('cancellation clears a pending human question', async () => {
  const { broker, request } = fixture()
  const controller = new AbortController()
  const result = request({ agent: { id: 'one', session: { id: 'one' } }, signal: controller.signal, questions: [{ id: 'q', question: 'Proceed?' }] })
  assert.equal(broker.list('one').length, 1)
  controller.abort()
  await assert.rejects(result, /cancelled/)
  assert.deepEqual(broker.list('one'), [])
  broker.dispose()
})

test('questions without an owning agent fall through to another answerer', async () => {
  const { broker, request } = fixture()
  let forwarded = false
  const result = await request({ questions: [] }, async () => {
    forwarded = true
    return { answers: [] }
  })
  assert.equal(forwarded, true)
  assert.deepEqual(result, { answers: [] })
  assert.deepEqual(broker.list('one'), [])
  broker.dispose()
})
