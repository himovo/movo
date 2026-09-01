import type { ExecutionItemV3 } from './model'

export type ExecutionTimelineEntry =
  | { type: 'item'; key: string; item: ExecutionItemV3 }
  | { type: 'tool-group'; key: string; items: ExecutionItemV3[]; statusItems: ExecutionItemV3[] }

const SENSITIVE_ARGUMENT = /(?:token|secret|password|authorization|cookie|api[_-]?key)/i
const INTERNAL_FILE_ARGUMENT = /^(?:object_path|signed_url|download_url|local_path|storage_path|blueprint_object_path)$/i
const FILE_ARGUMENT = /^(?:artifact|artifacts|file|files|document|documents|image|images|filename)$/i
const DETAIL_LIMIT = 180

export type ToolCapabilityKey =
  | 'execution.v3.activity.read_files'
  | 'execution.v3.activity.edit_files'
  | 'execution.v3.activity.run_commands'
  | 'execution.v3.activity.search_code'
  | 'execution.v3.activity.use_browser'
  | 'execution.v3.activity.search_web'
  | 'execution.v3.activity.call_tools'

function toolCapability(item: ExecutionItemV3): ToolCapabilityKey | null {
  const name = toolName(item).toLowerCase().replace(/[^a-z0-9]+/g, '_')
  if (/(?:^|_)(browser|navigate|click|fill|press|screenshot)(?:_|$)/.test(name)) return 'execution.v3.activity.use_browser'
  if (/(?:^|_)(web_search|search_web|internet_search|external_search)(?:_|$)/.test(name)) return 'execution.v3.activity.search_web'
  if (/(?:^|_)(apply_patch|patch|edit|write|create_file|delete_file|move_file|rename_file|multi_edit)(?:_|$)/.test(name)) return 'execution.v3.activity.edit_files'
  if (/(?:^|_)(bash|shell|terminal|exec|run_command|powershell|command)(?:_|$)/.test(name)) return 'execution.v3.activity.run_commands'
  if (/(?:^|_)(grep|glob|ripgrep|search_files|find_files|list_files)(?:_|$)/.test(name)) return 'execution.v3.activity.search_code'
  if (/(?:^|_)(read|read_file|view_file|preview_file|cat|head|tail)(?:_|$)/.test(name)) return 'execution.v3.activity.read_files'
  return null
}

/** Summarizes what a collapsed tool group actually did, in first-seen order. */
export function toolCapabilityKeys(items: ExecutionItemV3[]): ToolCapabilityKey[] {
  const keys: ToolCapabilityKey[] = []
  for (const item of items) {
    const key = toolCapability(item)
    if (key && !keys.includes(key)) keys.push(key)
  }
  return keys.length ? keys : ['execution.v3.activity.call_tools']
}

export function toolName(item: ExecutionItemV3): string {
  return String(item.payload?.display_name || item.payload?.name || '').trim() || 'tool'
}

function fileNameFromPath(value: unknown): string {
  const clean = String(value || '').split(/[?#]/, 1)[0].replace(/\\/g, '/')
  const name = clean.slice(clean.lastIndexOf('/') + 1)
  try { return decodeURIComponent(name) } catch { return name }
}

function friendlyFileValue(value: unknown): string {
  if (Array.isArray(value)) return value.map(friendlyFileValue).filter(Boolean).join(', ')
  if (!value || typeof value !== 'object') return fileNameFromPath(value)
  const record = value as Record<string, unknown>
  return String(record.filename || record.title || '').trim()
    || fileNameFromPath(record.object_path || record.url || record.signed_url)
}

function compactValue(value: unknown): string {
  if (typeof value === 'string') return value.replace(/\s+/g, ' ').trim()
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  if (Array.isArray(value)) return value.map(compactValue).filter(Boolean).join(', ')
  if (value && typeof value === 'object') {
    const record = value as Record<string, unknown>
    const visible = Object.entries(record)
      .filter(([key]) => !SENSITIVE_ARGUMENT.test(key) && !INTERNAL_FILE_ARGUMENT.test(key))
      .map(([key, nested]) => {
        const rendered = FILE_ARGUMENT.test(key) ? friendlyFileValue(nested) : compactValue(nested)
        return rendered ? `${key}: ${rendered}` : ''
      })
      .filter(Boolean)
    return visible.join(' · ')
  }
  return ''
}

function narrativeText(item: ExecutionItemV3): string {
  if (!['commentary', 'final_answer'].includes(item.kind)) return ''
  return String(item.payload?.text || '').replace(/\s+/g, ' ').trim()
}

function dedupeAdjacentNarration(items: ExecutionItemV3[]): ExecutionItemV3[] {
  const output: ExecutionItemV3[] = []
  for (const item of items) {
    const text = narrativeText(item)
    const previous = output.at(-1)
    if (text && previous && narrativeText(previous) === text) {
      // Prefer the authoritative completed commentary over a provisional
      // streamed assistant row left by older projected histories.
      if (item.kind === 'commentary' || previous.kind === 'final_answer') output[output.length - 1] = item
      continue
    }
    output.push(item)
  }
  return output
}

function structuralParentIds(items: ExecutionItemV3[]): Set<string> {
  const ids = new Set<string>()
  for (const item of items) {
    if (item.kind !== 'tool' || !item.payload?.code_dispatch) continue
    const parent = String(item.payload?.parent_call_id || '').trim()
    const root = String(item.payload?.root_call_id || '').trim()
    if (parent && parent !== item.id) ids.add(parent)
    if (root && root !== item.id) ids.add(root)
  }
  return ids
}

function relatedStatusItems(
  visible: ExecutionItemV3[],
  hiddenParents: Map<string, ExecutionItemV3>,
): ExecutionItemV3[] {
  const related = [...visible]
  const seen = new Set(visible.map(item => item.id))
  for (const item of visible) {
    for (const id of [item.payload?.parent_call_id, item.payload?.root_call_id]) {
      const parent = hiddenParents.get(String(id || ''))
      if (parent && !seen.has(parent.id)) {
        seen.add(parent.id)
        related.push(parent)
      }
    }
  }
  return related
}

/**
 * Produces a compact presentation projection without changing the underlying
 * audit events. Native code-dispatch parents are absorbed into their visible
 * leaf operations, and adjacent operations become one disclosure group.
 */
export function collapseRepeatedToolCalls(items: ExecutionItemV3[]): ExecutionTimelineEntry[] {
  const deduped = dedupeAdjacentNarration(items)
  const parentIds = structuralParentIds(deduped)
  const hiddenParents = new Map(
    deduped.filter(item => item.kind === 'tool' && parentIds.has(item.id)).map(item => [item.id, item]),
  )
  const visible = deduped.filter(item => item.kind !== 'tool' || !parentIds.has(item.id))
  const output: ExecutionTimelineEntry[] = []
  for (let index = 0; index < visible.length;) {
    const current = visible[index]
    if (current.kind !== 'tool') {
      output.push({ type: 'item', key: current.id, item: current })
      index += 1
      continue
    }

    const calls = [current]
    let cursor = index + 1
    while (cursor < visible.length && visible[cursor].kind === 'tool') {
      calls.push(visible[cursor])
      cursor += 1
    }
    const statusItems = relatedStatusItems(calls, hiddenParents)
    const hasStructuralParent = statusItems.length > calls.length
    output.push(calls.length === 1 && !hasStructuralParent
      ? { type: 'item', key: current.id, item: current }
      : { type: 'tool-group', key: `tool-group:${current.id}`, items: calls, statusItems })
    index = cursor
  }
  return output
}

export function toolCallSummary(item: ExecutionItemV3): string {
  const args = item.payload?.args
  if (!args || typeof args !== 'object' || Array.isArray(args)) return ''
  const description = compactValue((args as Record<string, unknown>).description)
  return description || toolCallDetail(item)
}

/** A schema-agnostic, redacted view of supplied call arguments for the detail list. */
export function toolCallDetail(item: ExecutionItemV3): string {
  const args = item.payload?.args
  if (!args || typeof args !== 'object' || Array.isArray(args)) return ''
  const parts = Object.entries(args as Record<string, unknown>)
    .filter(([key]) => !SENSITIVE_ARGUMENT.test(key) && !INTERNAL_FILE_ARGUMENT.test(key))
    .map(([key, value]) => {
      const rendered = FILE_ARGUMENT.test(key) ? friendlyFileValue(value) : compactValue(value)
      if (!rendered) return ''
      return FILE_ARGUMENT.test(key) ? rendered : `${key}: ${rendered}`
    })
    .filter(Boolean)
  const detail = parts.join(' · ')
  return detail.length > DETAIL_LIMIT ? `${detail.slice(0, DETAIL_LIMIT)}…` : detail
}
