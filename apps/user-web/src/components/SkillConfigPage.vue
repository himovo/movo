
<template>
  <div class="flex flex-col h-full w-full bg-[#f8fafc]">
    <!-- Header -->
    <header class="h-16 border-b border-gray-200 bg-white/80 backdrop-blur-sm flex items-center px-8 justify-between shrink-0 sticky top-0 z-10">
      <div class="flex items-center gap-4 min-w-0 flex-1">
        <n-button quaternary circle @click="emit('back')" :title="t('skill_config.back')">
          <template #icon>
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m15 18-6-6 6-6"/></svg>
          </template>
        </n-button>
        <div class="min-w-0 flex-1">
          <input
            v-model="skillName"
            type="text"
            class="skill-config-title-input"
            :placeholder="t('skill_config.name_placeholder')"
          />
          <input
            v-model="skillDesc"
            type="text"
            class="skill-config-desc-input"
            :placeholder="t('skill_config.desc_placeholder')"
          />
        </div>
      </div>
      <n-space :size="8" class="shrink-0">
        <n-button type="error" ghost @click="emit('remove', props.skill)">
          {{ t('skill_config.delete_skill') }}
        </n-button>
        <n-button @click="emit('back')">
          {{ t('skill_config.discard') }}
        </n-button>
        <n-button type="primary" @click="saveConfig">
          <template #icon>
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>
          </template>
          {{ t('skill_config.save_changes') }}
        </n-button>
      </n-space>
    </header>

    <div class="flex-1 overflow-hidden p-6 lg:p-8">
      <div class="max-w-[1400px] mx-auto h-full grid grid-cols-12 gap-8">
        
        <!-- Main Editor Card -->
        <div class="col-span-12 lg:col-span-8 flex flex-col h-full">
          <div class="bg-white rounded-2xl border border-gray-200 shadow-sm flex flex-col h-full overflow-hidden">
            <div class="px-5 py-3 border-b border-gray-100 bg-gray-50/50 flex items-center justify-between">
              <span class="text-xs font-bold text-gray-400 uppercase tracking-widest">{{ t('skill_config.instructions') }}</span>
              <div class="flex items-center gap-2">
                <span class="w-2 h-2 rounded-full bg-green-500"></span>
                <span class="text-[10px] text-gray-500 font-medium uppercase">{{ t('skill_config.active_editor') }}</span>
              </div>
            </div>
            <textarea
              v-model="skillMarkdown"
              spellcheck="false"
              :placeholder="t('skill_config.markdown_placeholder')"
              class="flex-1 w-full p-6 text-sm leading-relaxed text-gray-700 focus:outline-none font-mono bg-[#fdfdfd] resize-none selection:bg-blue-100"
              style="font-family: 'JetBrains Mono', 'Fira Code', ui-monospace, monospace;"
            ></textarea>
            <div class="px-5 py-2 border-t border-gray-100 bg-white flex justify-between items-center">
               <span class="text-[10px] text-gray-400 italic">{{ t('skill_config.markdown_supported') }}</span>
               <span class="text-[10px] text-gray-400 uppercase font-bold">{{ skillMarkdown.length }} chars</span>
            </div>
          </div>
        </div>

        <!-- Sidebar / Config Cards -->
        <div class="col-span-12 lg:col-span-4 space-y-6 overflow-y-auto pr-2 custom-scrollbar">
          
          <!-- Metadata Section -->
          <div class="space-y-3 pt-1">
            <h2 class="text-xs font-bold text-gray-400 uppercase tracking-widest px-1">{{ t('skill_config.settings') }}</h2>
            <div class="bg-white rounded-xl border border-gray-200 shadow-sm p-4 space-y-3">
               <div class="space-y-1.5">
                  <label class="block text-[11px] font-semibold text-gray-700">{{ t('skill_config.skill_type') }}</label>
                  <n-select v-model:value="skillType" :options="skillTypeOptions" />
                </div>
               <div class="space-y-1.5">
                  <label class="block text-[11px] font-semibold text-gray-700">{{ t('skill_config.category') }}</label>
                  <n-select v-model:value="skillCategory" :options="categoryOptions" />
                </div>
               <div class="space-y-1.5">
                  <label class="block text-[11px] font-semibold text-gray-700">{{ t('skill_config.applicable_scenarios') }}</label>
                  <n-input
                    v-model:value="applicableScenarios"
                    type="textarea"
                    :autosize="{ minRows: 3, maxRows: 5 }"
                    :placeholder="t('skill_config.scenario_placeholder')"
                  />
                </div>
               <div class="flex min-h-[220px] flex-col space-y-1.5">
                  <label class="block text-[11px] font-semibold text-gray-700">{{ t('skill_config.channels') }}</label>
                  <TokenInput v-model="publishChannelInput" :suggestions="publishChannelSuggestions" :placeholder="t('skill_config.add_channels')" />
               </div>
               <div class="flex min-h-[220px] flex-col space-y-1.5">
                  <label class="block text-[11px] font-semibold text-gray-700">{{ t('skill_config.content_forms') }}</label>
                  <TokenInput v-model="contentFormInput" :suggestions="contentFormSuggestions" :placeholder="t('skill_config.add_content_forms')" />
               </div>
               <div class="flex min-h-[220px] flex-col space-y-1.5">
                  <label class="block text-[11px] font-semibold text-gray-700">{{ t('skill_config.target_audience') }}</label>
                  <TokenInput v-model="targetAudienceInput" :suggestions="targetAudienceSuggestions" :placeholder="t('skill_config.add_audiences')" />
               </div>
               <div class="flex min-h-[220px] flex-col space-y-1.5">
                  <label class="block text-[11px] font-semibold text-gray-700">{{ t('skill_config.preferred_style') }}</label>
                  <TokenInput v-model="preferredStyleInput" :suggestions="preferredStyleSuggestions" :placeholder="t('skill_config.add_styles')" />
               </div>
               <div class="space-y-1.5">
                  <label class="block text-[11px] font-semibold text-gray-700">{{ t('skill_config.must_include') }}</label>
                  <TokenInput v-model="requiredElementsInput" :placeholder="t('skill_config.add_required')" />
               </div>
               <div class="space-y-1.5">
                  <label class="block text-[11px] font-semibold text-gray-700">{{ t('skill_config.must_avoid') }}</label>
                  <TokenInput v-model="forbiddenElementsInput" :placeholder="t('skill_config.add_forbidden')" />
               </div>
               <div class="pt-0.5">
                  <n-button
                    size="small"
                    secondary
                    class="transition-all"
                    :class="canSmartFill ? 'border border-amber-200 bg-gradient-to-r from-amber-50 to-orange-50 text-amber-700 shadow-sm hover:from-amber-100 hover:to-orange-100' : 'border border-gray-200 bg-gray-50 text-gray-400'"
                    :disabled="enriching || !canSmartFill"
                    @click="enrichContract"
                  >
                    {{ enriching ? t('skill_config.smart_fill_contract_loading') : t('skill_config.smart_fill_contract') }}
                  </n-button>
               </div>
            </div>
          </div>

          <!-- Resources Section -->
          <div v-if="skillType !== 'style'" class="space-y-4">
            <h2 class="text-xs font-bold text-gray-400 uppercase tracking-widest px-1">{{ t('skill_config.resources') }}</h2>
            
            <!-- Resource Groups -->
            <div v-for="group in resourceGroups" :key="group.key" class="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden p-4">
              <div class="flex items-center justify-between mb-3">
                <div class="flex items-center gap-2">
                  <div class="w-8 h-8 rounded-lg flex items-center justify-center bg-blue-50 text-blue-600">
                    <component :is="group.icon" class="w-4 h-4" />
                  </div>
                  <div>
                    <h3 class="text-sm font-semibold text-gray-800">{{ group.label }}</h3>
                    <p class="text-[10px] text-gray-400">{{ group.description }}</p>
                  </div>
                </div>
                <div class="relative group">
                  <input 
                    type="file" 
                    multiple 
                    class="absolute inset-0 w-full h-full opacity-0 cursor-pointer z-20" 
                    @change="(e) => emit('upload', e, group.key)" 
                  />
                  <button class="w-8 h-8 rounded-lg border border-dashed border-gray-300 flex items-center justify-center text-gray-400 group-hover:border-blue-500 group-hover:text-blue-500 group-hover:bg-blue-50 transition-all">
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14M5 12h14"/></svg>
                  </button>
                </div>
              </div>

              <!-- File List -->
              <div class="space-y-1.5 min-h-[40px]">
                <div v-if="group.files.length === 0" class="flex flex-col items-center justify-center py-4 border border-dashed border-gray-100 rounded-lg bg-gray-50/50">
                  <span class="text-[10px] text-gray-400 italic">{{ t('ui.none_uploaded') }}</span>
                </div>
                <div 
                  v-for="src in group.files" 
                  :key="src.object_path" 
                  class="flex items-center justify-between p-2 rounded-lg bg-gray-50 border border-transparent hover:border-gray-200 group/item transition-all"
                >
                  <div class="flex items-center gap-2 min-w-0">
                    <svg class="w-3 h-3 text-gray-400 shrink-0" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                    <span class="text-[11px] font-medium text-gray-600 truncate">{{ src.filename || src.object_path }}</span>
                  </div>
                  <button class="opacity-0 group-hover/item:opacity-100 p-1 text-gray-400 hover:text-red-500 transition-opacity">
                    <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2M10 11v6M14 11v6"/></svg>
                  </button>
                </div>
              </div>
            </div>
          </div>

          <!-- Advanced Controls -->
          <div v-if="skillType !== 'style'" class="space-y-4 pt-2">
             <h2 class="text-xs font-bold text-gray-400 uppercase tracking-widest px-1">{{ t('skill_config.capabilities') }}</h2>
             <div class="bg-white rounded-xl border border-gray-200 shadow-sm p-4 space-y-4">
                
                <!-- Toggle Item -->
                <div v-for="toggle in advancedToggles" :key="toggle.key" class="flex items-center justify-between group">
                  <div>
                    <h4 class="text-xs font-semibold text-gray-700">{{ toggle.label }}</h4>
                    <p class="text-[10px] text-gray-400 italic">{{ toggle.desc }}</p>
                  </div>
                  <n-switch v-model:value="toggle.model.value" size="small" />
                </div>

             </div>
          </div>

        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, h, ref, watch } from 'vue'
import { NButton, NInput, NSelect, NSpace, NSwitch } from 'naive-ui'
import { enrichSkillDraft } from '../api/skills'
import { t, useLocale } from '../composables/i18n'
import TokenInput from './TokenInput.vue'

const props = defineProps<{
  skill: any | null
}>()

const emit = defineEmits(['back', 'save', 'upload', 'remove'])

const skillName = ref(props.skill?.name || '')
const skillDesc = ref(props.skill?.description || '')
const skillCategory = ref(props.skill?.category || 'document')
const skillType = ref(props.skill?.skill_type || 'style')
const skillMarkdown = ref(props.skill?.skill_markdown || '')
const applicableScenarios = ref(props.skill?.contract_json?.applicable_scenarios || '')
const publishChannelInput = ref<string[]>((props.skill?.contract_json?.publish_channel || []) as string[])
const contentFormInput = ref<string[]>((props.skill?.contract_json?.content_form || []) as string[])
const targetAudienceInput = ref<string[]>((props.skill?.contract_json?.target_audience || []) as string[])
const preferredStyleInput = ref<string[]>((props.skill?.contract_json?.preferred_style || []) as string[])
const requiredElementsInput = ref<string[]>((props.skill?.contract_json?.required_elements || []) as string[])
const forbiddenElementsInput = ref<string[]>((props.skill?.contract_json?.forbidden_elements || []) as string[])
const resourceKnowledge = ref(props.skill?.resources?.knowledge || [])
const resourceTemplates = ref(props.skill?.resources?.templates || [])
const resourceTools = ref(props.skill?.resources?.tools || [])
const isActive = ref(props.skill?.is_active ?? true)
const enriching = ref(false)

const allowToolExecution = ref(props.skill?.advanced?.allowToolExecution || false)
const requireConfirmation = ref(props.skill?.advanced?.requireConfirmation || false)
const allowNetwork = ref(props.skill?.advanced?.allowNetwork || false)
const allowFileWrite = ref(props.skill?.advanced?.allowFileWrite || false)
const { locale } = useLocale()

// Computed helpers for UI
const resourceGroups = computed(() => [
  {
    key: 'knowledge',
    label: t('skill_config.knowledge'),
    description: t('skill_config.knowledge_desc'),
    files: resourceKnowledge.value,
    icon: h('svg', { xmlns: 'http://www.w3.org/2000/svg', width: '24', height: '24', viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': '2' }, [
      h('path', { d: 'M4 19.5A2.5 2.5 0 0 1 6.5 17H20' }),
      h('path', { d: 'M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z' })
    ])
  },
  {
    key: 'templates',
    label: t('skill_config.templates'),
    description: t('skill_config.templates_desc'),
    files: resourceTemplates.value,
    icon: h('svg', { xmlns: 'http://www.w3.org/2000/svg', width: '24', height: '24', viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': '2' }, [
      h('rect', { width: '18', height: '18', x: '3', y: '3', rx: '2' }),
      h('path', { d: 'M3 9h18' }),
      h('path', { d: 'M9 21V9' })
    ])
  },
  {
    key: 'tools',
    label: t('skill_config.tools'),
    description: t('skill_config.tools_desc'),
    files: resourceTools.value,
    icon: h('svg', { xmlns: 'http://www.w3.org/2000/svg', width: '24', height: '24', viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': '2' }, [
      h('path', { d: 'm16 18 2 2 4-4' }),
      h('path', { d: 'M21 11V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h6' }),
      h('path', { d: 'M3 10h18' }),
      h('path', { d: 'M10 3v18' })
    ])
  }
])

const advancedToggles = computed(() => [
  { key: 'tool', label: t('skill_config.cap.allow_tools'), desc: t('skill_config.cap.allow_tools_desc'), model: allowToolExecution },
  { key: 'confirm', label: t('skill_config.cap.require_confirmation'), desc: t('skill_config.cap.require_confirmation_desc'), model: requireConfirmation },
  { key: 'net', label: t('skill_config.cap.allow_network'), desc: t('skill_config.cap.allow_network_desc'), model: allowNetwork },
  { key: 'file', label: t('skill_config.cap.allow_file_write'), desc: t('skill_config.cap.allow_file_write_desc'), model: allowFileWrite },
])
const canSmartFill = computed(() => Boolean(skillName.value.trim() && (skillDesc.value.trim() || applicableScenarios.value.trim())))
const publishChannelSuggestions = [
  'wechat_official',
  'xiaohongshu',
  'zhihu',
  'website',
  'email',
  'knowledge_base',
  'docs',
  'social_post',
  'community_post',
  'generic',
]
const contentFormSuggestions = [
  'article',
  'report',
  'brief',
  'guide',
  'memo',
  'review',
  'faq',
  'presentation_outline',
]
const targetAudienceSuggestions = [
  'general_public',
  'beginners',
  'professionals',
  'developers',
  'entrepreneurs',
  'business_owners',
  'marketers',
  'students',
  'decision_makers',
  'product_users',
]
const preferredStyleSuggestions = [
  'formal',
  'professional',
  'casual',
  'conversational',
  'friendly',
  'authoritative',
  'analytical',
  'objective',
  'persuasive',
  'inspirational',
  'humorous',
  'storytelling',
  'concise',
  'detailed',
  'technical',
  'educational',
  'practical',
  'neutral',
  'critical',
  'optimistic',
]
const skillTypeOptions = computed(() => [
  { label: t('skill_config.type.style'), value: 'style' },
  { label: t('skill_config.type.execution'), value: 'execution' },
  { label: t('skill_config.type.renderer'), value: 'renderer' },
])
const categoryOptions = computed(() => [
  { label: t('skills.category.analysis_reports'), value: 'Analysis & Reports' },
  { label: t('skills.category.specs_product'), value: 'Specs & Product' },
  { label: t('skills.category.governance_sops'), value: 'Governance & SOPs' },
  { label: t('skills.category.presentation_visuals'), value: 'Presentation & Visuals' },
  { label: t('skills.category.coding_engineering'), value: 'Coding & Engineering' },
  { label: t('skills.category.browser_automation'), value: 'Browser Automation' },
])

watch(
  () => props.skill,
  (val) => {
    skillName.value = val?.name || ''
    skillDesc.value = val?.description || ''
    skillCategory.value = val?.category || 'document'
    skillType.value = val?.skill_type || 'style'
    skillMarkdown.value = val?.skill_markdown || ''
    applicableScenarios.value = val?.contract_json?.applicable_scenarios || ''
    publishChannelInput.value = ((val?.contract_json?.publish_channel || []) as string[])
    contentFormInput.value = ((val?.contract_json?.content_form || []) as string[])
    targetAudienceInput.value = ((val?.contract_json?.target_audience || []) as string[])
    preferredStyleInput.value = ((val?.contract_json?.preferred_style || []) as string[])
    requiredElementsInput.value = ((val?.contract_json?.required_elements || []) as string[])
    forbiddenElementsInput.value = ((val?.contract_json?.forbidden_elements || []) as string[])
    resourceKnowledge.value = val?.resources?.knowledge || []
    resourceTemplates.value = val?.resources?.templates || []
    resourceTools.value = val?.resources?.tools || []
    allowToolExecution.value = val?.advanced?.allowToolExecution || false
    requireConfirmation.value = val?.advanced?.requireConfirmation || false
    allowNetwork.value = val?.advanced?.allowNetwork || false
    allowFileWrite.value = val?.advanced?.allowFileWrite || false
    isActive.value = val?.is_active ?? true
  }
)

async function enrichContract() {
  if (!props.skill?.user_id || !skillName.value.trim()) return
  enriching.value = true
  try {
    const inputProfile = {
      skill_type: skillType.value,
      name: skillName.value,
      summary: skillDesc.value,
      applicable_scenarios: applicableScenarios.value,
      publish_channel: publishChannelInput.value,
      content_form: contentFormInput.value,
      target_audience: targetAudienceInput.value,
      preferred_style: preferredStyleInput.value,
      required_elements: requiredElementsInput.value,
      forbidden_elements: forbiddenElementsInput.value,
      reference_materials: [
        ...resourceKnowledge.value.map((item: any) => item.filename || item.object_path),
        ...resourceTemplates.value.map((item: any) => item.filename || item.object_path),
      ],
      notes: skillMarkdown.value,
    }
    const enriched = await enrichSkillDraft({
      user_id: props.skill.user_id,
      name: skillName.value,
      description: skillDesc.value,
      skill_type: skillType.value,
      input_profile: inputProfile,
    })
    const contract = enriched?.contract_json || {}
    skillMarkdown.value = enriched?.skill_markdown || skillMarkdown.value
    applicableScenarios.value = contract.applicable_scenarios || applicableScenarios.value
    publishChannelInput.value = contract.publish_channel || publishChannelInput.value
    contentFormInput.value = contract.content_form || contentFormInput.value
    targetAudienceInput.value = contract.target_audience || targetAudienceInput.value
    preferredStyleInput.value = contract.preferred_style || preferredStyleInput.value
    requiredElementsInput.value = contract.required_elements || requiredElementsInput.value
    forbiddenElementsInput.value = contract.forbidden_elements || forbiddenElementsInput.value
  } finally {
    enriching.value = false
  }
}

function saveConfig() {
  if (!props.skill) return
  const contractJson = {
    skill_type: skillType.value,
    name: skillName.value,
    summary: skillDesc.value,
    applicable_scenarios: applicableScenarios.value,
    publish_channel: publishChannelInput.value,
    content_form: contentFormInput.value,
    target_audience: targetAudienceInput.value,
    preferred_style: preferredStyleInput.value,
    required_elements: requiredElementsInput.value,
    forbidden_elements: forbiddenElementsInput.value,
    reference_materials: [
      ...resourceKnowledge.value.map((item: any) => item.filename || item.object_path),
      ...resourceTemplates.value.map((item: any) => item.filename || item.object_path),
    ],
    notes: skillMarkdown.value,
  }
  emit('save', {
    id: props.skill.id,
    name: skillName.value,
    description: skillDesc.value,
    category: skillCategory.value,
    skill_type: skillType.value,
    is_active: isActive.value,
    input_profile: contractJson,
    contract_json: contractJson,
    skill_markdown: skillMarkdown.value,
    resources: {
      knowledge: resourceKnowledge.value,
      templates: resourceTemplates.value,
      tools: resourceTools.value,
    },
    advanced: {
      allowToolExecution: allowToolExecution.value,
      requireConfirmation: requireConfirmation.value,
      allowNetwork: allowNetwork.value,
      allowFileWrite: allowFileWrite.value,
    },
  })
}
</script>

<style scoped>
.skill-config-title-input {
  font-size: 1.125rem;
  font-weight: 600;
  color: rgb(17 24 39);
  line-height: 1.1;
  padding: 0;
  border: 0;
  outline: none;
  background: transparent;
  width: 100%;
}

.skill-config-desc-input {
  font-size: 0.75rem;
  font-weight: 500;
  color: rgb(107 114 128);
  line-height: 1.25;
  padding: 0;
  border: 0;
  outline: none;
  background: transparent;
  width: 100%;
  margin-top: 0.25rem;
}

.skill-config-title-input::placeholder {
  color: rgb(156 163 175);
}

.skill-config-desc-input::placeholder {
  color: rgb(156 163 175);
}

.custom-scrollbar::-webkit-scrollbar {
  width: 4px;
}
.custom-scrollbar::-webkit-scrollbar-track {
  background: transparent;
}
.custom-scrollbar::-webkit-scrollbar-thumb {
  background: #e2e8f0;
  border-radius: 10px;
}
.custom-scrollbar::-webkit-scrollbar-thumb:hover {
  background: #cbd5e1;
}

textarea {
  tab-size: 2;
}

/* Simple fade transition for peer peer-checked after */
.peer:checked ~ div::after {
  transform: translateX(100%);
}
</style>
