<script setup lang="ts">
import { computed } from 'vue'
import { entryVisible } from '../composables/useEntryVisibility'
import { t } from '../composables/i18n'
import type { AppView } from '../composables/useAppNavigation'

const props = defineProps<{
  currentView: AppView
  canUseSkills: boolean
  canUseTools: boolean
  pendingSkillShareCount: number
  personalKnowledgeUnreadCount: number
}>()
const hasVisibleEntries = computed(() => (props.canUseSkills && entryVisible('skills')) || entryVisible('plugins') || (props.canUseTools && (entryVisible('tools') || entryVisible('knowledge'))))
const emit = defineEmits<{ skills: []; plugins: []; tools: []; knowledge: [] }>()
</script>

<template>
  <template v-if="hasVisibleEntries">
  <div class="mt-2 px-5 pb-1 text-[10px] font-bold text-gray-400 uppercase tracking-[0.1em]">{{ t('app.sidebar.skills') }}</div>
  <div class="mb-2 space-y-0.5 px-3">
    <button
      v-if="props.canUseSkills && entryVisible('skills')"
      class="flex w-full items-center gap-3 rounded-xl border border-transparent px-3 py-2 text-left text-sm transition-all active:scale-95"
      :class="props.currentView === 'skills'
        ? 'bg-white text-blue-700 shadow-sm border-gray-200 font-semibold'
        : 'text-gray-700 hover:bg-gray-200/50'"
      @click="emit('skills')"
    >
      <span class="text-gray-500">
        <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M20 7l.94-2.06L23 4l-2.06-.94L20 1l-.94 2.06L17 4l2.06.94zM8.5 7l.94-2.06L11.5 4l-2.06-.94L8.5 1l-.94 2.06L5.5 4l2.06.94zM20 12.5l-.94 2.06l-2.06.94l2.06.94l.94 2.06l.94-2.06L23 15.5l-2.06-.94zm-2.29-3.38l-2.83-2.83c-.2-.19-.45-.29-.71-.29c-.26 0-.51.1-.71.29L2.29 17.46a.996.996 0 0 0 0 1.41l2.83 2.83c.2.2.45.3.71.3s.51-.1.71-.29l11.17-11.17c.39-.39.39-1.03 0-1.42zm-3.54-.7l1.41 1.41L14.41 11L13 9.59l1.17-1.17zM5.83 19.59l-1.41-1.41L11.59 11L13 12.41l-7.17 7.18z"/></svg>
      </span>
      <span>{{ t('app.sidebar.marketplace') }}</span>
      <span
        v-if="props.pendingSkillShareCount > 0"
        class="ml-auto inline-flex min-w-[18px] items-center justify-center rounded-full bg-red-500 px-1.5 py-0.5 text-[10px] font-bold leading-none text-white shadow-sm"
        :title="t('skills.share.pending_nav', { count: props.pendingSkillShareCount })"
        :aria-label="t('skills.share.pending_nav', { count: props.pendingSkillShareCount })"
      >{{ props.pendingSkillShareCount > 99 ? '99+' : props.pendingSkillShareCount }}</span>
    </button>
    <button
      v-if="entryVisible('plugins')"
      class="flex w-full items-center gap-3 rounded-xl border border-transparent px-3 py-2 text-left text-sm transition-all active:scale-95"
      :class="props.currentView === 'plugins' ? 'bg-white text-blue-700 shadow-sm border-gray-200 font-semibold' : 'text-gray-700 hover:bg-gray-200/50'"
      @click="emit('plugins')"
    >
      <span class="text-gray-500"><svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M8 3h8v4h4v5h-4v3h4v6H4v-6h4v-3H4V7h4V3Z"/><path d="M8 7h8M8 15h8"/></svg></span>
      <span>{{ t('plugins.sidebar') }}</span>
    </button>
    <button
      v-if="props.canUseTools && entryVisible('tools')"
      class="flex w-full items-center gap-3 rounded-xl border border-transparent px-3 py-2 text-left text-sm transition-all active:scale-95"
      :class="props.currentView === 'tools'
        ? 'bg-white text-blue-700 shadow-sm border-gray-200 font-semibold'
        : 'text-gray-700 hover:bg-gray-200/50'"
      @click="emit('tools')"
    >
      <span class="text-gray-500">
        <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path opacity=".3" d="M3 10.5c-.55 0-1-.45-1-1s.45-1 1-1s1 .45 1 1s-.45 1-1 1zM6 21c-.55 0-1-.45-1-1s.45-1 1-1s1 .45 1 1s-.45 1-1 1zm5-18c0-.55.45-1 1-1s1 .45 1 1s-.45 1-1 1s-1-.45-1-1zm1 12a2.5 2.5 0 0 1 0-5a2.5 2.5 0 0 1 0 5zm6 4c.55 0 1 .45 1 1s-.45 1-1 1s-1-.45-1-1s.45-1 1-1zm3-8.5c-.55 0-1-.45-1-1s.45-1 1-1s1 .45 1 1s-.45 1-1 1z" /><path d="M21 6.5a2.996 2.996 0 0 0-2.99 3.21l-2.03.68a4.468 4.468 0 0 0-3.22-2.32V5.91A3.018 3.018 0 0 0 15 3c0-1.66-1.34-3-3-3S9 1.34 9 3c0 1.4.96 2.57 2.25 2.91v2.16c-1.4.23-2.58 1.11-3.22 2.32l-2.04-.68C6 9.64 6 9.57 6 9.5c0-1.66-1.34-3-3-3s-3 1.34-3 3s1.34 3 3 3c1.06 0 1.98-.55 2.52-1.37l2.03.68c-.2 1.29.17 2.66 1.09 3.69l-1.41 1.77C6.85 17.09 6.44 17 6 17c-1.66 0-3 1.34-3 3s1.34 3 3 3s3-1.34 3-3c0-.68-.22-1.3-.6-1.8l1.41-1.77c1.36.76 3.02.75 4.37 0l1.41 1.77c-.37.5-.59 1.12-.59 1.8c0 1.66 1.34 3 3 3s3-1.34 3-3s-1.34-3-3-3c-.44 0-.85.09-1.23.26l-1.41-1.77a4.49 4.49 0 0 0 1.09-3.69l2.03-.68c.53.82 1.46 1.37 2.52 1.37c1.66 0 3-1.34 3-3S22.66 6.5 21 6.5zm-18 4c-.55 0-1-.45-1-1s.45-1 1-1s1 .45 1 1s-.45 1-1 1zM6 21c-.55 0-1-.45-1-1s.45-1 1-1s1 .45 1 1s-.45 1-1 1zm5-18c0-.55.45-1 1-1s1 .45 1 1s-.45 1-1 1s-1-.45-1-1zm1 12a2.5 2.5 0 0 1 0-5a2.5 2.5 0 0 1 0 5zm6 4c.55 0 1 .45 1 1s-.45 1-1 1s-1-.45-1-1s.45-1 1-1zm3-8.5c-.55 0-1-.45-1-1s.45-1 1-1s1 .45 1 1s-.45 1-1 1z" /></svg>
      </span>
      <span>{{ t('app.sidebar.tools') }}</span>
    </button>
    <button
      v-if="props.canUseTools && entryVisible('knowledge')"
      class="flex w-full items-center gap-3 rounded-xl border border-transparent px-3 py-2 text-left text-sm transition-all active:scale-95"
      :class="props.currentView === 'knowledge' ? 'bg-white text-blue-700 shadow-sm border-gray-200 font-semibold' : 'text-gray-700 hover:bg-gray-200/50'"
      @click="emit('knowledge')"
    >
      <span class="text-gray-500">
        <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2Z"/></svg>
      </span>
      <span>{{ t('knowledge.sidebar') }}</span>
      <span v-if="props.personalKnowledgeUnreadCount > 0" class="ml-auto inline-flex min-w-[18px] items-center justify-center rounded-full bg-red-500 px-1.5 py-0.5 text-[10px] font-bold leading-none text-white">{{ props.personalKnowledgeUnreadCount > 99 ? '99+' : props.personalKnowledgeUnreadCount }}</span>
    </button>
  </div>
  </template>
</template>
