<script setup lang="ts">
import { NInput } from 'naive-ui'
import type { SessionSummary } from '../api/sessions'
import type { ProjectGroup } from '../composables/code/projectHistoryVisibility'
import { t } from '../composables/i18n'

defineProps<{
  pinnedSessions: SessionSummary[]
  historyItems: SessionSummary[]
  sharedSessions: SessionSummary[]
  projectHistoryGroups: ProjectGroup[]
  currentSessionId: string | null
  currentView: string
  sessionsLoading: boolean
  sessionsLoadingMore: boolean
  sessionsHasMore: boolean
  sharedSessionsLoading: boolean
  sharedSessionsLoadingMore: boolean
  sharedSessionsHasMore: boolean
  sessionPageSize: number
  trimmedSessionSearchQuery: string
  editingSessionId: string | null
  renamingSessionId: string | null
  deletingSessionId: string | null
  canUseCode: boolean
  supportsLocalCodeProjects: boolean
  localWorkspacePicker: boolean
  isSessionPinned: (id: string) => boolean
  isUnavailableProjectHistory: (id: string) => boolean
  sessionNeedsHumanAssistance: (id: string) => boolean
  sessionScheduledIsRunning: (id: string) => boolean
  sessionIsRunning: (id: string) => boolean
  sessionIsUnread: (id: string) => boolean
  displaySessionTitle: (session: SessionSummary) => string
  compactSessionTitle: (session: SessionSummary) => string
  selectSession: (id: string) => unknown
  toggleSessionPin: (id: string) => unknown
  startEditSessionTitle: (session: SessionSummary) => unknown
  commitSessionTitleEdit: (session: SessionSummary) => unknown
  cancelSessionTitleEdit: () => unknown
  handleDeleteSession: (id: string) => unknown
  loadSessions: (refresh: boolean) => unknown
  loadSharedSessions: (refresh: boolean) => unknown
  projectHistoryExpanded: (workspaceId: string) => boolean
  toggleProjectHistory: (workspaceId: string) => unknown
  createProject: () => unknown
}>()
const pinnedHistoryExpanded = defineModel<boolean>('pinnedExpanded', { required: true })
const normalHistoryExpanded = defineModel<boolean>('normalExpanded', { required: true })
const sharedHistoryExpanded = defineModel<boolean>('sharedExpanded', { required: true })
const editingSessionTitle = defineModel<string>('editingTitle', { required: true })
</script>

<template>
      <section v-if="pinnedSessions.length" class="px-3 pt-2">
        <button type="button" class="flex w-full items-center gap-1 px-2 pb-1 text-left text-[10px] font-bold uppercase tracking-[0.1em] text-gray-400" :aria-expanded="pinnedHistoryExpanded" @click="pinnedHistoryExpanded = !pinnedHistoryExpanded">
          <span>{{ t('app.pinned') }}</span>
          <svg class="h-3.5 w-3.5 transition-transform duration-150" :class="pinnedHistoryExpanded ? 'rotate-90' : ''" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="m5 3 5 5-5 5"/></svg>
        </button>
        <div v-if="pinnedHistoryExpanded" class="max-h-40 overflow-y-auto">
          <div v-for="session in pinnedSessions" :key="session.id" class="group flex items-center gap-1 rounded-lg px-2 py-1 text-sm text-gray-600 hover:bg-gray-200/50">
            <button type="button" class="min-w-0 flex-1 truncate text-left" :title="displaySessionTitle(session)" @click="selectSession(session.id)">{{ compactSessionTitle(session) }}</button>
            <button type="button" class="shrink-0 text-blue-500 opacity-0 group-hover:opacity-100 focus:opacity-100" :aria-label="t('app.unpin')" :title="t('app.unpin')" @click="toggleSessionPin(session.id)"><svg viewBox="0 0 24 24" class="h-3.5 w-3.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 3h6l-1 6 3 3v2H7v-2l3-3-1-6Z"/><path d="M12 14v7"/></svg></button>
          </div>
        </div>
      </section>
      <!-- Scripts Section -->
      <button
        type="button"
        class="group mt-4 flex w-full items-center gap-1 px-5 pb-1 text-left text-[10px] font-bold uppercase tracking-[0.1em] text-gray-400"
        :aria-expanded="normalHistoryExpanded"
        @click="normalHistoryExpanded = !normalHistoryExpanded"
      >
        <span>{{ t('app.conversations') }}</span>
        <svg class="h-3.5 w-3.5 opacity-100 transition-transform duration-150" :class="normalHistoryExpanded ? 'rotate-90' : ''" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="m5 3 5 5-5 5"/></svg>
      </button>
      <div class="flex-1 overflow-y-auto px-3 space-y-1 custom-scrollbar history-scrollbar">
        <div
          v-if="normalHistoryExpanded && sessionsLoading"
          class="px-3 py-4 text-xs text-gray-400 animate-pulse italic text-center"
        >
          {{ t('app.sidebar.loading_history') }}
        </div>
        <div
          v-for="session in normalHistoryExpanded ? historyItems.filter((item) => !isSessionPinned(item.id)) : []"
          :key="session.id"
          class="group w-full text-left px-2.5 py-1.5 rounded-lg transition-all border border-transparent"
          :class="session.id === currentSessionId && currentView === 'chat'
            ? 'bg-white text-blue-700 shadow-sm border-gray-200 font-semibold'
            : 'text-gray-600 hover:bg-gray-200/50 hover:text-gray-900'"
          @click="editingSessionId !== session.id && selectSession(session.id)"
          @keydown.enter.prevent="editingSessionId !== session.id && selectSession(session.id)"
          @keydown.space.prevent="editingSessionId !== session.id && selectSession(session.id)"
          role="button"
          tabindex="0"
        >
          <div class="flex min-w-0 items-center gap-2">
            <n-input
              v-if="editingSessionId === session.id"
              v-model:value="editingSessionTitle"
              size="small"
              class="min-w-0 flex-1"
              :data-session-title-input="session.id"
              :disabled="renamingSessionId === session.id"
              @click.stop
              @dblclick.stop
              @blur="commitSessionTitleEdit(session)"
              @keydown.enter.prevent="commitSessionTitleEdit(session)"
              @keydown.esc.prevent="cancelSessionTitleEdit"
            />
            <div
              v-else
              class="min-w-0 flex-1 text-[13px] truncate"
              :title="displaySessionTitle(session)"
              @dblclick.stop="startEditSessionTitle(session)"
            >
              {{ compactSessionTitle(session) }}
            </div>
            <span v-if="isUnavailableProjectHistory(session.id)" class="shrink-0 rounded bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-500" :title="t('app.sidebar.project_folder_unavailable')">{{ t('app.sidebar.project_history_only') }}</span>
            <span
              v-if="sessionNeedsHumanAssistance(session.id)"
              class="shrink-0 rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold text-amber-700"
              :aria-label="t('app.sidebar.session_needs_assistance')"
              :title="t('app.sidebar.session_needs_assistance')"
            >
              {{ t('app.sidebar.session_needs_assistance_short') }}
            </span>
            <div
              v-else-if="sessionScheduledIsRunning(session.id)"
              class="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-blue-50 text-blue-600"
              :aria-label="t('projectDialog.scheduledRunning')"
              :title="t('projectDialog.scheduledRunning')"
            >
              <svg viewBox="0 0 24 24" class="h-3.5 w-3.5 animate-pulse" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>
            </div>
            <div
              v-else-if="sessionIsRunning(session.id)"
              class="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-blue-50"
              :aria-label="t('app.sidebar.session_running')"
              :title="t('app.sidebar.session_running')"
            >
              <span class="h-1.5 w-1.5 rounded-full bg-blue-500 animate-pulse"></span>
            </div>
            <span
              v-else-if="sessionIsUnread(session.id)"
              class="h-2 w-2 shrink-0 rounded-full bg-blue-500"
              :aria-label="t('app.sidebar.session_unread')"
              :title="t('app.sidebar.session_unread')"
            ></span>
            <button v-if="editingSessionId !== session.id" type="button" class="shrink-0 text-gray-400 opacity-0 group-hover:opacity-100 focus:opacity-100 hover:text-blue-600" :aria-label="t('app.pin')" :title="t('app.pin')" @click.stop="toggleSessionPin(session.id)"><svg viewBox="0 0 24 24" class="h-3.5 w-3.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 3h6l-1 6 3 3v2H7v-2l3-3-1-6Z"/><path d="M12 14v7"/></svg></button>
            <button
              type="button"
              class="shrink-0 overflow-hidden rounded-md p-0 text-gray-400 opacity-0 transition-all hover:bg-gray-200 hover:text-red-500 group-hover:w-6 group-hover:p-1 group-hover:opacity-100"
              :class="deletingSessionId === session.id ? 'w-6 !p-1 !opacity-100 text-red-500' : 'w-0'"
              :disabled="deletingSessionId === session.id"
              @click.stop="handleDeleteSession(session.id)"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/></svg>
            </button>
          </div>
        </div>
        <button
          v-if="normalHistoryExpanded && !trimmedSessionSearchQuery && !sessionsLoading && sessionsHasMore && historyItems.length >= sessionPageSize"
          class="w-full text-left px-2.5 py-1 text-[11px] text-gray-400 hover:text-gray-600 disabled:opacity-60 disabled:cursor-not-allowed"
          :disabled="sessionsLoadingMore"
          @click="loadSessions(false)"
        >
          {{ sessionsLoadingMore ? t('ui.loading') : t('app.sidebar.load_more') }}
        </button>
        <!-- Shared conversations follow ordinary conversations. -->
        <template v-if="sharedSessions.length">
          <button type="button" class="group mt-4 flex w-full items-center gap-1 px-2 pb-1 text-left text-[10px] font-bold uppercase tracking-[0.1em] text-gray-400" :aria-expanded="sharedHistoryExpanded" @click="sharedHistoryExpanded = !sharedHistoryExpanded">
            <span>{{ t('session.sharedWithMe.title') }}</span>
            <svg class="h-3.5 w-3.5 transition-transform duration-150" :class="sharedHistoryExpanded ? 'rotate-90' : ''" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="m5 3 5 5-5 5"/></svg>
          </button>
          <div
            v-for="session in sharedHistoryExpanded ? sharedSessions.filter((item) => !isSessionPinned(item.id)) : []"
            :key="session.id"
            class="group w-full text-left px-2.5 py-1.5 rounded-lg transition-all border border-transparent"
            :class="session.id === currentSessionId && currentView === 'chat'
              ? 'bg-white text-blue-700 shadow-sm border-gray-200 font-semibold'
              : 'text-gray-600 hover:bg-gray-200/50 hover:text-gray-900'"
            @click="selectSession(session.id)"
            @keydown.enter.prevent="selectSession(session.id)"
            @keydown.space.prevent="selectSession(session.id)"
            role="button"
            tabindex="0"
          >
            <div class="flex min-w-0 items-center gap-2">
              <div class="min-w-0 flex-1 text-[13px] truncate" :title="displaySessionTitle(session)">
                {{ compactSessionTitle(session) }}
              </div>
              <span
                class="shrink-0 rounded-full bg-blue-50 px-2 py-0.5 text-[10px] font-medium text-blue-600"
                :aria-label="t('session.sharedWithMe.badge')"
                :title="t('session.sharedWithMe.badge')"
              >
                {{ t('session.sharedWithMe.badge') }}
              </span>
              <button type="button" class="shrink-0 text-gray-400 opacity-0 group-hover:opacity-100 focus:opacity-100 hover:text-blue-600" :aria-label="t('app.pin')" :title="t('app.pin')" @click.stop="toggleSessionPin(session.id)"><svg viewBox="0 0 24 24" class="h-3.5 w-3.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 3h6l-1 6 3 3v2H7v-2l3-3-1-6Z"/><path d="M12 14v7"/></svg></button>
              <span
                v-if="session.shared_unread"
                class="h-2 w-2 shrink-0 rounded-full bg-blue-500"
                :aria-label="t('session.sharedWithMe.unread')"
                :title="t('session.sharedWithMe.unread')"
              ></span>
            </div>
          </div>
          <button
            v-if="sharedHistoryExpanded && !sharedSessionsLoading && sharedSessionsHasMore && sharedSessions.length >= sessionPageSize"
            class="w-full text-left px-2.5 py-1 text-[11px] text-gray-400 hover:text-gray-600 disabled:opacity-60 disabled:cursor-not-allowed"
            :disabled="sharedSessionsLoadingMore"
            @click="loadSharedSessions(false)"
          >
            {{ sharedSessionsLoadingMore ? t('ui.loading') : t('app.sidebar.load_more') }}
          </button>
        </template>
        <slot name="desktop-plugin-shortcuts" />
        <section v-if="canUseCode && supportsLocalCodeProjects" class="space-y-0.5 pt-4" :aria-label="t('projectDialog.projectsLabel')">
          <div class="group flex items-center justify-between px-2 pb-1 text-[10px] font-bold uppercase tracking-[0.1em] text-gray-400">
            <span>{{ t('app.projects') }}</span>
            <button v-if="canUseCode && localWorkspacePicker" type="button" class="flex h-4 w-4 items-center justify-center rounded text-blue-600 opacity-0 transition-opacity hover:bg-blue-50 group-hover:opacity-100" :aria-label="t('app.createProject')" :title="t('app.createProject')" @click="createProject"><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M8 3v10M3 8h10"/></svg></button>
          </div>
          <section v-for="group in projectHistoryGroups" :key="group.workspaceId" class="space-y-0.5">
            <button type="button" class="group flex w-full min-w-0 items-center gap-2 rounded-xl px-3 py-2 text-left text-sm font-semibold text-slate-500 hover:bg-gray-200/50 hover:text-slate-700" :aria-expanded="projectHistoryExpanded(group.workspaceId)" :title="group.title" @click="toggleProjectHistory(group.workspaceId)">
              <svg v-if="projectHistoryExpanded(group.workspaceId)" class="h-4 w-4 shrink-0 text-slate-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M3 7.5h6l2 2h10v9.5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7.5Z"/></svg>
              <svg v-else class="h-4 w-4 shrink-0 text-slate-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M3 7.5h6l2 2h10v9.5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7.5Z"/><path d="M3 7.5V6a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v1.5"/></svg>
              <span class="truncate">{{ group.title }}</span>
            </button>
            <div
              v-for="session in projectHistoryExpanded(group.workspaceId) ? group.items.filter((item) => !isSessionPinned(item.id)) : []"
              :key="session.id"
              class="group flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-[13px] transition-all"
              :class="session.id === currentSessionId && currentView === 'chat' ? 'bg-white font-semibold text-blue-700 shadow-sm ring-1 ring-gray-200' : 'text-gray-600 hover:bg-gray-200/50 hover:text-gray-900'"
              :title="displaySessionTitle(session)"
            >
              <button type="button" class="min-w-0 flex-1 truncate text-left" @click="selectSession(session.id)">{{ compactSessionTitle(session) }}</button>
              <button type="button" class="shrink-0 text-gray-400 opacity-0 group-hover:opacity-100 focus:opacity-100 hover:text-blue-600" :aria-label="t('app.pin')" :title="t('app.pin')" @click.stop="toggleSessionPin(session.id)"><svg viewBox="0 0 24 24" class="h-3.5 w-3.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 3h6l-1 6 3 3v2H7v-2l3-3-1-6Z"/><path d="M12 14v7"/></svg></button>
              <span v-if="sessionIsRunning(session.id)" class="h-1.5 w-1.5 shrink-0 rounded-full bg-blue-500 animate-pulse"></span>
              <span v-else-if="sessionIsUnread(session.id)" class="h-2 w-2 shrink-0 rounded-full bg-blue-500"></span>
            </div>
          </section>
        </section>
      </div>

</template>
