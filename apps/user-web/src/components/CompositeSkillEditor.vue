<script setup lang="ts">
// Editor for `skill_type === 'composite_task'` skills.
// Each step is a "where + what" pair; the backend parses the YAML
// frontmatter this component emits into subtasks for the planner.
import { computed, onMounted, ref, watch } from 'vue'
import {
  NButton,
  NCard,
  NForm,
  NFormItem,
  NInput,
  NInputGroup,
  NModal,
  NSelect,
  NSpace,
  NSwitch,
  NTag,
} from 'naive-ui'
import { t, useLocale } from '../composables/i18n'
import {
  type SiteProfile,
  type SiteProfileInput,
  createSiteProfile,
  listSiteProfiles,
} from '../api/siteProfiles'
import { generateSkill, updateSkill } from '../api/skills'
import {
  type CompositeSkillDraft,
  type CompositeStep,
  type Locator,
  decodeCompositeSkill,
  encodeCompositeSkill,
} from '../api/compositeSkill'
import LocatorEditor from './LocatorEditor.vue'
import RecordingPanel from './RecordingPanel.vue'

const props = defineProps<{
  skill: any | null     // null → create mode
  userId: string | null
}>()

const emit = defineEmits(['back', 'saved', 'remove'])
const { locale } = useLocale()
const name = ref<string>('')
const description = ref<string>('')
const isActive = ref<boolean>(true)
const visibility = ref<'private' | 'team' | 'global'>('private')
const triggers = ref<string[]>([])
const newTrigger = ref<string>('')
const steps = ref<CompositeStep[]>([])
const sites = ref<SiteProfile[]>([])
const saving = ref(false)
const showSiteModal = ref(false)
const targetStepIndex = ref<number>(-1)
const newSite = ref<SiteProfileInput>({
  name: '', domain: '', entry_url: '', auth_method: '', hints: '', visibility: 'private',
})

const visibilityOptions = computed(() => [
  { label: t('composite.visibility.private'), value: 'private' },
  { label: t('composite.visibility.team'), value: 'team' },
  { label: t('composite.visibility.global'), value: 'global' },
])

const siteOptions = computed(() => sites.value.map(s => ({
  label: s.name + (s.domain ? ` · ${s.domain}` : ''),
  value: s.id,
})))

function hydrateFromSkill() {
  const s = props.skill
  if (!s) {
    name.value = ''
    description.value = ''
    triggers.value = []
    steps.value = [{ instruction: '' }]
    isActive.value = true
    visibility.value = 'private'
    return
  }
  name.value = s.name || ''
  description.value = s.description || ''
  isActive.value = s.is_active !== false
  visibility.value = (s.visibility as any) || 'private'
  const decoded: CompositeSkillDraft = decodeCompositeSkill(s.skill_markdown || '')
  triggers.value = decoded.triggers
  steps.value = decoded.steps.length ? decoded.steps : [{ instruction: '' }]
}

async function loadSites() {
  if (!props.userId) return
  try {
    sites.value = await listSiteProfiles(props.userId)
  } catch (e) {
    console.error('load sites failed', e)
  }
}

onMounted(async () => {
  hydrateFromSkill()
  await loadSites()
})

watch(() => props.skill, hydrateFromSkill)

// ---- Triggers
function addTrigger() {
  const v = newTrigger.value.trim()
  if (!v) return
  if (!triggers.value.includes(v)) triggers.value.push(v)
  newTrigger.value = ''
}
function removeTrigger(tr: string) {
  triggers.value = triggers.value.filter(x => x !== tr)
}

// ---- Locator helpers (Line A)
// Step stores locators as a per-op bag ({ primary, update, delete, ... }).
// The form currently edits the ``primary`` slot only — per-op locators
// are reserved for advanced users / recorder output.
function stepPrimaryLocator(step: CompositeStep): Locator | undefined {
  return step.locators?.primary
}
function setStepPrimaryLocator(step: CompositeStep, loc: Locator | undefined) {
  if (!loc || Object.keys(loc).length === 0) {
    if (step.locators) { delete step.locators.primary; if (!Object.keys(step.locators).length) delete step.locators }
    return
  }
  step.locators = { ...(step.locators || {}), primary: loc }
}

// ---- Recording (Line B)
const showRecording = ref(false)
function openRecording() { showRecording.value = true }
function onRecordingDone(newSteps: CompositeStep[]) {
  if (!newSteps?.length) { showRecording.value = false; return }
  // Append recorded steps to the existing list. Blank trailing step
  // (the default one from hydrateFromSkill) is replaced if empty.
  if (steps.value.length === 1 && !steps.value[0].instruction.trim()) {
    steps.value = [...newSteps]
  } else {
    steps.value = [...steps.value, ...newSteps]
  }
  showRecording.value = false
}

// ---- Steps
function addStep() { steps.value.push({ instruction: '' }) }
function removeStep(i: number) {
  if (steps.value.length <= 1) { steps.value = [{ instruction: '' }]; return }
  steps.value.splice(i, 1)
}
function moveStep(i: number, delta: -1 | 1) {
  const j = i + delta
  if (j < 0 || j >= steps.value.length) return
  const tmp = steps.value[i]
  steps.value[i] = steps.value[j]
  steps.value[j] = tmp
}
// Drag-reorder via native HTML5 (keeps bundle size unchanged)
const dragFromIndex = ref<number>(-1)
function onDragStart(i: number, ev: DragEvent) {
  dragFromIndex.value = i
  ev.dataTransfer?.setData('text/plain', String(i))
  if (ev.dataTransfer) ev.dataTransfer.effectAllowed = 'move'
}
function onDragOver(ev: DragEvent) {
  ev.preventDefault()
  if (ev.dataTransfer) ev.dataTransfer.dropEffect = 'move'
}
function onDrop(toIndex: number, ev: DragEvent) {
  ev.preventDefault()
  const from = dragFromIndex.value
  if (from < 0 || from === toIndex) return
  const moved = steps.value.splice(from, 1)[0]
  steps.value.splice(toIndex, 0, moved)
  dragFromIndex.value = -1
}

// ---- Site creation (inline)
function openSiteModal(forStepIndex: number) {
  targetStepIndex.value = forStepIndex
  newSite.value = { name: '', domain: '', entry_url: '', auth_method: '', hints: '', visibility: 'private' }
  showSiteModal.value = true
}

async function saveNewSite() {
  if (!props.userId || !newSite.value.name.trim()) return
  try {
    const created = await createSiteProfile(props.userId, newSite.value)
    sites.value.unshift(created)
    if (targetStepIndex.value >= 0 && steps.value[targetStepIndex.value]) {
      steps.value[targetStepIndex.value].site_profile_id = created.id
    }
    showSiteModal.value = false
  } catch (e) {
    console.error('create site failed', e)
    alert(t('composite.site.create_failed'))
  }
}

// ---- Persist
function collectDraft(): CompositeSkillDraft {
  return {
    triggers: [...triggers.value].map(x => x.trim()).filter(Boolean),
    steps: steps.value
      .map(s => ({ ...s, instruction: (s.instruction || '').trim() }))
      .filter(s => s.instruction.length > 0),
  }
}

async function save() {
  if (!props.userId) { alert(t('skills.login_first')); return }
  const trimmedName = name.value.trim()
  if (!trimmedName) { alert(t('composite.validate.name_required')); return }
  const draft = collectDraft()
  if (!draft.steps.length) { alert(t('composite.validate.steps_required')); return }
  const skillMarkdown = encodeCompositeSkill(draft, {
    name: trimmedName,
    description: description.value.trim(),
  })
  saving.value = true
  try {
    if (props.skill?.id) {
      const updated = await updateSkill(props.skill.id, {
        user_id: props.userId,
        name: trimmedName,
        description: description.value.trim(),
        skill_type: 'composite_task',
        visibility: visibility.value,
        skill_markdown: skillMarkdown,
        is_active: isActive.value,
      })
      emit('saved', updated)
    } else {
      const created = await generateSkill({
        user_id: props.userId,
        name: trimmedName,
        description: description.value.trim(),
        summary: description.value.trim(),
        category: 'Browser Automation',
        skill_type: 'composite_task',
        tags: ['composite_task'],
        visibility: visibility.value,
        formats: ['markdown'],
        notes: '',
        sources: [],
        resources: {},
        input_profile: {},
        contract_json: {},
        skill_markdown: skillMarkdown,
        advanced: {},
        is_active: isActive.value,
      } as any)
      emit('saved', created)
    }
  } catch (e) {
    console.error('save composite skill failed', e)
    alert(t('composite.validate.save_failed'))
  } finally {
    saving.value = false
  }
}

function requestRemove() {
  if (!props.skill?.id) { emit('back'); return }
  if (!confirm(t('composite.validate.confirm_remove'))) return
  emit('remove', props.skill)
}
</script>

<template>
  <div class="flex flex-col h-full w-full bg-[#f8fafc]">
    <!-- Header -->
    <header class="h-16 border-b border-gray-200 bg-white/80 backdrop-blur-sm flex items-center px-8 justify-between shrink-0 sticky top-0 z-10">
      <div class="flex items-center gap-3 min-w-0">
        <n-button size="small" @click="emit('back')">{{ t('composite.back') }}</n-button>
        <div class="min-w-0">
          <h1 class="text-lg font-semibold text-gray-900 leading-none truncate">
            {{ props.skill?.id ? t('composite.edit_title') : t('composite.new_title') }}
          </h1>
          <p class="text-xs text-gray-500 font-medium mt-1">{{ t('composite.subtitle') }}</p>
        </div>
      </div>
      <n-space :size="8">
        <n-button v-if="props.skill?.id" type="error" ghost size="small" @click="requestRemove">
          {{ t('composite.remove') }}
        </n-button>
        <n-button type="primary" :loading="saving" :disabled="saving" @click="save">
          {{ t('composite.save') }}
        </n-button>
      </n-space>
    </header>

    <!-- Body -->
    <div class="flex-1 overflow-y-auto p-6 lg:p-8 custom-scrollbar">
      <div class="max-w-[820px] mx-auto">
        <n-form
          label-placement="left"
          label-align="right"
          :label-width="100"
          :show-require-mark="true"
          :model="{ name, description }"
        >
          <!-- 1. Basic info -->
          <n-card :title="t('composite.section.basic')" :bordered="false" class="!rounded-xl mb-6" size="small">
            <n-form-item :label="t('composite.field.name')" required :show-feedback="false" class="mb-3">
              <n-input v-model:value="name" :placeholder="t('composite.field.name_ph')" />
            </n-form-item>
            <n-form-item :label="t('composite.field.description')" required :show-feedback="false" class="mb-3">
              <n-input
                v-model:value="description"
                type="textarea"
                :placeholder="t('composite.field.description_ph')"
                :autosize="{ minRows: 2, maxRows: 5 }"
              />
            </n-form-item>

            <n-form-item :label="t('composite.field.triggers')" :show-feedback="false" class="mb-3">
              <div class="w-full">
                <n-space :size="6" class="mb-2" v-if="triggers.length">
                  <n-tag
                    v-for="tr in triggers"
                    :key="tr"
                    closable
                    size="small"
                    type="info"
                    :bordered="false"
                    round
                    @close="removeTrigger(tr)"
                  >
                    {{ tr }}
                  </n-tag>
                </n-space>
                <n-input-group>
                  <n-input
                    v-model:value="newTrigger"
                    size="small"
                    :placeholder="triggers.length ? t('composite.field.triggers_ph') : t('composite.field.triggers_empty')"
                    @keyup.enter="addTrigger"
                  />
                  <n-button size="small" @click="addTrigger">
                    {{ t('composite.field.triggers_add') }}
                  </n-button>
                </n-input-group>
              </div>
            </n-form-item>

            <n-form-item :label="t('composite.field.visibility')" :show-feedback="false" class="mb-3">
              <div class="flex items-center gap-8">
                <n-select
                  v-model:value="visibility"
                  :options="visibilityOptions"
                  size="small"
                  style="width: 140px"
                />
                <div class="flex items-center gap-2">
                  <span class="text-xs font-medium text-gray-500">{{ t('composite.field.is_active') }}</span>
                  <n-switch v-model:value="isActive" size="small" />
                </div>
              </div>
            </n-form-item>
          </n-card>

          <!-- 2. Steps -->
          <n-card :bordered="false" class="!rounded-xl" size="small">
            <template #header>
              <div class="flex items-center justify-between gap-3">
                <span>{{ t('composite.section.steps') }}</span>
                <div class="flex items-center gap-3">
                  <span class="text-xs font-normal text-gray-400">{{ t('composite.section.steps_hint') }}</span>
                  <n-button size="small" type="primary" ghost @click="openRecording">
                    ● {{ locale === 'zh' ? '录制' : 'Record' }}
                  </n-button>
                </div>
              </div>
            </template>

            <div class="space-y-3">
              <div
                v-for="(step, i) in steps"
                :key="i"
                class="border border-gray-200 rounded-xl p-4 bg-white hover:border-blue-200 transition-colors"
                @dragover="onDragOver"
                @drop="(e) => onDrop(i, e)"
              >
                <!-- Step header: drag handle + label + inline action icons -->
                <div class="flex items-center justify-between mb-3">
                  <div class="flex items-center gap-2">
                    <span
                      class="cursor-move select-none text-gray-400 hover:text-gray-600 text-base leading-none"
                      draggable="true"
                      @dragstart="(e) => onDragStart(i, e)"
                      :title="t('composite.step.drag_hint')"
                    >⋮⋮</span>
                    <span class="text-xs font-bold text-gray-500">
                      {{ t('composite.step.label') }} #{{ i + 1 }}
                    </span>
                  </div>
                  <n-space :size="4">
                    <n-button
                      quaternary
                      circle
                      size="tiny"
                      :disabled="i === 0"
                      :title="t('composite.step.move_up')"
                      @click="moveStep(i, -1)"
                    >
                      <template #icon>↑</template>
                    </n-button>
                    <n-button
                      quaternary
                      circle
                      size="tiny"
                      :disabled="i === steps.length - 1"
                      :title="t('composite.step.move_down')"
                      @click="moveStep(i, 1)"
                    >
                      <template #icon>↓</template>
                    </n-button>
                    <n-button
                      quaternary
                      circle
                      size="tiny"
                      type="error"
                      :title="t('composite.step.delete')"
                      @click="removeStep(i)"
                    >
                      <template #icon>✕</template>
                    </n-button>
                  </n-space>
                </div>

                <n-form-item
                  :label="t('composite.step.site')"
                  :label-width="72"
                  :show-feedback="false"
                  class="mb-3"
                >
                  <n-input-group>
                    <n-select
                      v-model:value="step.site_profile_id"
                      :options="siteOptions"
                      :placeholder="t('composite.step.site_ph')"
                      size="small"
                      clearable
                    />
                    <n-button size="small" ghost type="primary" @click="openSiteModal(i)">
                      + {{ t('composite.step.site_new') }}
                    </n-button>
                  </n-input-group>
                </n-form-item>

                <n-form-item
                  :label="t('composite.step.instruction')"
                  :label-width="72"
                  required
                  :show-feedback="false"
                  class="mb-3"
                >
                  <n-input
                    v-model:value="step.instruction"
                    type="textarea"
                    :placeholder="t('composite.step.instruction_ph')"
                    :autosize="{ minRows: 2, maxRows: 6 }"
                  />
                </n-form-item>

                <LocatorEditor
                  :model-value="stepPrimaryLocator(step)"
                  :title="t('locator.title_with_desc')"
                  @update:model-value="(loc) => setStepPrimaryLocator(step, loc)"
                />
              </div>

              <n-button dashed block @click="addStep">
                + {{ t('composite.step.add') }}
              </n-button>
            </div>
          </n-card>
        </n-form>
      </div>
    </div>

    <!-- Recording modal (Line B) -->
    <n-modal
      v-model:show="showRecording"
      preset="card"
      :title="t('recording.title')"
      style="width: 860px"
      :mask-closable="false"
    >
      <RecordingPanel
        v-if="showRecording"
        :user-id="props.userId"
        :site-profile-id="steps[steps.length - 1]?.site_profile_id || ''"
        @done="onRecordingDone"
        @cancel="showRecording = false"
      />
    </n-modal>

    <!-- New site modal -->
    <n-modal
      v-model:show="showSiteModal"
      preset="card"
      :title="t('composite.site.modal_title')"
      style="width: 560px"
      :mask-closable="false"
    >
      <n-form
        label-placement="left"
        label-align="right"
        :label-width="96"
        :show-require-mark="true"
      >
        <n-form-item :label="t('composite.site.name')" required :show-feedback="false" class="mb-3">
          <n-input v-model:value="newSite.name" :placeholder="t('composite.site.name_ph')" />
        </n-form-item>
        <n-form-item :label="t('composite.site.entry_url')" :show-feedback="false" class="mb-3">
          <n-input v-model:value="newSite.entry_url" placeholder="https://oa.acme.com/" />
        </n-form-item>
        <n-form-item :label="t('composite.site.auth_method')" :show-feedback="false" class="mb-3">
          <n-input v-model:value="newSite.auth_method" :placeholder="t('composite.site.auth_ph')" />
        </n-form-item>
        <n-form-item :label="t('composite.site.hints')" :show-feedback="false" class="mb-3">
          <n-input
            v-model:value="newSite.hints"
            type="textarea"
            :autosize="{ minRows: 4, maxRows: 10 }"
            :placeholder="t('composite.site.hints_ph')"
          />
        </n-form-item>
        <n-form-item :label="t('composite.field.visibility')" :show-feedback="false" class="mb-0">
          <n-select
            v-model:value="newSite.visibility"
            :options="visibilityOptions"
            size="small"
            style="width: 140px"
          />
        </n-form-item>
      </n-form>
      <template #footer>
        <n-space justify="end" :size="8">
          <n-button @click="showSiteModal = false">{{ t('composite.cancel') }}</n-button>
          <n-button type="primary" :disabled="!newSite.name.trim()" @click="saveNewSite">
            {{ t('composite.save') }}
          </n-button>
        </n-space>
      </template>
    </n-modal>
  </div>
</template>

<style scoped>
.custom-scrollbar::-webkit-scrollbar { width: 6px; }
.custom-scrollbar::-webkit-scrollbar-track { background: transparent; }
.custom-scrollbar::-webkit-scrollbar-thumb { background: #e2e8f0; border-radius: 10px; }
</style>
