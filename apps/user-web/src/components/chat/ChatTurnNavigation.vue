<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { t } from '../../composables/i18n'
import type { ChatMessage } from './chatMessage'
import { useCurrentChatTurn } from './useCurrentChatTurn'

const props = defineProps<{ messages: ChatMessage[]; container: HTMLElement | null; sessionId?: string; userId?: string; mainId?: string }>()
const emit = defineEmits<{ jump: [index: number] }>()
const currentTurn = useCurrentChatTurn(() => props.container, () => props.messages.length)
const preview = ref<number>()
const hoveredTurn = ref<number>()
const previewTop = ref(0)
const bookmarkButton = ref<HTMLButtonElement>()
const bookmarks = ref(new Set<string>())
const storageKey = computed(() => props.sessionId && props.userId
  ? `movo:chat-turn-bookmarks:${JSON.stringify([props.mainId ?? '', props.userId, props.sessionId])}`
  : undefined)
function excerpt(content: string) {
  return content.trim().replace(/\s+/g, ' ').slice(0, 220)
}

const turns = computed(() => {
  const entries: { index: number; id?: string; label: string; reply: string }[] = []
  props.messages.forEach((message, index) => {
    if (message.role === 'user' && !message.question_answer) {
      entries.push({ index, id: message.message_id || message._id, label: excerpt(message.content), reply: '' })
    } else if (message.role === 'assistant' && message.content.trim()) {
      const turn = entries.at(-1)
      if (turn) turn.reply = excerpt(message.content)
    }
  })
  return entries
})
const previewTurn = computed(() => turns.value.find(turn => turn.index === preview.value))
const emphasisIndex = computed(() => turns.value.findIndex(turn => turn.index === hoveredTurn.value))
const markWidths = ['26px', '20px', '14px', '10px', '6px']

function markWidth(index: number) {
  return markWidths[Math.min(emphasisIndex.value < 0 ? 4 : Math.abs(index - emphasisIndex.value), 4)]
}

watch(storageKey, key => {
  preview.value = undefined
  hoveredTurn.value = undefined
  bookmarks.value = new Set()
  if (!key) return
  try {
    const stored: unknown = JSON.parse(localStorage.getItem(key) ?? '[]')
    if (Array.isArray(stored)) bookmarks.value = new Set(stored.filter(item => typeof item === 'string'))
  } catch { /* Storage may be unavailable. */ }
}, { immediate: true })

function showPreview(index: number, event: Event) {
  const button = event.currentTarget as HTMLElement
  const navigation = button.closest('nav')
  if (!navigation) return
  previewTop.value = button.getBoundingClientRect().top - navigation.getBoundingClientRect().top
  preview.value = index
}

function hoverTurn(index: number, event: MouseEvent) {
  hoveredTurn.value = index
  showPreview(index, event)
}

function toggleBookmark(id: string) {
  const key = storageKey.value
  if (!key) return
  const updated = new Set(bookmarks.value)
  if (updated.has(id)) updated.delete(id)
  else updated.add(id)
  bookmarks.value = updated
  try {
    localStorage.setItem(key, JSON.stringify([...updated]))
  } catch { /* Keep the current view usable without storage. */ }
}

function handleFocusOut(event: FocusEvent) {
  if (!(event.currentTarget as HTMLElement).contains(event.relatedTarget as Node | null)) preview.value = undefined
}

async function focusBookmark(index: number, event: KeyboardEvent) {
  showPreview(index, event)
  await nextTick()
  bookmarkButton.value?.focus()
}
</script>

<template>
  <nav
    v-if="turns.length > 1" class="turn-navigation" :aria-label="t('chat.turn_navigation')"
    @mouseleave="preview = undefined" @focusout="handleFocusOut"
  >
    <div class="turn-navigation-list" @mouseleave="hoveredTurn = undefined" @scroll="preview = hoveredTurn = undefined">
      <button
        v-for="(turn, number) in turns" :key="turn.index"
        type="button" class="turn-navigation-button"
        :class="{ 'is-previewed': preview === turn.index, 'is-current': currentTurn === turn.index }"
        :style="{ '--turn-mark-width': markWidth(number) }"
        :aria-current="currentTurn === turn.index ? 'location' : undefined"
        :aria-label="`${t('chat.jump_to_turn')} ${number + 1}: ${turn.label}${turn.id && bookmarks.has(turn.id) ? `, ${t('chat.turn_bookmarked')}` : ''}`"
        :aria-keyshortcuts="turn.id && storageKey ? 'ArrowRight' : undefined"
        @mouseenter="hoverTurn(turn.index, $event)"
        @focus="showPreview(turn.index, $event)"
        @keydown.right.prevent="focusBookmark(turn.index, $event)"
        @click="emit('jump', turn.index)"
      >
        <span class="turn-navigation-mark" aria-hidden="true" />
        <span v-if="turn.id && bookmarks.has(turn.id)" class="turn-navigation-dot" aria-hidden="true" />
      </button>
    </div>
    <div v-if="previewTurn" class="turn-navigation-preview" :style="{ top: `${previewTop}px` }">
      <div class="turn-preview-copy">
        <div class="turn-preview-title">{{ previewTurn.label || t('chat.jump_to_turn') }}</div>
        <div v-if="previewTurn.reply" class="turn-preview-reply">{{ previewTurn.reply }}</div>
      </div>
      <button
        v-if="previewTurn.id && storageKey" ref="bookmarkButton" type="button" class="turn-bookmark"
        :aria-pressed="bookmarks.has(previewTurn.id)" :aria-label="t('chat.bookmark_turn')" :title="t('chat.bookmark_turn')"
        @click="toggleBookmark(previewTurn.id)"
      >
        <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" stroke="currentColor" stroke-width="1.7"
          :fill="bookmarks.has(previewTurn.id) ? 'currentColor' : 'none'">
          <path d="M7 4h10a2 2 0 0 1 2 2v14l-7-4-7 4V6a2 2 0 0 1 2-2Z" stroke-linejoin="round" />
        </svg>
      </button>
    </div>
  </nav>
</template>

<style scoped>
.turn-navigation {
  --turn-ink: #17263a;
  --turn-muted: #5d6e83;
  --turn-surface: #fff;
  --turn-line: #dce5ef;
  --turn-accent: #3168b4;
  --turn-hover: #eef4fc;
  position: absolute;
  inset-inline-start: 0.35rem;
  inset-block-start: 50%;
  transform: translateY(-50%);
  z-index: 10;
  color: var(--turn-ink);
}
:global(.theme-dark) .turn-navigation {
  --turn-ink: #edf3fc;
  --turn-muted: #aebcd0;
  --turn-surface: #202c3c;
  --turn-line: #3c4d63;
  --turn-accent: #9ac1ff;
  --turn-hover: #2b3b51;
}
.turn-navigation-list {
  max-height: 50vh;
  overflow-y: auto;
  scrollbar-width: thin;
}
.turn-navigation-button {
  --turn-mark-color: color-mix(in srgb, var(--turn-ink) 35%, var(--turn-surface));
  position: relative;
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 3px;
  padding-inline-start: 2px;
  width: 36px;
  height: 22px;
  border-radius: 5px;
}
.turn-navigation-button.is-previewed { --turn-mark-color: var(--turn-muted); }
.turn-navigation-button.is-current { --turn-mark-color: var(--turn-ink); }
.turn-navigation-mark {
  width: var(--turn-mark-width, 6px);
  height: 2px;
  border-radius: 2px;
  background: var(--turn-mark-color);
  transition: width 140ms ease;
}
.turn-navigation-dot {
  flex: none;
  width: 3px;
  height: 3px;
  border-radius: 50%;
  background: var(--turn-mark-color);
}
.turn-navigation-preview {
  position: absolute;
  inset-inline-start: calc(100% + 6px);
  display: flex;
  align-items: flex-start;
  gap: 12px;
  width: clamp(176px, 65vw, 312px);
  padding: 12px 12px 12px 14px;
  border: 1px solid var(--turn-line);
  border-radius: 12px;
  background: var(--turn-surface);
  box-shadow: 0 8px 24px #101c3220, 0 1px 3px #101c320a;
  font-size: 0.8125rem;
  line-height: 1.45;
  overflow-wrap: anywhere;
}
.turn-navigation-preview::before {
  content: '';
  position: absolute;
  inset: 0 100% 0 auto;
  width: 8px;
}
.turn-preview-copy { flex: 1; min-width: 0; }
.turn-preview-title { font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.turn-preview-reply {
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  overflow: hidden;
  margin-top: 4px;
  color: var(--turn-muted);
}
.turn-bookmark {
  flex: none;
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  margin: -3px -2px 0 0;
  border-radius: 6px;
  color: var(--turn-muted);
}
.turn-bookmark:is(:hover, :focus-visible, [aria-pressed='true']) {
  background: var(--turn-hover);
  color: var(--turn-accent);
}
</style>
