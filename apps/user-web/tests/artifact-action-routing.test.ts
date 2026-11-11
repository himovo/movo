import assert from 'node:assert/strict'
import test from 'node:test'
import { resolveArtifactPresentation } from '../src/registries/artifacts'
import { useChatArtifactActions } from '../src/components/chat/useChatArtifactActions'
import type { ArtifactItem } from '../src/features/execution-v3/domain/delivery'
import type { ChatMessage } from '../src/components/chat/chatMessage'

const message: ChatMessage = { role: 'assistant', content: '' }

function actionsFor(artifact: ArtifactItem) {
  return resolveArtifactPresentation(artifact).actions
}

test('a Skill-produced PPTX offers download without a misleading online edit action', () => {
  const artifact: ArtifactItem = { id: 'pptx', ts: 1, kind: 'pptx', filename: 'deck.pptx', object_path: 'user/deck.pptx' }
  assert.deepEqual(actionsFor(artifact), ['download'])
  const calls: string[] = []
  const actions = useChatArtifactActions({
    downloadDocument: () => calls.push('download'),
    openDocumentEditor: () => calls.push('document-editor'),
    openPresentationEditor: () => calls.push('presentation-editor'),
    confirmPresentationPreview: () => {},
    openHtmlPreview: () => {},
    openFilePreview: () => {},
  })
  actions.onArtifactOpen(artifact, message, 0)
  assert.deepEqual(calls, ['download'])
})

test('a presentation with a blueprint keeps its online editor action', () => {
  const artifact: ArtifactItem = {
    id: 'editable', ts: 1, kind: 'pptx', filename: 'deck.pptx',
    bundle: { deck_ir_artifact: { object_path: 'user/blueprint.json' } },
  }
  assert.ok(actionsFor(artifact).includes('edit'))
  let opened = false
  const actions = useChatArtifactActions({
    downloadDocument: () => {},
    openDocumentEditor: () => {},
    openPresentationEditor: () => { opened = true },
    confirmPresentationPreview: () => {},
    openHtmlPreview: () => {},
    openFilePreview: () => {},
  })
  actions.onArtifactOpen(artifact, message, 0)
  assert.equal(opened, true)
})

test('generated PDF, Word, and Excel open the file preview without an edit action', () => {
  const calls: string[] = []
  const actions = useChatArtifactActions({
    downloadDocument: () => calls.push('download'),
    openDocumentEditor: () => calls.push('document-editor'),
    openPresentationEditor: () => calls.push('presentation-editor'),
    confirmPresentationPreview: () => {},
    openHtmlPreview: () => {},
    openFilePreview: () => calls.push('file-preview'),
  })
  for (const kind of ['pdf', 'doc', 'docx', 'xls', 'xlsx', 'xlsm']) {
    const artifact: ArtifactItem = { id: kind, ts: 1, kind, filename: `result.${kind}`, object_path: `owner/result.${kind}` }
    assert.ok(actionsFor(artifact).includes('preview'))
    assert.ok(!actionsFor(artifact).includes('edit'))
    actions.onArtifactOpen(artifact, message, 0)
    actions.onArtifactPreviewHtml(artifact)
  }
  assert.deepEqual(calls, Array(12).fill('file-preview'))
})
