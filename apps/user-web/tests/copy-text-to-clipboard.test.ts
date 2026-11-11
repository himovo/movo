import assert from 'node:assert/strict'
import { copyTextToClipboard, type ClipboardEnvironment } from '../src/utils/copyTextToClipboard'

async function testClipboardApi() {
  let copied = ''
  await copyTextToClipboard('share-url', {
    clipboard: { writeText: async text => { copied = text } },
  })
  assert.equal(copied, 'share-url')
}

async function testSelectionFallback() {
  let appended = false
  let removed = false
  let selected = false
  const textarea = {
    value: '',
    readOnly: false,
    style: {},
    setAttribute() {},
    focus() {},
    select() { selected = true },
    setSelectionRange() {},
    remove() { removed = true },
  }
  const documentRef = {
    activeElement: null,
    body: { appendChild() { appended = true } },
    createElement() { return textarea },
    execCommand(command: string) { return command === 'copy' },
  } as unknown as Document
  const environment: ClipboardEnvironment = {
    clipboard: { writeText: async () => { throw new Error('permission denied') } },
    document: documentRef,
  }

  await copyTextToClipboard('fallback-url', environment)
  assert.equal(textarea.value, 'fallback-url')
  assert.equal(appended, true)
  assert.equal(selected, true)
  assert.equal(removed, true)
}

async function testUnavailableClipboard() {
  await assert.rejects(() => copyTextToClipboard('share-url', {}), /unavailable/)
}

async function testInsecureContextUsesLegacyCopy() {
  let legacyCopyAttempted = false
  const textarea = {
    value: '', readOnly: false, style: {}, setAttribute() {}, focus() {},
    select() {}, setSelectionRange() {}, remove() {},
  }
  const environment: ClipboardEnvironment = {
    document: {
      activeElement: null,
      body: { appendChild() {} },
      createElement() { return textarea },
      execCommand() { legacyCopyAttempted = true; return true },
    } as unknown as Document,
  }
  await copyTextToClipboard('share-url', environment)
  assert.equal(legacyCopyAttempted, true)
  assert.equal(textarea.value, 'share-url')
}

await testClipboardApi()
await testSelectionFallback()
await testUnavailableClipboard()
await testInsecureContextUsesLegacyCopy()
console.log('copy-text-to-clipboard tests passed')
