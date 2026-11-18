import assert from 'node:assert/strict'
import { parseVisualBlock, visualKindFromHeading } from '../src/components/chat/assistantVisualBlocks'

for (const kind of ['metrics', 'priorities', 'flow', 'timeline', 'insights', 'checklist']) {
  const block = parseVisualBlock(JSON.stringify({ kind, title: 'Overview', items: [{ label: 'First', value: '12', detail: 'Detail', checked: true }] }))
  assert.equal(block?.kind, kind)
  assert.equal(block?.items[0].label, 'First')
}

assert.equal(parseVisualBlock('{"kind":"metrics","items":[]}'), null)
assert.equal(parseVisualBlock('{"kind":"other","items":[{"label":"A"}]}'), null)
assert.equal(parseVisualBlock('{"kind":"metrics","items":[{"label":""}]}'), null)
assert.equal(parseVisualBlock('{"kind":"metrics","items":[{"label":"A","tone":"invalid"}]}')?.items[0].tone, undefined)
assert.equal(parseVisualBlock('{"kind":"metrics","items":[{"label":"<script>alert(1)</script>"}]}')?.items[0].label, '<script>alert(1)</script>')

for (const [heading, kind] of [
  ['\u6307\u6807\u5bf9\u6bd4', 'metrics'],
  ['\u4e09\u9879\u4f18\u5148\u7ea7', 'priorities'],
  ['\u5206\u5c42\u6d41\u7a0b', 'flow'],
  ['\u4e09\u9636\u6bb5\u65f6\u95f4\u7ebf', 'timeline'],
  ['\u6838\u5fc3\u5224\u65ad', 'insights'],
  ['\u68c0\u67e5\u6e05\u5355', 'checklist'],
] as const) {
  assert.equal(visualKindFromHeading(heading), kind)
  assert.equal(parseVisualBlock('{"title":"Overview","items":[{"label":"A"}]}', heading)?.kind, kind)
  assert.equal(parseVisualBlock(JSON.stringify({ title: heading, items: [{ label: 'A' }] }))?.kind, kind)
}
assert.equal(parseVisualBlock('{"title":"Overview","items":[{"label":"A"}]}'), null)
