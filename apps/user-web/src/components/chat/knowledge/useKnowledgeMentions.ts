import { nextTick, onBeforeUnmount, ref, watch, type Ref } from 'vue'
import { searchKnowledgeReferences, type KnowledgeReference, type KnowledgeScope } from '../../../api/knowledgeReferences'
import { knowledgeMentionAt } from './mentionTrigger'

export function useKnowledgeMentions(options: { input: Ref<string>; element: Ref<HTMLTextAreaElement | null>; userId: () => string | undefined; mainId: () => string | undefined; allowed: () => boolean; onOpen: () => void; resize: () => void; onLimit: () => void }) {
  const open = ref(false), loading = ref(false), failed = ref(false)
  const scope = ref<KnowledgeScope>('personal'), directory = ref(''), query = ref('')
  const items = ref<KnowledgeReference[]>([]), selected = ref<KnowledgeReference[]>([])
  const active = ref(0), cursor = ref<number | null>(null)
  const root = ref<HTMLElement | null>(null)
  const trail = ref<Array<{ id: string; name: string }>>([])
  let timer: ReturnType<typeof setTimeout> | undefined, request: AbortController | undefined, generation = 0
  let trigger: ReturnType<typeof knowledgeMentionAt> = null
  function close() { open.value = false; generation++; request?.abort(); clearTimeout(timer) }
  async function load(more = false) {
    if (!open.value || (more && cursor.value === null)) return
    request?.abort(); request = new AbortController()
    const token = ++generation
    loading.value = true; failed.value = false
    if (!more) { items.value = []; active.value = 0; cursor.value = null }
    try {
      const page = await searchKnowledgeReferences({ scope: scope.value, keyword: query.value, directory_id: directory.value, cursor: more ? cursor.value! : 0 }, request.signal)
      if (token !== generation || !open.value) return
      items.value = more ? [...items.value, ...page.items] : page.items
      cursor.value = page.next_cursor
    } catch { if (token === generation && open.value) failed.value = true }
    finally { if (token === generation) loading.value = false }
  }
  function handleInput() {
    trigger = knowledgeMentionAt(options.input.value, options.element.value?.selectionStart ?? options.input.value.length)
    if (!trigger || !options.allowed() || !options.userId()) { close(); return }
    if (!open.value) { directory.value = ''; trail.value = [] }
    query.value = trigger.query; open.value = true; options.onOpen()
    clearTimeout(timer); request?.abort(); generation++
    timer = setTimeout(() => { void load() }, 200)
  }
  function setScope(value: KnowledgeScope) { scope.value = value; directory.value = ''; trail.value = []; void load() }
  function browse(item: KnowledgeReference) { directory.value = item.source_id; trail.value.push({ id: item.source_id, name: item.name }); query.value = ''; void load() }
  function back() { trail.value.pop(); directory.value = trail.value.at(-1)?.id || ''; void load() }
  async function select(item: KnowledgeReference) {
    if (!trigger) return
    if (selected.value.length >= 20 && !selected.value.some(row => row.scope === item.scope && row.kind === item.kind && row.source_id === item.source_id)) { options.onLimit(); return }
    if (!selected.value.some(row => row.scope === item.scope && row.kind === item.kind && row.source_id === item.source_id)) selected.value.push(item)
    const marker = `@「${item.name}」 `
    options.input.value = options.input.value.slice(0, trigger.start) + marker + options.input.value.slice(trigger.end)
    const position = trigger.start + marker.length
    close(); await nextTick(); options.element.value?.focus(); options.element.value?.setSelectionRange(position, position); options.resize()
  }
  function remove(item: KnowledgeReference) {
    selected.value = selected.value.filter(row => !(row.scope === item.scope && row.kind === item.kind && row.source_id === item.source_id))
    options.input.value = options.input.value.split(`@「${item.name}」`).join('')
    void nextTick(options.resize)
  }
  function keydown(event: KeyboardEvent) {
    if (!open.value) return false
    if (event.key === 'Escape') { event.preventDefault(); close(); return true }
    if (!event.altKey && !event.ctrlKey && !event.metaKey && ['ArrowLeft', 'ArrowRight'].includes(event.key)) {
      event.preventDefault()
      const nextScope = event.key === 'ArrowLeft' ? 'personal' : 'organization'
      if (scope.value !== nextScope) setScope(nextScope)
      return true
    }
    if (['ArrowDown', 'ArrowUp'].includes(event.key)) { event.preventDefault(); active.value = Math.max(0, Math.min(items.value.length - 1, active.value + (event.key === 'ArrowDown' ? 1 : -1))); void nextTick(() => root.value?.querySelectorAll('[role="option"]')[active.value]?.scrollIntoView({ block: 'nearest' })); return true }
    if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); if (items.value[active.value]) void select(items.value[active.value]); return true }
    return false
  }
  function outside(event: PointerEvent) { if (!root.value?.contains(event.target as Node) && event.target !== options.element.value) close() }
  if (typeof document !== 'undefined') document.addEventListener('pointerdown', outside)
  watch(options.input, text => { selected.value = selected.value.filter(item => text.includes(`@「${item.name}」`)) })
  watch([options.userId, options.mainId], () => { for (const item of [...selected.value]) remove(item); close() })
  onBeforeUnmount(() => { close(); document.removeEventListener('pointerdown', outside) })
  return { open, loading, failed, scope, items, selected, active, cursor, root, trail, handleInput, setScope, browse, back, select, remove, keydown, close, load }
}
