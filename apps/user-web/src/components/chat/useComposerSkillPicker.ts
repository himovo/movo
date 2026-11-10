import { computed, nextTick, onBeforeUnmount, ref, watch, type Ref } from 'vue'
import { fetchSelectablePluginCommands, fetchSelectablePluginSkills, fetchSelectableSkills, type SelectableSkillItem } from '../../api/skills'

type Scope = 'all' | 'user' | 'organization'

interface Options {
  userId: () => string | undefined
  mainId: () => string | undefined
  allowSkills: () => boolean | undefined
  allowPluginEntries: () => boolean
  running: () => boolean
  input: Ref<string>
  inputElement: Ref<HTMLTextAreaElement | null>
  pickerElement: () => HTMLElement | null | undefined
  closeAttachmentMenu: () => void
  resizeInput: () => void
}

export function useComposerSkillPicker(options: Options) {
  const open = ref(false)
  const loading = ref(false)
  const loadingMore = ref(false)
  const scope = ref<Scope>('all')
  const keyword = ref('')
  const cursor = ref('')
  const hasMore = ref(false)
  const pluginCursor = ref('')
  const pluginHasMore = ref(false)
  const commandCursor = ref('')
  const commandHasMore = ref(false)
  const combinedHasMore = computed(() => hasMore.value || pluginHasMore.value || commandHasMore.value)
  const items = ref<SelectableSkillItem[]>([])
  const activeIndex = ref(-1)
  const selectedSkill = ref<SelectableSkillItem | null>(null)
  const triggerRange = ref<{ start: number; end: number } | null>(null)
  let requestSequence = 0
  let searchTimer: ReturnType<typeof setTimeout> | null = null

  function close() {
    open.value = false
    activeIndex.value = -1
    triggerRange.value = null
  }

  function normalizeSlashKeyword(value: string, selection = value.length): string | null {
    const text = String(value || '')
    const beforeCursor = text.slice(0, Math.max(0, selection))
    const slashIndex = beforeCursor.lastIndexOf('/')
    if (slashIndex < 0) return null
    const beforeSlash = slashIndex > 0 ? beforeCursor[slashIndex - 1] : ''
    if (beforeSlash && !/\s/.test(beforeSlash)) return null
    const rawKeyword = beforeCursor.slice(slashIndex + 1)
    if (/\s/.test(rawKeyword)) return null
    triggerRange.value = { start: slashIndex, end: selection }
    return rawKeyword.trim()
  }

  async function load(reset = false) {
    const userId = options.userId()
    if (!userId) return
    if (reset) {
      cursor.value = ''
      hasMore.value = false
      pluginCursor.value = ''
      pluginHasMore.value = false
      commandCursor.value = ''
      commandHasMore.value = false
    } else if ((!hasMore.value && !pluginHasMore.value && !commandHasMore.value) || loadingMore.value) return

    const requestId = ++requestSequence
    if (reset) loading.value = true
    else loadingMore.value = true
    try {
      const [native, plugin, commands] = await Promise.allSettled([
        options.allowSkills() !== false && (reset || hasMore.value) ? fetchSelectableSkills({
          userId, mainId: options.mainId() || 'default', scope: scope.value,
          keyword: keyword.value, cursor: reset ? '' : cursor.value, limit: 20,
        }) : Promise.resolve(null),
        options.allowPluginEntries() && (reset || pluginHasMore.value) ? fetchSelectablePluginSkills({
          scope: scope.value, keyword: keyword.value,
          cursor: reset ? '' : pluginCursor.value, limit: 20,
        }) : Promise.resolve(null),
        options.allowPluginEntries() && (reset || commandHasMore.value) ? fetchSelectablePluginCommands({
          scope: scope.value, keyword: keyword.value,
          cursor: reset ? '' : commandCursor.value, limit: 20,
        }) : Promise.resolve(null),
      ])
      if (requestId !== requestSequence) return
      const nativePage = native.status === 'fulfilled' ? native.value : null
      const pluginPage = plugin.status === 'fulfilled' ? plugin.value : null
      const commandPage = commands.status === 'fulfilled' ? commands.value : null
      const incoming = [...(nativePage?.items || []), ...(pluginPage?.items || []), ...(commandPage?.items || [])]
      items.value = reset ? incoming : [...items.value, ...incoming]
      cursor.value = nativePage?.nextCursor || ''
      hasMore.value = nativePage?.hasMore || false
      pluginCursor.value = pluginPage?.nextCursor || ''
      pluginHasMore.value = pluginPage?.hasMore || false
      commandCursor.value = commandPage?.nextCursor || ''
      commandHasMore.value = commandPage?.hasMore || false
      if (reset) activeIndex.value = incoming.findIndex(item => item.available !== false)
      else if (activeIndex.value >= items.value.length) activeIndex.value = items.value.findIndex(item => item.available !== false)
    } catch {
      if (requestId !== requestSequence) return
      if (reset) items.value = []
      hasMore.value = false
      if (reset) activeIndex.value = -1
    } finally {
      if (requestId === requestSequence) {
        loading.value = false
        loadingMore.value = false
      }
    }
  }

  function scheduleSearch(nextKeyword: string) {
    keyword.value = nextKeyword
    if (searchTimer) clearTimeout(searchTimer)
    searchTimer = setTimeout(() => { void load(true) }, 180)
  }
  function openPicker(nextKeyword = '') {
    if ((options.allowSkills() === false && !options.allowPluginEntries()) || !options.userId() || options.running()) return
    open.value = true
    options.closeAttachmentMenu()
    scheduleSearch(nextKeyword)
  }
  function handleInput() {
    options.resizeInput()
    const text = options.input.value
    const nextKeyword = normalizeSlashKeyword(text, options.inputElement.value?.selectionStart ?? text.length)
    if (nextKeyword === null) close()
    else openPicker(nextKeyword)
  }
  function setScope(nextScope: Scope) {
    if (scope.value === nextScope) return
    scope.value = nextScope
    void load(true)
  }
  function select(skill: SelectableSkillItem) {
    if (skill.available === false) return
    selectedSkill.value = skill
    const range = triggerRange.value
    if (range) options.input.value = `${options.input.value.slice(0, range.start)}${options.input.value.slice(range.end)}`
    else if (options.input.value.trim().startsWith('/')) options.input.value = ''
    close()
    nextTick(() => {
      options.resizeInput()
      options.inputElement.value?.focus()
    })
  }
  function moveActive(delta: number) {
    const selectable = items.value.map((item, index) => item.available !== false ? index : -1).filter(index => index >= 0)
    if (!selectable.length) {
      activeIndex.value = -1
      return
    }
    const current = selectable.indexOf(activeIndex.value)
    activeIndex.value = current < 0
      ? selectable[delta > 0 ? 0 : selectable.length - 1]
      : selectable[(current + delta + selectable.length) % selectable.length]
    nextTick(() => {
      options.pickerElement()?.querySelector<HTMLElement>(`[data-skill-index="${activeIndex.value}"]`)
        ?.scrollIntoView({ block: 'nearest' })
    })
  }
  function selectActive() {
    const skill = items.value[activeIndex.value] || items.value.find(item => item.available !== false)
    if (skill) select(skill)
  }
  function onScroll(event: Event) {
    const element = event.currentTarget as HTMLElement | null
    if (!element || loading.value || loadingMore.value || !combinedHasMore.value) return
    if (element.scrollTop + element.clientHeight >= element.scrollHeight - 24) void load(false)
  }
  async function selectShortcutSkill(skillId: string, label: string): Promise<boolean> {
    const userId = options.userId()
    if (!userId || options.allowSkills() === false || options.running()) return false
    const page = await fetchSelectableSkills({
      userId, mainId: options.mainId() || 'default', keyword: label, limit: 50,
    })
    const normalize = (value: string) => value.startsWith('org_skill:') ? value.slice('org_skill:'.length) : value
    const skill = page.items.find(item => normalize(item.id) === normalize(skillId))
    if (!skill || skill.available === false) return false
    select(skill)
    return true
  }

  watch(options.userId, () => {
    requestSequence += 1
    if (searchTimer) clearTimeout(searchTimer)
    close()
    selectedSkill.value = null
    items.value = []
  })
  watch(options.allowSkills, allowed => {
    if (allowed !== false || options.allowPluginEntries()) return
    requestSequence += 1
    if (searchTimer) clearTimeout(searchTimer)
    close()
    selectedSkill.value = null
    items.value = []
  })
  onBeforeUnmount(() => {
    requestSequence += 1
    if (searchTimer) clearTimeout(searchTimer)
  })

  return {
    open, loading, loadingMore, scope, hasMore: combinedHasMore, items, activeIndex,
    selectedSkill, close, openPicker, handleInput, load, setScope, select,
    moveActive, selectActive, onScroll, selectShortcutSkill,
  }
}
