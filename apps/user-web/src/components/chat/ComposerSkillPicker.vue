<script setup lang="ts">
import { computed, ref } from 'vue'
import type { SelectableSkillItem } from '../../api/skills'
import { t } from '../../composables/i18n'
type Scope = 'all' | 'user' | 'organization'
defineProps<{
  items: SelectableSkillItem[]
  scope: Scope
  loading: boolean
  loadingMore: boolean
  hasMore: boolean
  activeIndex: number
}>()
const emit = defineEmits<{
  (e: 'scope', scope: Scope): void
  (e: 'select', skill: SelectableSkillItem): void
  (e: 'active-index', index: number): void
  (e: 'scroll', event: Event): void
  (e: 'load-more'): void
}>()
const root = ref<HTMLElement | null>(null)
defineExpose({ root })
const scopeOptions = computed<Array<{ key: Scope; label: string }>>(() => [
  { key: 'all', label: t('composer.scope.all') },
  { key: 'user', label: t('composer.scope.mine') },
  { key: 'organization', label: t('composer.scope.organization') },
])
function skillTypeLabel(type: SelectableSkillItem['type']) {
  if (type === 'workflow') return t('composer.skill.workflow')
  if (type === 'ordinary') return t('composer.skill.ordinary')
  if (type === 'expert_package') return t('composer.skill.expert')
  return t('composer.skill.writing')
}
function skillSourceLabel(source: SelectableSkillItem['sourceScope']) {
  return source === 'organization' ? t('composer.scope.organization') : t('composer.scope.mine')
}
function unavailableMessage(reason?: string) {
  const key = reason === 'environment_preparing' ? 'composer.skill.environmentPreparing'
    : reason === 'environment_failed' ? 'composer.skill.environmentFailed'
    : reason?.startsWith('environment_') ? 'composer.skill.environmentUnavailable'
    : 'composer.skill.executionAccessDenied'
  return t(key)
}
</script>

<template>
<div
  ref="root"
  class="absolute bottom-[calc(100%+10px)] left-3 z-30 w-[420px] max-w-[calc(100vw-40px)] overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl shadow-slate-900/12"
>
  <div class="flex items-center justify-between border-b border-slate-100 px-3 py-2">
    <div class="text-sm font-semibold text-slate-800">{{ t('composer.selectSkill') }}</div>
    <div class="flex rounded-full bg-slate-100 p-0.5">
      <button
        v-for="option in scopeOptions"
        :key="option.key"
        type="button"
        class="rounded-full px-2.5 py-1 text-xs font-medium transition"
        :class="scope === option.key ? 'bg-white text-blue-700 shadow-sm' : 'text-slate-500 hover:text-slate-700'"
        @click="emit('scope', option.key)"
      >
        {{ option.label }}
      </button>
    </div>
  </div>
  <div
    class="max-h-[300px] overflow-y-auto py-1"
    role="listbox"
    :aria-label="t('composer.skillList')"
    @scroll="emit('scroll', $event)"
  >
    <div v-if="loading" class="px-4 py-8 text-center text-sm text-slate-400">
      {{ t('composer.loading') }}
    </div>
    <template v-else>
      <button
        v-for="(skill, index) in items"
        :key="skill.id"
        :id="`skill-picker-option-${index}`"
        :data-skill-index="index"
        type="button"
        role="option"
        :aria-selected="activeIndex === index"
        :aria-disabled="skill.available === false"
        :disabled="skill.available === false"
        class="flex w-full gap-3 px-3 py-2.5 text-left transition"
        :class="skill.available === false ? 'cursor-not-allowed opacity-65' : activeIndex === index ? 'bg-blue-50/80' : 'hover:bg-slate-50'"
        @mouseenter="skill.available !== false && emit('active-index', index)"
        @click="emit('select', skill)"
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
          <span class="block break-words text-sm font-semibold text-slate-900">{{ skill.name }}</span>
          <span class="mt-1 flex flex-wrap items-center gap-1.5">
            <span v-if="skill.entryKind === 'command'" class="shrink-0 rounded-full bg-amber-50 px-1.5 py-0.5 text-[11px] font-medium text-amber-700">{{ t('composer.skill.pluginCommand') }}</span>
            <span v-if="skill.pluginName" class="shrink-0 rounded-full bg-indigo-50 px-1.5 py-0.5 text-[11px] font-medium text-indigo-700">{{ t('composer.skill.pluginSource', { name: skill.pluginName }) }}</span>
            <span class="shrink-0 rounded-full bg-slate-100 px-1.5 py-0.5 text-[11px] font-medium text-slate-500">{{ skillSourceLabel(skill.sourceScope) }}</span>
            <span class="shrink-0 rounded-full bg-slate-100 px-1.5 py-0.5 text-[11px] font-medium text-slate-500">{{ skillTypeLabel(skill.type) }}</span>
          </span>
          <span class="mt-1 block truncate text-xs text-slate-500" :title="skill.description || skill.scenario || t('composer.noDescription')">{{ skill.description || skill.scenario || (t('composer.noDescription')) }}</span>
          <span v-if="skill.available === false" class="mt-1 block text-xs font-medium text-amber-700">{{ unavailableMessage(skill.unavailableReason) }}</span>
        </span>
      </button>
      <div v-if="items.length === 0" class="px-4 py-8 text-center text-sm text-slate-400">
        {{ t('composer.noSkills') }}
      </div>
      <button
        v-if="hasMore"
        type="button"
        class="mx-3 my-2 flex w-[calc(100%-24px)] items-center justify-center rounded-xl border border-slate-200 px-3 py-2 text-sm font-medium text-slate-600 transition hover:bg-slate-50 disabled:cursor-wait disabled:opacity-60"
        :disabled="loadingMore"
        @click="emit('load-more')"
      >
        {{ loadingMore ? (t('composer.loading')) : (t('composer.loadMore')) }}
      </button>
    </template>
          </div>
        </div>
</template>
