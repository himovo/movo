import { readFile } from 'node:fs/promises'

const CONVERSATION_VIEW_REGISTRATION = /\.slots\.(?:inject|register)\s*\(\s*(?:\{\s*name\s*:\s*)?["'`]conversation\.view["'`]/
const cache = new Map()

async function hasConversationView(path, revision) {
  if (!path) return false
  const key = `${path}:${revision}`
  if (!cache.has(key)) {
    cache.set(key, readFile(path, 'utf8').then(
      source => CONVERSATION_VIEW_REGISTRATION.test(source),
      () => false,
    ))
  }
  return cache.get(key)
}

export async function clientModuleSummaries(modules) {
  if (!modules) return []
  return Promise.all(modules.graph().entries.map(async entry => ({
    id: entry.id,
    rev: entry.rev,
    conversationView: await hasConversationView(modules.clientPath(entry.id), entry.rev),
  })))
}
