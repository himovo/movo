import assert from 'node:assert/strict'
import { visibleAnswerArtifacts } from '../src/features/execution-v3/domain/artifactVisibility'
import { ensureMessageExecutionV3 } from '../src/features/execution-v3/stores/messageExecution'

const first = { id: 'first', ts: 1, kind: 'document', filename: 'draft.docx', object_path: 'user/draft.docx' }
const final = { id: 'final', ts: 2, kind: 'document', filename: 'final.docx', object_path: 'user/final.docx' }

assert.deepEqual(visibleAnswerArtifacts([first, final], 'running'), [])
assert.deepEqual(visibleAnswerArtifacts([first, final], 'completed'), [first, final])
assert.deepEqual(visibleAnswerArtifacts([
  { ...first, lifecycle: 'intermediate', visibility: 'internal' }, final,
], 'completed'), [final])

const preview = {
  id: 'preview', ts: 3, kind: 'presentation_preview_bundle',
  bundle: { deck_ir_artifact: { object_path: 'user/deck.json' } },
}
const exported = {
  id: 'pptx', ts: 4, kind: 'pptx', filename: 'deck.pptx',
  bundle: { preview_metadata: { blueprint_artifact_path: 'user/deck.json' } },
}
const otherDeck = { ...preview, id: 'other', ts: 2, bundle: { deck_ir_artifact: { object_path: 'user/other.json' } } }
assert.deepEqual(visibleAnswerArtifacts([preview, exported, otherDeck, final], 'completed'), [exported, final])
assert.deepEqual(visibleAnswerArtifacts([preview, { ...exported, lifecycle: 'intermediate' }], 'completed'), [preview])
assert.deepEqual(visibleAnswerArtifacts([preview, { ...exported, bundle: undefined }], 'completed'), [{ ...exported, bundle: undefined }])

// Actual incident: one-page probe, two-page preview, and final PPTX.
const incident = [otherDeck, preview, exported]
assert.deepEqual(visibleAnswerArtifacts(incident, 'completed'), [exported])
assert.equal(incident.length, 3)
assert.deepEqual(visibleAnswerArtifacts([otherDeck, preview], 'completed'), [preview])
assert.deepEqual(visibleAnswerArtifacts(incident, 'running'), [])

// Re-exporting a deck replaces the old downloadable card, too.
const reexported = { ...exported, id: 'reexported', ts: 5, filename: 'revised.pptx' }
assert.deepEqual(visibleAnswerArtifacts([...incident, reexported], 'completed'), [reexported])
assert.deepEqual(visibleAnswerArtifacts([...incident, { ...reexported, visibility: 'internal' }], 'completed'), [exported])

// A new revision without an export must not masquerade as an older PPTX.
const revision = { ...otherDeck, ts: 6 }
assert.deepEqual(visibleAnswerArtifacts([...incident, revision], 'completed'), [revision])

// Preserve a valid export if its own preview is replayed with a newer timestamp.
assert.deepEqual(visibleAnswerArtifacts([exported, { ...preview, ts: 7 }], 'completed'), [exported])

// Historical HTML cards with a blueprint use the same policy.
assert.deepEqual(visibleAnswerArtifacts([
  { ...otherDeck, kind: 'html', filename: 'old.html' }, exported,
], 'completed'), [exported])

// Each call belongs to one assistant message; other conversation turns remain independent.
assert.deepEqual(visibleAnswerArtifacts([otherDeck], 'completed'), [otherDeck])
assert.deepEqual(visibleAnswerArtifacts([
  { ...preview, ts: 1 }, { ...otherDeck, ts: 1 },
], 'completed'), [{ ...otherDeck, ts: 1 }])

// Refresh/history hydration preserves all audit records, but shows one card.
const restored = ensureMessageExecutionV3({ documents: incident })
const restoredCards = visibleAnswerArtifacts(restored.state.artifacts, restored.state.runStatus)
assert.equal(restored.state.artifacts.length, 3)
assert.equal(restoredCards.length, 1)
assert.equal(restoredCards[0].filename, 'deck.pptx')
