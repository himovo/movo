import { PLUGIN_CLIENT_SERVICES } from './plugin-client-services.mjs'

const MAX_BODY_BYTES = 64 * 1024

async function allowedNamespaces(ctx, plugin) {
  const namespaces = new Set()
  const modules = new Set(PLUGIN_CLIENT_SERVICES)
  for (const { entry } of ctx.get('configEditor')?.configuration?.() ?? []) {
    if (modules.has(entry.options?.name)) namespaces.add(entry.options.id)
  }
  const bundles = await ctx.get('pluginManager')?.listBundles?.() ?? []
  const bundle = bundles.find(item => item.name === plugin.name && item.version === plugin.version && item.enabled)
  for (const row of bundle?.rows ?? []) {
    if (row.entryId) namespaces.add(String(row.entryId))
  }
  return namespaces
}

export async function pluginSettingsView(ctx, plugin) {
  const allowed = await allowedNamespaces(ctx, plugin)
  const settings = ctx.get('settings')
  if (!settings) throw new Error('plugin_ui_settings_unavailable')
  // Native settings owns schema-aware redaction; the scoped page does not
  // mount the unrestricted native settings controller.
  const descriptors = await settings.describe({ redactSecrets: true })
  return {
    writable: false,
    hasDocument: false,
    namespaces: descriptors.filter(item => allowed.has(item.ns)).map(item => ({
      ns: String(item.ns), autoGenerate: item.autoGenerate,
      schema: item.schema, value: item.value, applies: item.applies, revision: item.revision,
      ...(item.base === undefined ? {} : { base: item.base }),
      ...(item.user === undefined ? {} : { user: item.user }),
      secrets: (item.secrets ?? []).map(secret => ({ path: [...secret.path], set: secret.set })),
    })),
  }
}

export async function respondPluginSettings(ctx, plugin, request, response) {
  let length = 0
  const chunks = []
  for await (const chunk of request) {
    length += chunk.length
    if (length > MAX_BODY_BYTES) {
      response.writeHead(413)
      response.end()
      return
    }
    chunks.push(chunk)
  }
  let envelope
  try { envelope = JSON.parse(Buffer.concat(chunks).toString('utf8')) } catch { /* Invalid RPC input. */ }
  if (envelope?.type !== 'client-request' || envelope.method !== 'settings/describe' ||
      typeof envelope.rpcId !== 'string' || !envelope.rpcId || envelope.rpcId.length > 256) {
    response.writeHead(400)
    response.end()
    return
  }
  let result
  try {
    result = { ok: true, value: await pluginSettingsView(ctx, plugin) }
  } catch {
    const message = String(request.headers['accept-language'] ?? '').toLowerCase().startsWith('zh')
      ? '\u63d2\u4ef6\u754c\u9762\u8bbe\u7f6e\u6682\u4e0d\u53ef\u7528'
      : 'Plugin UI settings are unavailable'
    result = { ok: false, error: {
      code: 'plugin_ui_settings_unavailable', message, details: {},
    } }
  }
  response.writeHead(200, { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' })
  response.end(JSON.stringify({ type: 'server-response', rpcId: envelope.rpcId, result }))
}
