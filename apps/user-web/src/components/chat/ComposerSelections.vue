<script setup lang="ts">
import type { SelectableSkillItem } from '../../api/skills'
import { t } from '../../composables/i18n'

defineProps<{
  knowledgeQaEnabled: boolean
  knowledgeLabel: string
  selectedSkill: SelectableSkillItem | null
}>()
const emit = defineEmits<{
  (e: 'disable-knowledge'): void
  (e: 'clear-skill'): void
  (e: 'show-feedback'): void
}>()
function skillSourceLabel(source: SelectableSkillItem['sourceScope']) {
  return source === 'organization' ? t('composer.scope.organization') : t('composer.scope.mine')
}
</script>

<template>
      <div v-if="knowledgeQaEnabled" class="mb-2 flex flex-wrap gap-2">
        <button
          type="button"
          class="inline-flex min-h-9 items-center gap-2 rounded-full border border-blue-200 bg-blue-50 px-3 text-sm font-medium text-blue-700 shadow-sm transition hover:border-blue-300 hover:bg-blue-100"
          @click="emit('disable-knowledge')"
        >
          <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4z"></path>
            <path d="M9 9a3 3 0 0 1 6 0c0 2-3 2-3 4"></path>
            <path d="M12 17h.01"></path>
          </svg>
          <span>{{ knowledgeLabel }}</span>
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
          @click="emit('clear-skill')"
        >
          <svg class="h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M12 3l7 4v5c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V7l7-4z"></path>
            <path d="M9 12l2 2 4-5"></path>
          </svg>
          <span class="shrink-0">{{ t('composer.selected') }}</span>
          <span class="min-w-0 truncate">{{ selectedSkill.name }}</span>
          <span v-if="selectedSkill.entryKind === 'command'" class="shrink-0 rounded-full bg-white/70 px-1.5 py-0.5 text-[11px] text-indigo-600">{{ t('composer.skill.pluginCommand') }}</span>
          <span v-if="selectedSkill.pluginName" class="shrink-0 rounded-full bg-white/70 px-1.5 py-0.5 text-[11px] text-indigo-600">{{ t('composer.skill.pluginSource', { name: selectedSkill.pluginName }) }}</span>
          <span class="shrink-0 rounded-full bg-white/70 px-1.5 py-0.5 text-[11px] text-indigo-600">{{ skillSourceLabel(selectedSkill.sourceScope) }}</span>
          <svg class="h-3.5 w-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" aria-hidden="true">
            <path d="M18 6 6 18"></path>
            <path d="m6 6 12 12"></path>
          </svg>
        </button>
        <button v-if="selectedSkill.sourceScope === 'organization'" type="button" class="inline-flex min-h-9 items-center rounded-full border border-slate-200 bg-white px-3 text-xs font-medium text-slate-600 hover:bg-slate-50" @click="emit('show-feedback')">
          {{ t('skills.feedback.title') }}
        </button>
      </div>
</template>
