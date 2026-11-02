<script setup lang="ts">
import { viewEntryVisible } from '../composables/useEntryVisibility'
import { defineAsyncComponent } from 'vue'
import type { SessionSummary } from '../api/sessions'
import type { AppView } from '../composables/useAppNavigation'
import TokenUsagePage from './TokenUsagePage.vue'

const SkillsPage = defineAsyncComponent(() => import('./MySkillsPage.vue'))
const PluginsPage = defineAsyncComponent(() => import('./MyPluginsPage.vue'))
const ToolsPage = defineAsyncComponent(() => import('./MyToolsPage.vue'))
const KnowledgePage = defineAsyncComponent(() => import('./MyKnowledgePage.vue'))
const SkillConfigPage = defineAsyncComponent(() => import('./MySkillConfigPage.vue'))
const CompositeSkillEditor = defineAsyncComponent(() => import('./CompositeSkillEditor.vue'))
const ScheduledTaskPage = defineAsyncComponent(() => import('./scheduled-tasks/ScheduledTaskPage.vue'))

defineProps<{
  currentView: AppView
  userId: string | null
  mainId: string
  authToken: string
  selectedSkill: any
  pendingSkillShareActionCount: number
  pendingSkillFeedbackCount: number
  personalKnowledgeShareCount: number
  personalKnowledgeUnreadCount: number
  sessions: SessionSummary[]
  currentSessionId: string | null
  scheduledTaskInitialSessionId: string | null
  scheduledTaskInitialPrompt: string
  scheduledTaskCreateRequestKey: number
  timezoneValue: string
}>()
const emit = defineEmits<{
  configure: [skill: any]
  login: []
  shareCountChange: []
  knowledgeViewed: []
  skillBack: []
  skillSaved: [skill: any]
  compositeSaved: [skill: any]
  removeSkill: [skill: any]
  scheduledBack: []
  openSession: [id: string]
  usageBack: []
}>()
</script>

<template>
  <template v-if="viewEntryVisible(currentView)">
  <div v-if="currentView === 'skills'" class="flex-1 min-w-0 min-h-0 overflow-hidden">
    <SkillsPage
      :userId="userId"
      :mainId="mainId"
      :pendingShareCount="pendingSkillShareActionCount"
      :pendingFeedbackCount="pendingSkillFeedbackCount"
      @configure="emit('configure', $event)"
      @login="emit('login')"
      @share-count-change="emit('shareCountChange')"
    />
  </div>
  <div v-else-if="currentView === 'plugins'" class="flex-1 min-w-0 min-h-0 overflow-hidden"><PluginsPage /></div>
  <div v-else-if="currentView === 'tools'" class="flex-1 min-w-0 min-h-0 overflow-hidden">
    <ToolsPage :userId="userId" :mainId="mainId" />
  </div>
  <div v-else-if="currentView === 'knowledge'" class="flex-1 min-w-0 min-h-0 overflow-hidden">
    <KnowledgePage
      :shared-unread-count="personalKnowledgeShareCount"
      :unread-count="personalKnowledgeUnreadCount"
      @viewed="emit('knowledgeViewed')"
    />
  </div>
  <div v-else-if="currentView === 'skill-config'" class="flex-1 min-w-0 min-h-0 overflow-hidden">
    <SkillConfigPage
      :skill="selectedSkill" :userId="userId" :mainId="mainId"
      @back="emit('skillBack')" @saved="emit('skillSaved', $event)"
    />
  </div>
  <div v-else-if="currentView === 'composite-editor'" class="flex-1 min-w-0 min-h-0 overflow-hidden">
    <CompositeSkillEditor
      :skill="selectedSkill" :userId="userId"
      @back="emit('skillBack')" @saved="emit('compositeSaved', $event)"
      @remove="emit('removeSkill', $event)"
    />
  </div>
  <div v-else-if="currentView === 'scheduled-tasks'" class="flex-1 min-w-0 min-h-0 overflow-hidden">
    <ScheduledTaskPage
      :token="authToken" :sessions="sessions"
      :current-session-id="scheduledTaskInitialSessionId || currentSessionId"
      :timezone="timezoneValue" :initial-prompt="scheduledTaskInitialPrompt"
      :create-request-key="scheduledTaskCreateRequestKey"
      @back="emit('scheduledBack')" @open-session="emit('openSession', $event)"
    />
  </div>
  <div v-else-if="currentView === 'token-usage'" class="flex-1 min-w-0 min-h-0 overflow-hidden">
    <TokenUsagePage
      :user-id="userId" :main-id="mainId" :token="authToken"
      @back="emit('usageBack')"
    />
  </div>
  </template>
</template>
