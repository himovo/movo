import { createHash } from 'node:crypto'
import { readFile } from 'node:fs/promises'
import { PLUGIN_CLIENT_SERVICES } from './plugin-client-services.mjs'

const SHELL_ID = 'movo-plugin-client-shell'
const SHELL_PATH = '/movo-client-shell.js'
const BOOT_SCRIPT = /(<script>globalThis\["__DSH_BOOT__"\] = )(.*?)(<\/script>)/s

const shellParts = await Promise.all([
  './plugin-client-shell/locales.js',
  './plugin-client-shell/conversation.js',
  './plugin-client-shell/client.js',
].map(path => readFile(new URL(path, import.meta.url))))
export const clientShellSource = Buffer.concat(shellParts.flatMap(part => [part, Buffer.from('\n')]))
const shellRevision = createHash('sha256').update(clientShellSource).digest('hex').slice(0, 12)
const shellUrl = `${SHELL_PATH}?rev=${shellRevision}`

export function injectPluginClientShell(html, plugin, { conversation = false } = {}) {
  if (!BOOT_SCRIPT.test(html)) throw new Error('DSH client boot manifest is unavailable')
  const withoutPreload = html.replace(/<link rel="preload" as="script" href="plugins\/\?\?[^>]+>/, '')
  return withoutPreload.replace(BOOT_SCRIPT, (_match, start, raw, end) => {
    const boot = JSON.parse(raw)
    if (!Array.isArray(boot.entries) || !Array.isArray(boot.batches)) {
      throw new Error('DSH client boot manifest is invalid')
    }
    const selected = new Set([
      '@deepseek-ai/dsh-typert-registry',
      '@deepseek-ai/dsh-client-modules',
      ...PLUGIN_CLIENT_SERVICES.filter(name => !conversation || name !== '@deepseek-ai/dsh-client-ui-conversation'),
      ...(plugin.client_modules ?? []).map(module => module.id),
    ])
    let changed = true
    while (changed) {
      changed = false
      for (const entry of boot.entries) {
        if (!selected.has(entry.id)) continue
        for (const dependency of entry.inject ?? []) {
          if (boot.entries.some(candidate => candidate.id === dependency) && !selected.has(dependency)) {
            selected.add(dependency)
            changed = true
          }
        }
      }
    }
    boot.entries = boot.entries.filter(entry => selected.has(entry.id))
    boot.batches = boot.batches.filter(batch => batch.phase === 'bootstrap')
    boot.batches.push(...boot.entries
      .filter(entry => entry.id !== '@deepseek-ai/dsh-client-modules')
      .map(entry => ({ phase: 'application', url: entry.url, rev: entry.rev, entries: [entry.id] })))
    if (!boot.entries.some(entry => entry.id === SHELL_ID)) {
      boot.entries.push({
        id: SHELL_ID,
        url: shellUrl,
        rev: shellRevision,
        inject: ['@deepseek-ai/dsh-client-ui-renderer', '@deepseek-ai/dsh-client-ui-session'],
        immediately: true,
      })
      boot.batches.push({ phase: 'application', url: shellUrl, rev: shellRevision, entries: [SHELL_ID] })
    }
    const pluginModule = (plugin.client_modules ?? []).find(module =>
      typeof module.id === 'string' && module.id)?.id ?? ''
    return `${start}${JSON.stringify(boot).replaceAll('<', '\\u003c')}${end}<script>globalThis.__MOVO_PLUGIN_MODULE__ = ${JSON.stringify(pluginModule).replaceAll('<', '\\u003c')}</script>`
  })
}

export function isClientShellRequest(path, method) {
  return method === 'GET' && path === SHELL_PATH
}
