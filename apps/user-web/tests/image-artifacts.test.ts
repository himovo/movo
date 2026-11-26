import assert from 'node:assert/strict'
import test from 'node:test'
import { ensureMessageExecutionV3, reconcileMessageExecutionSnapshot } from '../src/features/execution-v3/stores/messageExecution'
import { visibleAnswerArtifacts } from '../src/features/execution-v3/domain/artifactVisibility'
import { isImageArtifact } from '../src/features/execution-v3/domain/artifactKind'
import { imageIsInline, inlineImageUrls } from '../src/features/execution-v3/domain/inlineImageArtifacts'
import type { ExecutionEventV3 } from '../src/features/execution-v3/domain/protocol'

const image = { type: 'webp', filename: 'cat.webp', object_path: 'owner/cat.webp', url: 'https://assets.test/cat.webp?signature=old', image_model_id: 'original-model' }
const row: ExecutionEventV3 = {
  v: 3, event_id: 'image', id: 'image', ts: 1, type: 'item.completed',
  item_kind: 'artifact', item_id: 'image', revision: 1, payload: { ...image, kind: image.type },
}

test('images display while running and survive history and snapshot reconciliation without duplicates', () => {
  const message = { execution_events: [row], documents: [image] }
  const store = ensureMessageExecutionV3(message)
  assert.equal(store.state.artifacts.length, 1)
  assert.equal(visibleAnswerArtifacts(store.state.artifacts, 'running').length, 1)
  reconcileMessageExecutionSnapshot(message)
  store.applyEvent(row)
  assert.equal(store.state.artifacts.length, 1)
  assert.equal(isImageArtifact(store.state.artifacts[0]!), true)
  assert.equal(store.state.artifacts[0]!.image_model_id, 'original-model')
  const html = { id: 'html', ts: 1, kind: 'html', filename: 'report.html' }
  assert.deepEqual(visibleAnswerArtifacts([html, ...store.state.artifacts], 'running'), store.state.artifacts)
  assert.equal(visibleAnswerArtifacts([html, ...store.state.artifacts], 'completed').length, 2)
})

test('only actual inline image references suppress the second large thumbnail', () => {
  const artifact = ensureMessageExecutionV3({ execution_events: [row] }).state.artifacts[0]!
  assert.equal(imageIsInline(artifact, inlineImageUrls('Done')), false)
  assert.equal(imageIsInline(artifact, inlineImageUrls(`[download](${image.url})`)), false)
  assert.equal(imageIsInline(artifact, inlineImageUrls('![cat](https://assets.test/cat.webp?signature=new)')), true)
  assert.equal(imageIsInline(artifact, inlineImageUrls('```\n![cat](https://assets.test/cat.webp)\n```')), false)
  assert.equal(imageIsInline(artifact, inlineImageUrls('![cat](https://other.test/cat.webp)')), false)
})
