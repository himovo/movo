import assert from 'node:assert/strict'
import test from 'node:test'
import { reactive } from 'vue'
import { cloneQuestionAnswers } from '../src/platform/cloneQuestionAnswers'

test('question answers cross Electron IPC without Vue proxies', () => {
  const selected = reactive(['cancel'])
  const answers = [{ id: 'question-1', selected }]
  const cloned = cloneQuestionAnswers(answers)
  assert.deepEqual(structuredClone(cloned), [{ id: 'question-1', selected: ['cancel'] }])
  assert.notEqual(cloned[0]?.selected, selected)
})
