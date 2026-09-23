<template>
  <n-modal :show="show" preset="card" :title="t('session.share.title')" style="width: min(600px, calc(100vw - 32px))" @update:show="emit('update:show', $event)">
    <div class="share-content">
      <div v-if="mode === 'owner'">
        <div class="section-label">{{ t('session.share.link_label') }}</div>
        <template v-if="!share">
          <div class="link-settings">
            <n-select v-model:value="expiresInDays" :options="expiryOptions" size="small" />
            <n-button secondary size="small" :loading="creating" @click="createLink">{{ t('session.share.create') }}</n-button>
          </div>
          <p class="hint">{{ t('session.share.link_hint') }}</p>
        </template>
        <template v-else>
          <n-input :value="shareUrl" readonly size="small">
            <template #suffix><n-button text type="primary" @click="copyLink">{{ t('session.share.copy') }}</n-button></template>
          </n-input>
          <p class="hint">{{ expiryText }}</p>
          <n-button text type="error" size="tiny" class="revoke-link" :loading="revoking" @click="revoke">{{ t('session.share.revoke') }}</n-button>
        </template>
      </div>
      <div>
        <div class="section-label">{{ t('session.share.members') }}</div>
        <div class="member-list">
          <div v-for="member in members" :key="member.user_id" class="member-row">
            <div class="member-info">
              <strong>{{ member.display_name }}</strong>
              <span>{{ formatJoinedAt(member.joined_at) }}</span>
            </div>
            <div class="member-actions">
              <span class="member-role" :class="{ 'is-owner': member.role === 'owner' }">{{ roleLabel(member.role) }}</span>
              <n-button v-if="mode === 'owner' && member.role !== 'owner'" text type="error" size="tiny" :loading="removingUserId === member.user_id" @click="removeMember(member)">{{ t('session.share.remove') }}</n-button>
            </div>
          </div>
        </div>
        <p v-if="isEmpty" class="hint">{{ t('session.share.empty') }}</p>
      </div>
    </div>
    <template #footer>
      <n-space justify="end">
        <n-button @click="emit('update:show', false)">{{ t('ui.close') }}</n-button>
        <n-button v-if="mode === 'participant'" type="error" :loading="leaving" @click="leave">{{ t('session.share.leave') }}</n-button>
      </n-space>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { NButton, NInput, NModal, NSelect, NSpace, useMessage } from 'naive-ui'
import type { SessionShareCreated, SessionShareError, SessionShareMember } from '../../api/sessionSharing'
import { createSessionShare, leaveSession, listSessionParticipants, removeParticipant, revokeSessionShare } from '../../api/sessionSharing'
import { t } from '../../composables/i18n'
import { formatAppShortDateTime } from '../../composables/appTimezone'
import { copyTextToClipboard } from '../../utils/copyTextToClipboard'

const props = defineProps<{ show: boolean; mode: 'owner' | 'participant'; sessionId: string | null }>()
// T24 wiring: the hosting header (ChatSessionHeader) re-fetches its session detail on
// removed/revoked so the participant count reflects the mutation; left hands off to the
// parent to clear the pane and refresh the session lists. create emits nothing — a new
// link changes no header-visible field (the share state is dialog-local).
const emit = defineEmits<{ 'update:show': [value: boolean]; left: []; removed: []; revoked: [] }>()
const message = useMessage()

const share = ref<SessionShareCreated | null>(null)
const shareSessionId = ref<string | null>(null)
const members = ref<SessionShareMember[]>([])
const membersLoading = ref(false)
const creating = ref(false)
const revoking = ref(false)
const leaving = ref(false)
const removingUserId = ref('')
const expiresInDays = ref(30)

const shareUrl = computed(() => {
  if (!share.value || typeof window === 'undefined') return ''
  const url = new URL('/', window.location.origin)
  url.searchParams.set('session-share', share.value.token)
  return url.toString()
})
const expiryOptions = computed(() => [
  { label: t('session.share.expiry_7'), value: 7 }, { label: t('session.share.expiry_30'), value: 30 }, { label: t('session.share.expiry_90'), value: 90 },
])
const expiryText = computed(() => t('session.share.expires_at', { date: formatAppShortDateTime(share.value?.expires_at) }))
const otherMembers = computed(() => members.value.filter((member) => member.role !== 'owner'))
const isEmpty = computed(() => {
  if (membersLoading.value) return false
  return props.mode === 'owner' ? otherMembers.value.length === 0 : members.value.length === 0
})

watch(() => [props.show, props.sessionId, props.mode], () => {
  if (!props.show) return
  if (shareSessionId.value !== props.sessionId) {
    share.value = null
    shareSessionId.value = null
  }
  members.value = []
  void loadMembers()
})

function roleLabel(role: SessionShareMember['role']): string {
  return role === 'owner' ? t('session.share.role_owner') : t('session.share.role_participant')
}

function formatJoinedAt(value: string | null): string {
  return formatAppShortDateTime(value)
}

function shareErrorMessage(error: SessionShareError): string {
  switch (error.code) {
    case 'session_not_found':
    case 'session_share_not_found':
      return t('session.share.error_not_found')
    case 'session_share_owner_required':
      return t('session.share.error_owner_required')
    case 'session_share_participant_required':
      return t('session.share.error_participant_required')
    case 'session_share_no_binding':
      return t('session.share.error_no_binding')
    case 'session_share_not_server':
      return t('session.share.error_not_server')
    case 'session_share_inactive':
      return t('session.share.error_inactive')
    case 'session_share_token_required':
      return t('session.share.error_token_required')
    case 'http_error':
      return t('session.share.error_generic')
    default: {
      const _exhaustive: never = error.code
      void _exhaustive
      return t('session.share.error_generic')
    }
  }
}

async function loadMembers() {
  const sessionId = props.sessionId
  if (!sessionId) return
  membersLoading.value = true
  try {
    const result = await listSessionParticipants(sessionId)
    if (sessionId !== props.sessionId) return
    if (result.ok === false) {
      message.error(shareErrorMessage(result.error))
      return
    }
    members.value = result.data.items
  } finally {
    if (sessionId === props.sessionId) membersLoading.value = false
  }
}

async function createLink() {
  if (!props.sessionId) return
  creating.value = true
  try {
    const result = await createSessionShare(props.sessionId, expiresInDays.value)
    if (result.ok === false) {
      message.error(shareErrorMessage(result.error))
      return
    }
    share.value = result.data
    shareSessionId.value = props.sessionId
  } finally {
    creating.value = false
  }
}

async function copyLink() {
  try { await copyTextToClipboard(shareUrl.value); message.success(t('session.share.copied')) }
  catch { message.error(t('session.share.copy_failed')) }
}

async function revoke() {
  if (!props.sessionId || !share.value) return
  revoking.value = true
  try {
    const result = await revokeSessionShare(props.sessionId)
    if (result.ok === false) {
      message.error(shareErrorMessage(result.error))
      return
    }
    message.success(t('session.share.revoked'))
    share.value = null
    shareSessionId.value = null
    emit('revoked')
  } finally {
    revoking.value = false
  }
}

async function leave() {
  if (!props.sessionId) return
  leaving.value = true
  try {
    const result = await leaveSession(props.sessionId)
    if (result.ok === false) {
      message.error(shareErrorMessage(result.error))
      return
    }
    message.success(t('session.share.left'))
    emit('update:show', false)
    emit('left')
  } finally {
    leaving.value = false
  }
}

async function removeMember(member: SessionShareMember) {
  if (!props.sessionId) return
  removingUserId.value = member.user_id
  try {
    const result = await removeParticipant(props.sessionId, member.user_id)
    if (result.ok === false) {
      message.error(shareErrorMessage(result.error))
      return
    }
    message.success(t('session.share.removed'))
    await loadMembers()
    emit('removed')
  } finally {
    removingUserId.value = ''
  }
}
</script>

<style scoped>
.share-content { display: grid; gap: 20px; }
.section-label { margin-bottom: 8px; color: #344054; font-size: 13px; font-weight: 700; }
.hint { margin: 7px 0 0; color: #7a8699; font-size: 12px; line-height: 1.55; }
.link-settings { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.link-settings :deep(.n-select) { width: 150px; }
.revoke-link { margin-top: 8px; }
.member-list { display: grid; gap: 8px; }
.member-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 10px 12px; border: 1px solid #e9edf5; border-radius: 10px; background: #f8faff; }
.member-info { min-width: 0; display: grid; gap: 2px; }
.member-info strong { color: #18233b; font-size: 14px; }
.member-info span { color: #667085; font-size: 12px; }
.member-actions { display: flex; align-items: center; gap: 10px; flex: 0 0 auto; }
.member-role { color: #667085; font-size: 12px; }
.member-role.is-owner { color: #2459e8; font-weight: 600; }
</style>
