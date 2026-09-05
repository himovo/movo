<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { ChatModelOption } from '../../api/models'
import { fetchSelectableSkills, type SelectableSkillItem } from '../../api/skills'
import { t, useLocale } from '../../composables/i18n'
import type { ChatDocumentKind, PendingDocument } from './types'

interface PendingImage {
  file: File
  previewUrl: string
}

const props = defineProps<{
  running: boolean
  stopping?: boolean
  isNewSessionView: boolean
  chatModels: ChatModelOption[]
  selectedModelId: string
  modelSelectorLabel: string
  modelLoadError?: string
  docIcon: (type: string) => string
  userId?: string
  mainId?: string
  allowKnowledge?: boolean
  allowSkills?: boolean
}>()

const emit = defineEmits<{
  (e: 'send', payload: { text: string; images: File[]; documents: PendingDocument[]; knowledgeQaEnabled: boolean; selectedSkillId?: string; modelId?: string }): void
  (e: 'stop'): void
  (e: 'select-model', modelId: string): void
  (e: 'image-preview', payload: { src: string; alt: string }): void
}>()

const { locale } = useLocale()

const userInput = ref('')
const composerInputRef = ref<HTMLTextAreaElement | null>(null)
const pendingImages = ref<PendingImage[]>([])
const pendingDocuments = ref<PendingDocument[]>([])
const imageInputRef = ref<HTMLInputElement | null>(null)
const documentInputRef = ref<HTMLInputElement | null>(null)
const attachmentMenuOpen = ref(false)
const attachmentMenuRef = ref<HTMLElement | null>(null)
const knowledgeQaEnabled = ref(false)
const modelDropdownOpen = ref(false)
const modelSelectorRef = ref<HTMLElement | null>(null)
const skillPickerOpen = ref(false)
const skillPickerLoading = ref(false)
const skillPickerLoadingMore = ref(false)
const skillPickerScope = ref<'all' | 'user' | 'organization'>('all')
const skillPickerKeyword = ref('')
const skillPickerCursor = ref('')
const skillPickerHasMore = ref(false)
const skillPickerItems = ref<SelectableSkillItem[]>([])
const activeSkillIndex = ref(-1)
const selectedSkill = ref<SelectableSkillItem | null>(null)
const skillPickerRef = ref<HTMLElement | null>(null)
const skillTriggerRange = ref<{ start: number; end: number } | null>(null)
const isComposingText = ref(false)
let skillPickerRequestSeq = 0
let skillPickerSearchTimer: ReturnType<typeof setTimeout> | null = null

const skillScopeOptions = computed<Array<{ key: 'all' | 'user' | 'organization'; label: string }>>(() => [
  { key: 'all', label: locale.value === 'zh' ? '全部' : 'All' },
  { key: 'user', label: locale.value === 'zh' ? '我的' : 'Mine' },
  { key: 'organization', label: locale.value === 'zh' ? '企业' : 'Org' },
])

function autoResizeComposerInput() {
  const el = composerInputRef.value
  if (!el) return
  el.style.height = ''
  el.style.height = `${el.scrollHeight}px`
}

function resetComposerInputHeight() {
  const el = composerInputRef.value
  if (!el) return
  el.style.height = ''
}

function revokePendingImage(url: string) {
  try {
    URL.revokeObjectURL(url)
  } catch {
    // ignore
  }
}

function closeAttachmentMenu() {
  attachmentMenuOpen.value = false
}

function closeSkillPicker() {
  skillPickerOpen.value = false
  activeSkillIndex.value = -1
  skillTriggerRange.value = null
}

function toggleAttachmentMenu() {
  attachmentMenuOpen.value = !attachmentMenuOpen.value
}

function openImagePicker() {
  imageInputRef.value?.click()
}

function openDocumentPicker() {
  documentInputRef.value?.click()
}

function selectImageAttachment() {
  closeAttachmentMenu()
  openImagePicker()
}

function selectDocumentAttachment() {
  closeAttachmentMenu()
  openDocumentPicker()
}

function toggleKnowledgeQa() {
  if (props.allowKnowledge === false) return
  knowledgeQaEnabled.value = !knowledgeQaEnabled.value
  closeAttachmentMenu()
}

function disableKnowledgeQa() {
  knowledgeQaEnabled.value = false
}

function enableKnowledgeQa() {
  if (props.allowKnowledge === false) return
  knowledgeQaEnabled.value = true
  closeAttachmentMenu()
}

function removePendingImage(index: number) {
  const item = pendingImages.value[index]
  if (!item) return
  revokePendingImage(item.previewUrl)
  pendingImages.value.splice(index, 1)
}

function removePendingDocument(index: number) {
  pendingDocuments.value.splice(index, 1)
}

function detectDocumentType(file: File): ChatDocumentKind | null {
  const name = String(file.name || '').toLowerCase()
  if (name.endsWith('.pdf')) return 'pdf'
  if (name.endsWith('.docx') || name.endsWith('.doc')) return 'docx'
  if (name.endsWith('.pptx') || name.endsWith('.ppt')) return 'pptx'
  if (name.endsWith('.md')) return 'md'
  if (name.endsWith('.xlsx') || name.endsWith('.xlsm') || name.endsWith('.xls')) return 'xlsx'
  if (name.endsWith('.csv') || name.endsWith('.tsv')) return 'xlsx'
  return null
}

function addImageFiles(files: File[]) {
  for (const file of files) {
    if (!(file.type || '').startsWith('image/')) continue
    const previewUrl = URL.createObjectURL(file)
    pendingImages.value.push({ file, previewUrl })
  }
}

function onImageSelected(event: Event) {
  const input = event.target as HTMLInputElement
  if (!input.files || input.files.length === 0) return
  addImageFiles(Array.from(input.files))
  input.value = ''
}

function onComposerPaste(event: ClipboardEvent) {
  if (props.running) return
  const items = Array.from(event.clipboardData?.items || [])
  const imageFiles = items
    .filter((item) => item.kind === 'file' && item.type.startsWith('image/'))
    .map((item) => item.getAsFile())
    .filter((file): file is File => Boolean(file))
  if (imageFiles.length === 0) return
  event.preventDefault()
  closeSkillPicker()
  closeAttachmentMenu()
  addImageFiles(imageFiles)
  nextTick(() => {
    composerInputRef.value?.focus()
  })
}

function onDocumentSelected(event: Event) {
  const input = event.target as HTMLInputElement
  if (!input.files || input.files.length === 0) return
  const files = Array.from(input.files)
  for (const file of files) {
    const kind = detectDocumentType(file)
    if (!kind) continue
    pendingDocuments.value.push({ file, kind })
  }
  input.value = ''
}

function toggleModelDropdown() {
  if (props.running) return
  modelDropdownOpen.value = !modelDropdownOpen.value
}

function selectChatModel(modelId: string) {
  emit('select-model', modelId)
  modelDropdownOpen.value = false
}

function onGlobalPointerDown(event: Event) {
  const target = event.target as Node | null
  if (!target) return
  const attachmentRoot = attachmentMenuRef.value
  if (attachmentMenuOpen.value && attachmentRoot && !attachmentRoot.contains(target)) {
    closeAttachmentMenu()
  }
  const modelRoot = modelSelectorRef.value
  if (modelDropdownOpen.value && modelRoot && !modelRoot.contains(target)) {
    modelDropdownOpen.value = false
  }
  const pickerRoot = skillPickerRef.value
  const inputRoot = composerInputRef.value
  if (
    skillPickerOpen.value &&
    pickerRoot &&
    !pickerRoot.contains(target) &&
    inputRoot &&
    !inputRoot.contains(target)
  ) {
    closeSkillPicker()
  }
}

function skillTypeLabel(type: SelectableSkillItem['type']) {
  if (type === 'workflow') return locale.value === 'zh' ? '工作流' : 'Workflow'
  return locale.value === 'zh' ? '写作规范' : 'Writing'
}

function skillSourceLabel(source: SelectableSkillItem['sourceScope']) {
  if (source === 'organization') return locale.value === 'zh' ? '企业' : 'Org'
  return locale.value === 'zh' ? '我的' : 'Mine'
}

function normalizeSlashKeyword(value: string, cursor = value.length) {
  const text = String(value || '')
  const beforeCursor = text.slice(0, Math.max(0, cursor))
  const slashIndex = beforeCursor.lastIndexOf('/')
  if (slashIndex < 0) return null
  const beforeSlash = slashIndex > 0 ? beforeCursor[slashIndex - 1] : ''
  if (beforeSlash && !/\s/.test(beforeSlash)) return null
  const rawKeyword = beforeCursor.slice(slashIndex + 1)
  if (/\s/.test(rawKeyword)) return null
  skillTriggerRange.value = { start: slashIndex, end: cursor }
  return rawKeyword.trim()
}

async function loadSelectableSkills(reset = false) {
  if (!props.userId) return
  if (reset) {
    skillPickerCursor.value = ''
    skillPickerHasMore.value = false
  } else if (!skillPickerHasMore.value || skillPickerLoadingMore.value) {
    return
  }
  const requestId = ++skillPickerRequestSeq
  if (reset) {
    skillPickerLoading.value = true
  } else {
    skillPickerLoadingMore.value = true
  }
  try {
    const page = await fetchSelectableSkills({
      userId: props.userId,
      mainId: props.mainId || 'default',
      scope: skillPickerScope.value,
      keyword: skillPickerKeyword.value,
      cursor: reset ? '' : skillPickerCursor.value,
      limit: 20,
    })
    if (requestId !== skillPickerRequestSeq) return
    skillPickerItems.value = reset ? page.items : [...skillPickerItems.value, ...page.items]
    skillPickerCursor.value = page.nextCursor
    skillPickerHasMore.value = page.hasMore
    if (reset) {
      activeSkillIndex.value = page.items.length > 0 ? 0 : -1
    } else if (activeSkillIndex.value >= skillPickerItems.value.length) {
      activeSkillIndex.value = skillPickerItems.value.length > 0 ? skillPickerItems.value.length - 1 : -1
    }
  } catch {
    if (requestId !== skillPickerRequestSeq) return
    if (reset) skillPickerItems.value = []
    skillPickerHasMore.value = false
    if (reset) activeSkillIndex.value = -1
  } finally {
    if (requestId === skillPickerRequestSeq) {
      skillPickerLoading.value = false
      skillPickerLoadingMore.value = false
    }
  }
}

function scheduleSkillPickerSearch(keyword: string) {
  skillPickerKeyword.value = keyword
  if (skillPickerSearchTimer) clearTimeout(skillPickerSearchTimer)
  skillPickerSearchTimer = setTimeout(() => {
    loadSelectableSkills(true)
  }, 180)
}

function openSkillPicker(keyword = '') {
  if (props.allowSkills === false || !props.userId || props.running) return
  skillPickerOpen.value = true
  closeAttachmentMenu()
  scheduleSkillPickerSearch(keyword)
}

function handleComposerInput() {
  autoResizeComposerInput()
  const keyword = normalizeSlashKeyword(userInput.value, composerInputRef.value?.selectionStart ?? userInput.value.length)
  if (keyword === null) {
    closeSkillPicker()
    return
  }
  openSkillPicker(keyword)
}

function setSkillPickerScope(scope: 'all' | 'user' | 'organization') {
  if (skillPickerScope.value === scope) return
  skillPickerScope.value = scope
  loadSelectableSkills(true)
}

function selectSkill(skill: SelectableSkillItem) {
  selectedSkill.value = skill
  const range = skillTriggerRange.value
  if (range) {
    userInput.value = `${userInput.value.slice(0, range.start)}${userInput.value.slice(range.end)}`
  } else if (userInput.value.trim().startsWith('/')) {
    userInput.value = ''
  }
  closeSkillPicker()
  nextTick(() => {
    autoResizeComposerInput()
    composerInputRef.value?.focus()
  })
}

function scrollActiveSkillIntoView() {
  nextTick(() => {
    const root = skillPickerRef.value
    if (!root || activeSkillIndex.value < 0) return
    const el = root.querySelector<HTMLElement>(`[data-skill-index="${activeSkillIndex.value}"]`)
    el?.scrollIntoView({ block: 'nearest' })
  })
}

function moveActiveSkill(delta: number) {
  const total = skillPickerItems.value.length
  if (total <= 0) {
    activeSkillIndex.value = -1
    return
  }
  const current = activeSkillIndex.value < 0 ? (delta > 0 ? -1 : 0) : activeSkillIndex.value
  activeSkillIndex.value = (current + delta + total) % total
  scrollActiveSkillIntoView()
}

function selectActiveSkill() {
  const skill = skillPickerItems.value[activeSkillIndex.value] || skillPickerItems.value[0]
  if (skill) selectSkill(skill)
}

function onComposerCompositionStart() {
  isComposingText.value = true
}

function onComposerCompositionEnd() {
  isComposingText.value = false
}

function isImeCompositionKey(event: KeyboardEvent) {
  return isComposingText.value || event.isComposing || event.key === 'Process' || event.keyCode === 229
}

function clearSelectedSkill() {
  selectedSkill.value = null
}

function onSkillPickerScroll(event: Event) {
  const el = event.currentTarget as HTMLElement | null
  if (!el || skillPickerLoading.value || skillPickerLoadingMore.value || !skillPickerHasMore.value) return
  if (el.scrollTop + el.clientHeight >= el.scrollHeight - 24) {
    loadSelectableSkills(false)
  }
}

function onComposerKeydown(event: KeyboardEvent) {
  if (isImeCompositionKey(event)) {
    return
  }
  if (skillPickerOpen.value) {
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      moveActiveSkill(1)
      return
    }
    if (event.key === 'ArrowUp') {
      event.preventDefault()
      moveActiveSkill(-1)
      return
    }
    if (event.key === 'Escape') {
      event.preventDefault()
      closeSkillPicker()
      return
    }
  }
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    if (skillPickerOpen.value) {
      selectActiveSkill()
      return
    }
    sendMessage()
  }
}

async function sendMessage() {
  if (props.running) {
    if (props.stopping) return
    emit('stop')
    return
  }
  const hasText = !!userInput.value.trim()
  const hasImages = pendingImages.value.length > 0
  const hasDocuments = pendingDocuments.value.length > 0
  const hasSelectedSkill = !!selectedSkill.value
  if (!hasText && !hasImages && !hasDocuments && !hasSelectedSkill) return

  const text = userInput.value
  const imageFiles = pendingImages.value.map((item) => item.file)
  const documentFiles = pendingDocuments.value.map((item) => ({ file: item.file, kind: item.kind }))
  closeAttachmentMenu()
  userInput.value = ''
  await nextTick()
  resetComposerInputHeight()
  for (const item of pendingImages.value) {
    revokePendingImage(item.previewUrl)
  }
  pendingImages.value = []
  pendingDocuments.value = []
  emit('send', {
    text,
    images: imageFiles,
    documents: documentFiles,
    knowledgeQaEnabled: knowledgeQaEnabled.value,
    selectedSkillId: selectedSkill.value?.id || undefined,
    modelId: props.selectedModelId || undefined,
  })
  selectedSkill.value = null
}

function openPendingImagePreview(src: string, alt: string) {
  emit('image-preview', { src, alt })
}

async function setTextAndFocus(text: string) {
  userInput.value = text
  await nextTick()
  autoResizeComposerInput()
  composerInputRef.value?.focus()
}

defineExpose({
  enableKnowledgeQa,
  setTextAndFocus,
})

onMounted(() => {
  document.addEventListener('pointerdown', onGlobalPointerDown)
})

onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', onGlobalPointerDown)
  if (skillPickerSearchTimer) clearTimeout(skillPickerSearchTimer)
  for (const item of pendingImages.value) {
    revokePendingImage(item.previewUrl)
  }
  pendingDocuments.value = []
})

watch(() => props.userId, () => {
  closeSkillPicker()
  selectedSkill.value = null
  skillPickerItems.value = []
})

watch(() => props.allowKnowledge, (allowed) => {
  if (allowed === false) knowledgeQaEnabled.value = false
})

watch(() => props.allowSkills, (allowed) => {
  if (allowed !== false) return
  closeSkillPicker()
  selectedSkill.value = null
  skillPickerItems.value = []
})
</script>

<template>
  <input
    ref="imageInputRef"
    type="file"
    accept="image/*"
    multiple
    class="hidden"
    @change="onImageSelected"
  />
  <input
    ref="documentInputRef"
    type="file"
    accept=".pdf,.doc,.docx,.ppt,.pptx,.md,.txt,.xlsx,.xlsm,.csv,.tsv,.xls"
    multiple
    class="hidden"
    @change="onDocumentSelected"
  />

  <div
    :class="isNewSessionView
      ? 'absolute inset-x-0 top-1/2 -translate-y-1/2 w-full px-4 z-10'
      : 'shrink-0 w-full bg-white pt-2 pb-6 px-4 border-t border-gray-100'"
  >
    <div class="max-w-4xl mx-auto">
      <div v-if="isNewSessionView" class="mb-6 text-center text-4xl font-semibold text-slate-800">
        {{ t('chat.welcome_title') }}
      </div>
      <div v-if="pendingImages.length" class="mb-2 flex flex-wrap gap-2">
        <div
          v-for="(item, idx) in pendingImages"
          :key="`${item.file.name}-${idx}`"
          class="relative"
        >
          <img
            :src="item.previewUrl"
            :alt="item.file.name"
            class="h-16 w-24 cursor-zoom-in rounded-lg border border-gray-200 object-cover"
            @click="openPendingImagePreview(item.previewUrl, item.file.name)"
          />
          <button
            class="absolute -right-1 -top-1 h-5 w-5 rounded-full bg-black/70 text-xs text-white"
            @click="removePendingImage(idx)"
          >
            x
          </button>
        </div>
      </div>
      <div v-if="pendingDocuments.length" class="mb-2 flex flex-wrap gap-2">
        <div
          v-for="(item, idx) in pendingDocuments"
          :key="`${item.file.name}-${idx}`"
          class="relative flex items-center gap-2 rounded-xl border border-gray-200 bg-white px-3 py-2 shadow-sm"
        >
          <img :src="docIcon(item.kind)" :alt="item.kind" class="h-8 w-8 object-contain" />
          <div class="max-w-[180px]">
            <div class="truncate text-sm font-medium text-slate-700">{{ item.file.name }}</div>
            <div class="text-xs text-slate-400">{{ item.kind.toUpperCase() }}</div>
          </div>
          <button
            class="absolute -right-1 -top-1 h-5 w-5 rounded-full bg-black/70 text-xs text-white"
            @click="removePendingDocument(idx)"
          >
            x
          </button>
        </div>
      </div>
      <div v-if="knowledgeQaEnabled" class="mb-2 flex flex-wrap gap-2">
        <button
          type="button"
          class="inline-flex min-h-9 items-center gap-2 rounded-full border border-blue-200 bg-blue-50 px-3 text-sm font-medium text-blue-700 shadow-sm transition hover:border-blue-300 hover:bg-blue-100"
          @click="disableKnowledgeQa"
        >
          <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4z"></path>
            <path d="M9 9a3 3 0 0 1 6 0c0 2-3 2-3 4"></path>
            <path d="M12 17h.01"></path>
          </svg>
          <span>{{ t('chat.knowledge_qa_active') }}</span>
          <svg class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" aria-hidden="true">
            <path d="M18 6 6 18"></path>
            <path d="m6 6 12 12"></path>
          </svg>
        </button>
      </div>
      <div v-if="selectedSkill" class="mb-2 flex flex-wrap gap-2">
        <button
          type="button"
          class="inline-flex min-h-9 max-w-full items-center gap-2 rounded-full border border-indigo-200 bg-indigo-50 px-3 text-sm font-medium text-indigo-700 shadow-sm transition hover:border-indigo-300 hover:bg-indigo-100"
          :title="selectedSkill.name"
          @click="clearSelectedSkill"
        >
          <svg class="h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M12 3l7 4v5c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V7l7-4z"></path>
            <path d="M9 12l2 2 4-5"></path>
          </svg>
          <span class="shrink-0">{{ locale === 'zh' ? '已选择' : 'Selected' }}</span>
          <span class="min-w-0 truncate">{{ selectedSkill.name }}</span>
          <span class="shrink-0 rounded-full bg-white/70 px-1.5 py-0.5 text-[11px] text-indigo-600">{{ skillSourceLabel(selectedSkill.sourceScope) }}</span>
          <svg class="h-3.5 w-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" aria-hidden="true">
            <path d="M18 6 6 18"></path>
            <path d="m6 6 12 12"></path>
          </svg>
        </button>
      </div>
      <div class="composer-context-slot"><slot name="context" /></div>
      <div class="composer-card relative flex w-full flex-col border border-gray-200 bg-white px-3 pb-1.5 pt-2.5 rounded-2xl shadow-xl focus-within:ring-1 focus-within:ring-black/5 focus-within:border-gray-300 transition-all duration-300">
        <div
          v-if="skillPickerOpen"
          ref="skillPickerRef"
          class="absolute bottom-[calc(100%+10px)] left-3 z-30 w-[420px] max-w-[calc(100vw-40px)] overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl shadow-slate-900/12"
        >
          <div class="flex items-center justify-between border-b border-slate-100 px-3 py-2">
            <div class="text-sm font-semibold text-slate-800">{{ locale === 'zh' ? '选择 Skill' : 'Select Skill' }}</div>
            <div class="flex rounded-full bg-slate-100 p-0.5">
              <button
                v-for="option in skillScopeOptions"
                :key="option.key"
                type="button"
                class="rounded-full px-2.5 py-1 text-xs font-medium transition"
                :class="skillPickerScope === option.key ? 'bg-white text-blue-700 shadow-sm' : 'text-slate-500 hover:text-slate-700'"
                @click="setSkillPickerScope(option.key)"
              >
                {{ option.label }}
              </button>
            </div>
          </div>
          <div
            class="max-h-[300px] overflow-y-auto py-1"
            role="listbox"
            :aria-label="locale === 'zh' ? 'Skill 列表' : 'Skill list'"
            @scroll="onSkillPickerScroll"
          >
            <div v-if="skillPickerLoading" class="px-4 py-8 text-center text-sm text-slate-400">
              {{ locale === 'zh' ? '加载中...' : 'Loading...' }}
            </div>
            <template v-else>
              <button
                v-for="(skill, index) in skillPickerItems"
                :key="skill.id"
                :id="`skill-picker-option-${index}`"
                :data-skill-index="index"
                type="button"
                role="option"
                :aria-selected="activeSkillIndex === index"
                class="flex w-full gap-3 px-3 py-2.5 text-left transition"
                :class="activeSkillIndex === index ? 'bg-blue-50/80' : 'hover:bg-slate-50'"
                @mouseenter="activeSkillIndex = index"
                @click="selectSkill(skill)"
              >
                <span class="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg"
                  :class="skill.type === 'workflow' ? 'bg-blue-100 text-blue-600' : 'bg-violet-100 text-violet-600'"
                >
                  <svg v-if="skill.type === 'workflow'" class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                    <path d="M6 3v6"></path>
                    <path d="M18 15v6"></path>
                    <path d="M6 9a3 3 0 1 0 0 6h12a3 3 0 1 0 0-6H6z"></path>
                  </svg>
                  <svg v-else class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                    <path d="M4 19.5V5a2 2 0 0 1 2-2h8l6 6v10.5a1.5 1.5 0 0 1-1.5 1.5H5.5A1.5 1.5 0 0 1 4 19.5z"></path>
                    <path d="M14 3v6h6"></path>
                    <path d="M8 13h8"></path>
                    <path d="M8 17h5"></path>
                  </svg>
                </span>
                <span class="min-w-0 flex-1">
                  <span class="flex min-w-0 items-center gap-2">
                    <span class="truncate text-sm font-semibold text-slate-900">{{ skill.name }}</span>
                    <span class="shrink-0 rounded-full bg-slate-100 px-1.5 py-0.5 text-[11px] font-medium text-slate-500">{{ skillSourceLabel(skill.sourceScope) }}</span>
                    <span class="shrink-0 rounded-full bg-slate-100 px-1.5 py-0.5 text-[11px] font-medium text-slate-500">{{ skillTypeLabel(skill.type) }}</span>
                  </span>
                  <span class="mt-0.5 block truncate text-xs text-slate-500">{{ skill.description || skill.scenario || (locale === 'zh' ? '暂无描述' : 'No description') }}</span>
                </span>
              </button>
              <div v-if="skillPickerItems.length === 0" class="px-4 py-8 text-center text-sm text-slate-400">
                {{ locale === 'zh' ? '没有找到可用 Skill' : 'No available skills' }}
              </div>
              <button
                v-if="skillPickerHasMore"
                type="button"
                class="mx-3 my-2 flex w-[calc(100%-24px)] items-center justify-center rounded-xl border border-slate-200 px-3 py-2 text-sm font-medium text-slate-600 transition hover:bg-slate-50 disabled:cursor-wait disabled:opacity-60"
                :disabled="skillPickerLoadingMore"
                @click="loadSelectableSkills(false)"
              >
                {{ skillPickerLoadingMore ? (locale === 'zh' ? '加载中...' : 'Loading...') : (locale === 'zh' ? '加载更多' : 'Load more') }}
              </button>
            </template>
          </div>
        </div>
        <textarea
          ref="composerInputRef"
          v-model="userInput"
          @input="handleComposerInput"
          @keydown="onComposerKeydown"
          @paste="onComposerPaste"
          @compositionstart="onComposerCompositionStart"
          @compositionend="onComposerCompositionEnd"
          rows="1"
          :placeholder="t('chat.composer.placeholder')"
          :disabled="running"
          :aria-expanded="skillPickerOpen"
          aria-haspopup="listbox"
          :aria-activedescendant="skillPickerOpen && activeSkillIndex >= 0 ? `skill-picker-option-${activeSkillIndex}` : undefined"
          class="w-full max-h-[200px] resize-none border-0 bg-transparent px-1 py-1.5 focus:ring-0 outline-none text-slate-800 placeholder:text-slate-400 leading-6"
          style="min-height: 36px;"
        ></textarea>
        <div class="composer-footer flex min-h-8 items-center gap-1.5">
        <div ref="attachmentMenuRef" class="relative">
          <button
            class="flex h-7 w-7 items-center justify-center rounded-md text-gray-500 transition-colors hover:bg-gray-100 hover:text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-100"
            :disabled="running"
            :aria-label="locale === 'zh' ? '添加附件' : 'Add attachment'"
            @click.stop="toggleAttachmentMenu"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="12" y1="5" x2="12" y2="19"></line>
              <line x1="5" y1="12" x2="19" y2="12"></line>
            </svg>
          </button>
          <div
            v-if="attachmentMenuOpen"
            class="absolute bottom-9 left-0 min-w-[220px] overflow-hidden rounded-xl border border-gray-200 bg-white py-1 shadow-lg"
          >
            <button
              class="flex w-full items-center gap-2 px-3 py-2 text-sm text-slate-700 hover:bg-slate-50"
              @click="selectImageAttachment"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
                <circle cx="8.5" cy="8.5" r="1.5"></circle>
                <polyline points="21 15 16 10 5 21"></polyline>
              </svg>
              {{ t('chat.upload_image') }}
            </button>
            <button
              class="flex w-full items-center gap-2 px-3 py-2 text-sm text-slate-700 hover:bg-slate-50"
              @click="selectDocumentAttachment"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                <polyline points="14 2 14 8 20 8"></polyline>
                <line x1="16" y1="13" x2="8" y2="13"></line>
                <line x1="16" y1="17" x2="8" y2="17"></line>
                <line x1="10" y1="9" x2="8" y2="9"></line>
              </svg>
              {{ t('chat.upload_document') }}
            </button>
            <button
              v-if="allowKnowledge !== false"
              class="flex w-full items-center gap-2 whitespace-nowrap px-3 py-2 text-sm hover:bg-slate-50"
              :class="knowledgeQaEnabled ? 'bg-blue-50 text-blue-700' : 'text-slate-700'"
              :aria-pressed="knowledgeQaEnabled"
              @click="toggleKnowledgeQa"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4z"></path>
                <path d="M9 9a3 3 0 0 1 6 0c0 2-3 2-3 4"></path>
                <path d="M12 17h.01"></path>
              </svg>
              {{ t('chat.knowledge_qa') }}
            </button>
          </div>
        </div>
        <slot name="model-actions" />
        <div class="flex-1"></div>
        <div ref="modelSelectorRef" class="relative min-w-0">
          <button
            type="button"
            class="group flex h-7 max-w-[240px] items-center gap-1 rounded-md px-1.5 text-[11px] font-medium text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-100"
            :class="running ? 'cursor-not-allowed opacity-70' : 'cursor-pointer'"
            :title="modelLoadError || modelSelectorLabel"
            :disabled="running"
            @click="toggleModelDropdown"
          >
            <span class="truncate text-left">{{ modelSelectorLabel }}</span>
            <svg class="h-3 w-3 shrink-0 text-slate-400" viewBox="0 0 20 20" fill="none" aria-hidden="true">
              <path d="M6 12l4-4 4 4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
          </button>
          <div
            v-if="modelDropdownOpen"
            class="absolute bottom-9 right-0 z-40 w-[320px] max-w-[calc(100vw-32px)] overflow-hidden rounded-2xl border border-slate-200 bg-white py-1.5 shadow-xl shadow-slate-900/10"
          >
            <button v-if="chatModels.length === 0" type="button" class="flex w-full items-center gap-3 px-3 py-2.5 text-left" @click="selectChatModel('')">
              <span class="min-w-0 flex-1"><span class="block truncate text-sm font-medium text-slate-800">{{ modelSelectorLabel }}</span></span>
            </button>
            <button
              v-for="model in chatModels"
              :key="model.id"
              type="button"
              class="flex w-full items-center gap-3 px-3 py-2.5 text-left transition-colors hover:bg-slate-50"
              :class="model.id === selectedModelId ? 'bg-blue-50/80' : ''"
              @click="selectChatModel(model.id)"
            >
              <span class="min-w-0 flex-1">
                <span class="flex min-w-0 items-center gap-2">
                  <span class="truncate text-sm font-medium text-slate-900">{{ model.displayName || model.modelName }}</span>
                </span>
                <span class="block truncate text-xs text-slate-500">{{ model.providerName }} · {{ model.modelName }}</span>
              </span>
              <svg v-if="model.id === selectedModelId" class="h-4 w-4 shrink-0 text-blue-600" viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="M5 10.5l3 3L15 6.5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" /></svg>
            </button>
          </div>
        </div>
        <div class="relative flex h-8 w-8 items-center justify-center">
          <svg v-if="running" class="ring-svg" viewBox="0 0 44 44">
            <rect x="4" y="4" width="36" height="36" rx="10" ry="10" fill="none" stroke="rgba(59,130,246,0.2)" stroke-width="2.5"/>
            <rect
              class="ring-dash"
              x="4"
              y="4"
              width="36"
              height="36"
              rx="10"
              ry="10"
              fill="none"
              stroke="rgba(59,130,246,0.9)"
              stroke-width="2.5"
              stroke-linecap="round"
              stroke-linejoin="round"
              pathLength="100"
              stroke-dasharray="18 90"
            />
          </svg>
          <button
            @click="sendMessage"
            :disabled="stopping || (!userInput.trim() && pendingImages.length === 0 && pendingDocuments.length === 0 && !selectedSkill && !running)"
            :title="stopping ? (locale === 'zh' ? '正在停止…' : 'Stopping…') : undefined"
            class="relative z-10 flex h-8 w-8 items-center justify-center rounded-lg text-white transition-all duration-200 ease-in-out transform active:scale-95"
            :class="(userInput.trim() || pendingImages.length > 0 || pendingDocuments.length > 0 || selectedSkill || running) ? 'bg-blue-600 hover:bg-blue-700 shadow-md shadow-blue-200' : 'bg-gray-200 cursor-not-allowed'"
          >
            <svg v-if="running && !stopping" width="16" height="16" viewBox="0 0 24 24" fill="currentColor" xmlns="http://www.w3.org/2000/svg">
              <rect x="6" y="6" width="12" height="12" rx="2" />
            </svg>
            <svg v-else-if="stopping" class="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="3" opacity="0.3" />
              <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" stroke-width="3" stroke-linecap="round" />
            </svg>
            <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" class="text-white" xmlns="http://www.w3.org/2000/svg"><path d="M7 11L12 6L17 11M12 18V7" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
          </button>
        </div>
        </div>
      </div>
      <slot name="prompt-guide" />
    </div>
  </div>
</template>

<style scoped>
.composer-context-slot:empty {
  display: none;
}

.composer-context-slot:not(:empty) + .composer-card {
  border-top-left-radius: 0;
  border-top-right-radius: 0;
}

.ring-svg {
  position: absolute;
  inset: -2px;
  width: 36px;
  height: 36px;
  pointer-events: none;
}

.ring-dash {
  animation: dashLoop 1.2s linear infinite;
}

@keyframes dashLoop {
  to {
    stroke-dashoffset: -100;
  }
}

@media (prefers-reduced-motion: reduce) {
  .ring-dash {
    animation: none;
  }
}
</style>
