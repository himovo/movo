<script setup lang="ts">
import KnowledgeMentionPicker from './knowledge/KnowledgeMentionPicker.vue'
import KnowledgeReferenceChips from './knowledge/KnowledgeReferenceChips.vue'
import { useKnowledgeMentions } from './knowledge/useKnowledgeMentions'
import type { KnowledgeReference } from '../../api/knowledgeReferences'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { ChatModelOption } from '../../api/models'
import { useComposerSkillPicker } from './useComposerSkillPicker'
import { fetchKnowledgeSourceSummary, type KnowledgeSourceSummary } from '../../api/knowledgeSource'
import { t, useLocale } from '../../composables/i18n'
import type { PendingDocument } from './types'
import { useComposerAttachments } from './useComposerAttachments'
import { NModal, useMessage } from 'naive-ui'
import SkillFeedbackPanel from '../skills/SkillFeedbackPanel.vue'
import ComposerActionButton from './ComposerActionButton.vue'
import ComposerAttachmentPreviews from './ComposerAttachmentPreviews.vue'
import ComposerSkillPicker from './ComposerSkillPicker.vue'
import ComposerModelPicker from './ComposerModelPicker.vue'
import ComposerAttachmentMenu from './ComposerAttachmentMenu.vue'
import ComposerSelections from './ComposerSelections.vue'
import { useComposerAutofocus } from '../../composables/useComposerAutofocus'

const props = defineProps<{
  running: boolean
  blocked?: boolean
  stopping?: boolean
  active: boolean
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
  (e: 'send', payload: { text: string; images: File[]; documents: PendingDocument[]; knowledgeQaEnabled: boolean; knowledgeReferences?: KnowledgeReference[]; selectedSkillId?: string; modelId?: string; onRejected?: () => void }): void
  (e: 'stop'): void
  (e: 'select-model', modelId: string): void
  (e: 'image-preview', payload: { src: string; alt: string }): void
  (e: 'document-preview', document: PendingDocument): void
  (e: 'knowledge-source', source: KnowledgeSourceSummary): void
}>()

const { locale } = useLocale()
const message = useMessage()

const userInput = ref('')
const composerInputRef = ref<HTMLTextAreaElement | null>(null)
const autofocusEnabled = computed(() => props.active && !props.running && !props.blocked)
useComposerAutofocus(composerInputRef, autofocusEnabled)
const attachmentMenuOpen = ref(false)
const attachmentMenuRef = ref<InstanceType<typeof ComposerAttachmentMenu> | null>(null)
const knowledgeQaEnabled = ref(false)
const knowledgeSource = ref<KnowledgeSourceSummary>({ mode: 'movo', displayName: '' })
const knowledgeLabel = computed(() => knowledgeSource.value.mode === 'external'
  ? t('chat.external_knowledge_name', { name: knowledgeSource.value.displayName })
  : t('chat.knowledge_qa'))
async function refreshKnowledgeSource() {
  if (!props.userId) return
  try {
    const source = await fetchKnowledgeSourceSummary()
    if (!props.userId) return
    knowledgeSource.value = source
    emit('knowledge-source', source)
  } catch { /* retain the last known source label during a transient request failure */ }
}
const modelDropdownOpen = ref(false)
const modelSelectorRef = ref<InstanceType<typeof ComposerModelPicker> | null>(null)
const organizationFeedbackVisible = ref(false)
const skillPickerRef = ref<InstanceType<typeof ComposerSkillPicker> | null>(null)
const isComposingText = ref(false)
const {
  open: skillPickerOpen, loading: skillPickerLoading, loadingMore: skillPickerLoadingMore,
  scope: skillPickerScope, hasMore: skillPickerHasMore, items: skillPickerItems,
  activeIndex: activeSkillIndex, selectedSkill, close: closeSkillPicker,
  openPicker: openSkillPicker, handleInput: handleComposerInput,
  load: loadSelectableSkills, setScope: setSkillPickerScope, select: selectSkill,
  moveActive: moveActiveSkill, selectActive: selectActiveSkill,
  onScroll: onSkillPickerScroll, selectShortcutSkill,
} = useComposerSkillPicker({
  userId: () => props.userId, mainId: () => props.mainId,
  allowSkills: () => props.allowSkills,
  allowPluginEntries: () => true,
  running: () => props.running,
  input: userInput, inputElement: composerInputRef,
  pickerElement: () => skillPickerRef.value?.root,
  closeAttachmentMenu, resizeInput: autoResizeComposerInput,
})
const mentions = useKnowledgeMentions({
  input: userInput, element: composerInputRef, userId: () => props.userId, mainId: () => props.mainId,
  allowed: () => props.allowKnowledge !== false && !props.running && !props.blocked,
  onOpen: () => { closeSkillPicker(); closeAttachmentMenu() }, resize: autoResizeComposerInput, onLimit: () => message.warning(t('knowledgeMention.limit')),
})
function onComposerInput() {
  handleComposerInput()
  if (!isComposingText.value) mentions.handleInput()
}
const {
  pendingImages, pendingDocuments, imageInputRef, documentInputRef,
  revokePendingImage, removePendingImage, removePendingDocument,
  onImageSelected, onDocumentSelected, onComposerPaste,
} = useComposerAttachments({
  running: () => props.running,
  onUnsupportedFiles: names => message.error(t('composer.unsupportedFiles', {
    names: names.join(locale.value === 'zh' ? '、' : ', '),
  })),
  onImagePasted: () => {
    closeSkillPicker()
    closeAttachmentMenu()
  },
  focusInput: () => composerInputRef.value?.focus(),
})

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

function closeAttachmentMenu() {
  attachmentMenuOpen.value = false
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
  void refreshKnowledgeSource()
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
  const attachmentRoot = attachmentMenuRef.value?.root
  if (attachmentMenuOpen.value && attachmentRoot && !attachmentRoot.contains(target)) {
    closeAttachmentMenu()
  }
  const modelRoot = modelSelectorRef.value?.root
  if (modelDropdownOpen.value && modelRoot && !modelRoot.contains(target)) {
    modelDropdownOpen.value = false
  }
  const pickerRoot = skillPickerRef.value?.root
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

function onComposerCompositionStart() {
  isComposingText.value = true
}

function onComposerCompositionEnd() {
  isComposingText.value = false
  mentions.handleInput()
}

function isImeCompositionKey(event: KeyboardEvent) {
  return isComposingText.value || event.isComposing || event.key === 'Process' || event.keyCode === 229
}

function clearSelectedSkill() {
  selectedSkill.value = null
}

function onComposerKeydown(event: KeyboardEvent) {
  if (isImeCompositionKey(event)) {
    return
  }
  if (mentions.keydown(event)) return
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
  if (props.blocked) return
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

  const rawText = userInput.value
  const knowledgeRefs = [...mentions.selected.value]
  mentions.close()
  mentions.selected.value = []
  const imageFiles = pendingImages.value.map((item) => item.file)
  const documentFiles = pendingDocuments.value.map((item) => ({ ...item }))
  const skill = selectedSkill.value
  const text = skill?.entryKind === 'command'
    ? `/${skill.name}${rawText.trim() ? ` ${rawText.trim()}` : ''}`
    : rawText
  const knowledgeEnabled = knowledgeQaEnabled.value
  closeAttachmentMenu()
  userInput.value = ''
  await nextTick()
  resetComposerInputHeight()
  for (const item of pendingImages.value) {
    revokePendingImage(item.previewUrl)
  }
  pendingImages.value = []
  pendingDocuments.value = []
  selectedSkill.value = null
  emit('send', {
    text,
    knowledgeReferences: knowledgeRefs,
    images: imageFiles,
    documents: documentFiles,
    knowledgeQaEnabled: knowledgeQaEnabled.value,
    selectedSkillId: skill?.id || undefined,
    modelId: props.selectedModelId || undefined,
    onRejected: () => {
      userInput.value = userInput.value ? `${rawText}\n\n${userInput.value}` : rawText
      pendingImages.value.push(...imageFiles.map((file) => ({ file, previewUrl: URL.createObjectURL(file) })))
      pendingDocuments.value.push(...documentFiles)
      mentions.selected.value = [...knowledgeRefs, ...mentions.selected.value]
      if (!selectedSkill.value) selectedSkill.value = skill
      knowledgeQaEnabled.value = knowledgeEnabled
      void nextTick(() => { autoResizeComposerInput(); composerInputRef.value?.focus() })
    },
  })
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
  selectShortcutSkill,
})

onMounted(() => {
  document.addEventListener('pointerdown', onGlobalPointerDown)
  void refreshKnowledgeSource()
})

onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', onGlobalPointerDown)
})

watch(() => props.userId, () => {
  knowledgeSource.value = { mode: 'movo', displayName: '' }
  void refreshKnowledgeSource()
})

watch(() => props.allowKnowledge, (allowed) => {
  if (allowed === false) {
    knowledgeQaEnabled.value = false
    for (const item of [...mentions.selected.value]) mentions.remove(item)
    mentions.close()
  }
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
      <ComposerAttachmentPreviews
        :images="pendingImages"
        :documents="pendingDocuments"
        :doc-icon="docIcon"
        @image-preview="openPendingImagePreview"
        @document-preview="emit('document-preview', $event)"
        @remove-image="removePendingImage"
        @remove-document="removePendingDocument"
      />
      <KnowledgeReferenceChips :items="mentions.selected.value" removable @remove="mentions.remove" />
      <ComposerSelections
        :knowledge-qa-enabled="knowledgeQaEnabled"
        :knowledge-label="knowledgeLabel"
        :selected-skill="selectedSkill"
        @disable-knowledge="disableKnowledgeQa"
        @clear-skill="clearSelectedSkill"
        @show-feedback="organizationFeedbackVisible = true"
      />
      <div class="composer-context-slot"><slot name="context" /></div>
      <div class="composer-card relative flex w-full flex-col border border-gray-200 bg-white px-3 pb-1.5 pt-2.5 rounded-2xl shadow-xl focus-within:ring-1 focus-within:ring-black/5 focus-within:border-gray-300 transition-all duration-300">
        <ComposerSkillPicker
          v-if="skillPickerOpen"
          ref="skillPickerRef"
          :items="skillPickerItems"
          :scope="skillPickerScope"
          :loading="skillPickerLoading"
          :loading-more="skillPickerLoadingMore"
          :has-more="skillPickerHasMore"
          :active-index="activeSkillIndex"
          @scope="setSkillPickerScope"
          @select="selectSkill"
          @active-index="activeSkillIndex = $event"
          @scroll="onSkillPickerScroll"
          @load-more="loadSelectableSkills(false)"
        />
        <div v-if="mentions.open.value" :ref="element => { mentions.root.value = element as HTMLElement | null }" class="knowledge-picker-root">
          <KnowledgeMentionPicker :items="mentions.items.value" :scope="mentions.scope.value" :loading="mentions.loading.value" :failed="mentions.failed.value" :active="mentions.active.value" :has-more="mentions.cursor.value !== null" :trail="mentions.trail.value" @scope="mentions.setScope" @select="mentions.select" @browse="mentions.browse" @back="mentions.back" @more="mentions.load(true)" @retry="mentions.load()" @close="mentions.close" />
        </div>
        <textarea
          ref="composerInputRef"
          data-chat-composer-input="true"
          v-model="userInput"
          @input="onComposerInput"
          @keydown="onComposerKeydown"
          @paste="onComposerPaste"
          @compositionstart="onComposerCompositionStart"
          @compositionend="onComposerCompositionEnd"
          rows="1"
          :placeholder="t('chat.composer.placeholder')"
          :disabled="running || blocked"
          :aria-expanded="skillPickerOpen || mentions.open.value"
          aria-haspopup="listbox"
          :aria-activedescendant="skillPickerOpen && activeSkillIndex >= 0 ? `skill-picker-option-${activeSkillIndex}` : undefined"
          class="w-full max-h-[200px] resize-none border-0 bg-transparent px-1 py-1.5 focus:ring-0 outline-none text-slate-800 placeholder:text-slate-400 leading-6"
          style="min-height: 36px;"
        ></textarea>
        <div class="composer-footer flex min-h-8 items-center gap-1.5">
        <ComposerAttachmentMenu
          ref="attachmentMenuRef"
          :open="attachmentMenuOpen"
          :running="running"
          :blocked="blocked"
          :allow-knowledge="allowKnowledge"
          :knowledge-qa-enabled="knowledgeQaEnabled"
          :knowledge-label="knowledgeLabel"
          @toggle="toggleAttachmentMenu"
          @image="selectImageAttachment"
          @document="selectDocumentAttachment"
          @knowledge="toggleKnowledgeQa"
        />
        <slot name="model-actions" />
        <div class="flex-1"></div>
        <ComposerModelPicker
          ref="modelSelectorRef"
          :models="chatModels"
          :selected-model-id="selectedModelId"
          :model-selector-label="modelSelectorLabel"
          :model-load-error="modelLoadError"
          :running="running"
          :blocked="blocked"
          :open="modelDropdownOpen"
          @toggle="toggleModelDropdown"
          @select="selectChatModel"
        />
        <ComposerActionButton
          :running="running"
          :stopping="stopping"
          :disabled="blocked || stopping || (!userInput.trim() && pendingImages.length === 0 && pendingDocuments.length === 0 && !selectedSkill && !running)"
          :locale="locale"
          @activate="sendMessage"
        />
        </div>
      </div>
      <slot name="prompt-guide" />
    </div>
  </div>
  <n-modal v-model:show="organizationFeedbackVisible" preset="card" :title="selectedSkill?.name || 'Skill'" style="width:620px">
    <SkillFeedbackPanel v-if="selectedSkill?.sourceScope === 'organization'" resource-type="organization_skill" :resource-id="selectedSkill.id" />
  </n-modal>
</template>

<style scoped>
.composer-context-slot:empty {
  display: none;
}

.composer-context-slot:not(:empty) + .composer-card {
  border-top-left-radius: 0;
  border-top-right-radius: 0;
}

</style>
