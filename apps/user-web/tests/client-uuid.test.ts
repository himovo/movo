import assert from 'node:assert/strict'
import test from 'node:test'
import { createClientUuid } from '../src/utils/clientUuid'

const uuidV4Pattern = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/

test('uses crypto.randomUUID when the secure-context API is available', () => {
  const expected = '11111111-2222-4333-8444-555555555555'
  assert.equal(createClientUuid({ randomUUID: () => expected }), expected)
})

test('uses crypto.getRandomValues on non-secure HTTP origins', () => {
  const generated = createClientUuid({
    getRandomValues: values => {
      values.forEach((_, index) => { values[index] = index })
      return values
    },
  })

  assert.match(generated, uuidV4Pattern)
  assert.equal(generated, '00010203-0405-4607-8809-0a0b0c0d0e0f')
})

test('still returns a valid UUID when Web Crypto is unavailable', () => {
  assert.match(createClientUuid(null), uuidV4Pattern)
})
