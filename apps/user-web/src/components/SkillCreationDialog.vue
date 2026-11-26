<script setup lang="ts">
import { computed } from 'vue'
import { NButton, NInput, NSelect } from 'naive-ui'
import TokenInput from './TokenInput.vue'
import { t } from '../composables/i18n'

defineProps<{ open: boolean; creating: boolean; enriching: boolean }>()
const emit = defineEmits<{ close: []; enrich: []; create: [] }>()
const skillName = defineModel<string>('name', { required: true })
const skillSummary = defineModel<string>('summary', { required: true })
const skillType = defineModel<string>('type', { required: true })
const skillScenario = defineModel<string>('scenario', { required: true })
const skillChannels = defineModel<string[]>('channels', { required: true })
const skillForms = defineModel<string[]>('forms', { required: true })
const skillAudience = defineModel<string[]>('audience', { required: true })
const skillStyle = defineModel<string[]>('preferredStyle', { required: true })
const skillRequired = defineModel<string[]>('required', { required: true })
const skillForbidden = defineModel<string[]>('forbidden', { required: true })
const canSmartFillSkill = computed(() => Boolean(skillName.value.trim() && (skillSummary.value.trim() || skillScenario.value.trim())))

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
  { label: t('app.style'), value: 'style' },
  { label: t('app.execution'), value: 'execution' },
  { label: t('app.renderer'), value: 'renderer' },
])
</script>

<template>
  <div v-if="open" class="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
    <div class="w-[820px] max-h-[88vh] overflow-y-auto rounded-3xl bg-white shadow-xl border border-gray-200 p-6 custom-scrollbar">
      <div class="flex items-center justify-between mb-3">
        <div>
          <div class="text-lg font-semibold text-gray-900">{{ t('app.skill_form.title') }}</div>
          <div class="text-xs text-gray-500 mt-1">{{ t('app.skill_form.subtitle') }}</div>
        </div>
        <n-button text size="small" class="!text-gray-400 hover:!text-gray-600" @click="emit('close')">{{ t('ui.close') }}</n-button>
      </div>
      <div class="space-y-5">
        <section class="rounded-2xl border border-gray-200 bg-gray-50/60 p-4">
          <div class="flex items-center justify-between mb-4">
            <div>
              <div class="text-sm font-semibold text-gray-900">{{ t('app.skill_form.basics') }}</div>
              <div class="text-xs text-gray-500 mt-1">{{ t('app.skill_form.basics_hint') }}</div>
            </div>
            <n-button
              size="small"
              secondary
              :class="canSmartFillSkill ? 'border border-amber-200 bg-gradient-to-r from-amber-50 to-orange-50 text-amber-700 shadow-sm hover:from-amber-100 hover:to-orange-100' : 'border border-gray-200 text-gray-400 bg-white'"
              :disabled="enriching || !canSmartFillSkill"
              @click="emit('enrich')"
            >
              {{ enriching ? t('app.skill_form.smart_fill_loading') : t('app.skill_form.smart_fill') }}
            </n-button>
          </div>
          <div class="grid grid-cols-2 gap-4">
            <div class="col-span-2">
              <label class="block text-xs font-semibold text-gray-700 mb-1">{{ t('app.skill_form.skill_name') }}</label>
              <n-input
                v-model:value="skillName"
                :placeholder="t('app.skill_form.skill_name_placeholder')"
              />
            </div>
            <div class="col-span-2">
              <label class="block text-xs font-semibold text-gray-700 mb-1">{{ t('app.skill_form.short_summary') }}</label>
              <n-input
                v-model:value="skillSummary"
                :placeholder="t('app.skill_form.short_summary_placeholder')"
              />
            </div>
            <div>
              <label class="block text-xs font-semibold text-gray-700 mb-1">{{ t('app.skill_form.skill_type') }}</label>
              <n-select v-model:value="skillType" :options="skillTypeOptions" />
            </div>
            <div>
              <label class="block text-xs font-semibold text-gray-700 mb-1">{{ t('app.skill_form.applicable_scenarios') }}</label>
              <n-input
                v-model:value="skillScenario"
                type="textarea"
                :autosize="{ minRows: 3, maxRows: 5 }"
                :placeholder="t('app.skill_form.scenario_placeholder')"
              />
            </div>
          </div>
        </section>

        <section class="rounded-2xl border border-gray-200 bg-white p-4">
          <div class="text-sm font-semibold text-gray-900 mb-1">{{ t('app.skill_form.positioning') }}</div>
          <div class="text-xs text-gray-500 mb-4">{{ t('app.skill_form.positioning_hint') }}</div>
          <div class="grid grid-cols-2 gap-4">
            <div class="flex min-h-[220px] flex-col">
              <label class="block text-xs font-semibold text-gray-700 mb-1">{{ t('app.skill_form.publish_channels') }}</label>
              <TokenInput v-model="skillChannels" :suggestions="publishChannelSuggestions" :placeholder="t('skill_config.add_channels')" />
            </div>
            <div class="flex min-h-[220px] flex-col">
              <label class="block text-xs font-semibold text-gray-700 mb-1">{{ t('app.skill_form.content_forms') }}</label>
              <TokenInput v-model="skillForms" :suggestions="contentFormSuggestions" :placeholder="t('skill_config.add_content_forms')" />
            </div>
            <div class="flex min-h-[220px] flex-col">
              <label class="block text-xs font-semibold text-gray-700 mb-1">{{ t('app.skill_form.target_audience') }}</label>
              <TokenInput v-model="skillAudience" :suggestions="targetAudienceSuggestions" :placeholder="t('skill_config.add_audiences')" />
            </div>
            <div class="flex min-h-[220px] flex-col">
              <label class="block text-xs font-semibold text-gray-700 mb-1">{{ t('app.skill_form.preferred_style') }}</label>
              <TokenInput v-model="skillStyle" :suggestions="preferredStyleSuggestions" :placeholder="t('skill_config.add_styles')" />
            </div>
          </div>
        </section>

        <section class="rounded-2xl border border-gray-200 bg-white p-4">
          <div class="text-sm font-semibold text-gray-900 mb-1">{{ t('app.skill_form.constraints') }}</div>
          <div class="text-xs text-gray-500 mb-4">{{ t('app.skill_form.constraints_hint') }}</div>
          <div class="grid grid-cols-2 gap-4">
            <div class="min-w-0">
              <label class="block text-xs font-semibold text-gray-700 mb-1">{{ t('app.skill_form.must_include') }}</label>
              <TokenInput v-model="skillRequired" :placeholder="t('skill_config.add_required')" />
            </div>
            <div class="min-w-0">
              <label class="block text-xs font-semibold text-gray-700 mb-1">{{ t('app.skill_form.must_avoid') }}</label>
              <TokenInput v-model="skillForbidden" :placeholder="t('skill_config.add_forbidden')" />
            </div>
          </div>
        </section>

        <div class="flex justify-end gap-2 pt-1">
          <n-button size="small" @click="emit('close')">
            {{ t('ui.cancel') }}
          </n-button>
          <n-button
            size="small"
            type="primary"
            :disabled="creating || !skillName.trim()"
            @click="emit('create')"
          >
            {{ creating ? t('app.skill_form.generating') : t('ui.generate') }}
          </n-button>
        </div>
      </div>
    </div>
  </div>
</template>
