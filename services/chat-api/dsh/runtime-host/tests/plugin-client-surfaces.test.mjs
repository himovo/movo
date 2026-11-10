import assert from 'node:assert/strict'
import { mkdtemp, writeFile, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import test from 'node:test'

import { clientModuleSummaries } from '../src/official-host/plugin-client-surfaces.mjs'

test('client module summaries identify declared conversation views', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'movo-client-surfaces-'))
  try {
    const paths = [join(directory, 'view.js'), join(directory, 'main.js')]
    await writeFile(paths[0], 'ctx.slots.inject("conversation.view", () => ctx.slots.register({name: "conversation.view"}, render))')
    await writeFile(paths[1], 'ctx.slots.register({name: "main"}, render)')
    const modules = {
      graph: () => ({ entries: [{ id: 'with-view', rev: 'one' }, { id: 'main-only', rev: 'two' }] }),
      clientPath: id => paths[id === 'with-view' ? 0 : 1],
    }
    assert.deepEqual(await clientModuleSummaries(modules), [
      { id: 'with-view', rev: 'one', conversationView: true },
      { id: 'main-only', rev: 'two', conversationView: false },
    ])
  } finally {
    await rm(directory, { recursive: true, force: true })
  }
})
