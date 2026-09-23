<template>
  <header class="flex h-12 shrink-0 items-center justify-between gap-3 border-b border-gray-200 bg-white px-4">
    <span class="min-w-0 flex-1 truncate text-[13px] font-semibold text-slate-700" :title="headerTitle">{{ headerTitle }}</span>
    <div class="flex shrink-0 items-center gap-1">
      <button
        type="button"
        class="relative grid h-9 w-9 place-items-center rounded-lg border-0 bg-transparent text-slate-600 transition-colors hover:bg-gray-100 hover:text-blue-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-200"
        :aria-label="t('session.share.participants_count', { count: participantCount })"
        :title="t('session.share.participants_count', { count: participantCount })"
        @click="shareDialogOpen = true"
      >
        <svg class="h-[18px] w-[18px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>
        </svg>
        <span v-if="participantCount > 0" class="absolute top-px right-px min-w-[14px] rounded-full border border-white bg-blue-600 px-[3px] text-center text-[8px] leading-[12px] text-white">{{ participantCount > 99 ? '99+' : participantCount }}</span>
      </button>
      <button
        v-if="canShare"
        type="button"
        class="grid h-9 w-9 place-items-center rounded-lg border-0 bg-transparent text-slate-600 transition-colors hover:bg-gray-100 hover:text-blue-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-200"
        :aria-label="t('session.share.action')"
        :title="t('session.share.action')"
        @click="shareDialogOpen = true"
      >
        <svg class="h-[18px] w-[18px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"/><polyline points="16 6 12 2 8 6"/><line x1="12" x2="12" y1="2" y2="15"/>
        </svg>
      </button>
    </div>
    <SessionShareDialog
      :show="shareDialogOpen"
      :mode="viewerMode"
      :session-id="sessionId"
      @update:show="shareDialogOpen = $event"
      @removed="reloadDetail"
      @revoked="reloadDetail"
      @left="onLeft"
    />
  </header>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import SessionShareDialog from '../session/SessionShareDialog.vue'
import { getSession, type SessionDetail } from '../../api/sessions'
import { t } from '../../composables/i18n'

const props = defineProps<{
  sessionId: string | null
  /** Pre-fetch title from the parent's session list (same source as the desktop chrome title). */
  title: string
  /** Viewer identity for the detail fetch's userId query param; the server resolves the viewer from the bearer token. */
  userId: string
  mainId: string
  authToken: string | null
}>()

// T24 wiring: left hands off to the parent (App.vue), which clears the leaved
// session's pane and refreshes the session lists; the header unmounts with it.
const emit = defineEmits<{ left: [sessionId: string] }>()
// T9 runtime contract: GET /sessions/{id} carries the VIEWER's access, owner_user_id,
// participant_count and execution_location for owner-viewed-own and participant-viewed-shared
// sessions alike. The TS type lags (todo 25 promotes the fields into SessionSummary) —
// read through this local widening intersection (optional fields keep SessionDetail
// assignable, no cast).
type SessionSharingDetail = SessionDetail & {
  access?: 'owner' | 'shared'
  owner_user_id?: string
  participant_count?: number
}

const detail = ref<SessionSharingDetail | null>(null)
const shareDialogOpen = ref(false)
let detailSequence = 0

watch(() => props.sessionId, (sessionId) => {
  detailSequence += 1
  detail.value = null
  shareDialogOpen.value = false
  if (!sessionId) return
  void loadDetail(sessionId)
}, { immediate: true })

async function loadDetail(sessionId: string) {
  const sequence = detailSequence
  try {
    const loaded = await getSession(sessionId, props.userId, props.mainId || undefined, props.authToken)
    if (sequence !== detailSequence) return
    detail.value = loaded
  } catch {
    // The viewer cannot see the session (removed member, 401, network failure) —
    // the header stays title-only; the authoritative gates are server-side.
    if (sequence !== detailSequence) return
    detail.value = null
  }
}

// detail.access is the VIEWER's access (T9). Absent falls back to "owner" — the
// historical default; the server's 403 (session_share_owner_required) is the
// authoritative gate for any stale-payload bypass.
const viewerMode = computed<'owner' | 'participant'>(() => (
  detail.value?.access === 'shared' ? 'participant' : 'owner'
))

// Server payload only (T9 detail: true active non-owner participant row count);
// never a client count.
const participantCount = computed(() => detail.value?.participant_count ?? 0)

// Best-effort shareability: session_runtime_context attaches execution_location
// through a viewer-scoped binding query, so it is usually absent for
// non-last-speaker viewers. Absent = unknown -> show; a reported desktop /
// remote_sandbox location hides the icon. The authoritative gate is the
// server-side 409 (session_share_no_binding / session_share_not_server).
const canShare = computed(() => {
  if (viewerMode.value !== 'owner') return false
  const location = detail.value?.execution_location
  if (!location) return true
  return location === 'server'
})

const headerTitle = computed(() => detail.value?.title || props.title || '')

// T24 wiring: the dialog's mutations change header-visible data — removed/revoked
// refresh the participant count (a mutation can also bound staleness from an
// out-of-band join through the link), so re-fetch the session detail; left hands
// off to the parent, which clears the pane (the header unmounts with it).
function reloadDetail() {
  if (!props.sessionId) return
  void loadDetail(props.sessionId)
}

function onLeft() {
  const sessionId = props.sessionId
  if (!sessionId) return
  emit('left', sessionId)
}
</script>
