<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted } from 'vue'
import type { EvidenceBundleItem, EvidenceSourceItem } from '../../features/execution-v3/domain/delivery'
import { evidenceSourceStats, type EvidenceSourceGroup } from '../../features/execution-v3/domain/evidenceSourceGroups'
import { t } from '../../composables/i18n'

const props = defineProps<{
  open: boolean
  bundle: EvidenceBundleItem | null
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'open-source', source: EvidenceSourceItem): void
}>()

const sources = computed(() => props.bundle?.sources || [])
const openQuestions = computed(() => props.bundle?.open_questions || [])
const sourceStats = computed(() => evidenceSourceStats(sources.value))
const displaySummary = computed(() => {
  const total = sourceStats.value.total
  if (!total) return props.bundle?.summary || t('evidence.summary_fallback')
  if (sourceStats.value.fragments) {
    return t('evidence.summary_with_fragments', {
      sources: total,
      fragments: sourceStats.value.fragments,
    })
  }
  const parts: string[] = []
  if (sourceStats.value.web) parts.push(`${t('evidence.web')} ${sourceStats.value.web}`)
  if (sourceStats.value.internal) parts.push(`${t('evidence.internal')} ${sourceStats.value.internal}`)
  return `${t('evidence.summary_prefix')} ${total} ${t('evidence.summary_suffix')}${parts.length ? ` · ${parts.join(' · ')}` : ''}`
})

function sourceLabel(item: EvidenceSourceItem): string {
  const type = String(item.source_type || '')
  if (type === 'web') return item.source_name || t('evidence.web_source')
  if (type === 'document') return item.source_name || t('evidence.document_source')
  return item.source_name || t('evidence.internal_source')
}

function showSourceLabel(item: EvidenceSourceItem): boolean {
  const label = sourceLabel(item).trim()
  if (!label) return false
  const title = String(item.title || '').trim()
  return label !== title
}

function typeBadge(item: EvidenceSourceItem): string {
  const type = String(item.source_type || '')
  if (type === 'web') return t('evidence.web')
  if (type === 'document') return t('evidence.document')
  return t('evidence.internal')
}

function sourcePageText(item: EvidenceSourceItem): string {
  const page = item.page_no
  if (page === undefined || page === null || String(page).trim() === '') return ''
  return t('evidence.page_no', { page: String(page) })
}

function sourceChunkText(item: EvidenceSourceItem): string {
  if (!item.chunk_id) return ''
  const type = String(item.content_type || '').toLowerCase()
  if (type === 'table_row') return t('evidence.table_row')
  if (type.includes('table')) return t('evidence.table')
  return t('evidence.document_fragment')
}

function sourceLocatorTitle(item: EvidenceSourceItem): string {
  return item.citation_id || (item.document_id && item.chunk_id ? `${item.document_id}:${item.chunk_id}` : item.chunk_id || '')
}

function groupCitationLabel(group: EvidenceSourceGroup): string {
  const positions = group.sources
    .map((source) => sources.value.indexOf(source) + 1)
    .filter((position) => position > 0)
  if (!positions.length) return ''
  if (positions.length === 1) return `[${positions[0]}]`
  const consecutive = positions.every((position, index) => index === 0 || position === positions[index - 1] + 1)
  return consecutive
    ? `[${positions[0]}–${positions[positions.length - 1]}]`
    : `[${positions.join(', ')}]`
}

function canOpenSource(item: EvidenceSourceItem): boolean {
  return Boolean((item.document_id && item.chunk_id) || item.source_url)
}

function openSource(item: EvidenceSourceItem) {
  if (item.document_id && item.chunk_id) {
    emit('open-source', item)
    return
  }
  if (item.source_url) {
    window.open(item.source_url, '_blank', 'noopener,noreferrer')
  }
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape' && props.open) emit('close')
}

onMounted(() => window.addEventListener('keydown', onKeydown))
onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))
</script>

<template>
  <Teleport to="body">
    <div v-if="open && bundle" class="fixed inset-0 z-50">
      <button
        type="button"
        class="absolute inset-0 h-full w-full cursor-default bg-slate-950/20"
        :aria-label="t('ui.close')"
        @click="emit('close')"
      ></button>

      <aside
        class="absolute right-0 top-0 flex h-full w-full max-w-full flex-col bg-white shadow-2xl sm:w-[480px]"
        role="dialog"
        aria-modal="true"
        :aria-label="t('evidence.drawer_title')"
      >
        <header class="flex items-start justify-between gap-4 border-b border-slate-200 px-5 py-4">
          <div>
            <h2 class="text-base font-semibold text-slate-950">{{ t('evidence.drawer_title') }}</h2>
            <p class="mt-1 text-sm leading-6 text-slate-600">
              {{ displaySummary }}
            </p>
          </div>
          <button
            type="button"
            class="flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-slate-500 transition hover:bg-slate-100 hover:text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500"
            :aria-label="t('ui.close')"
            @click="emit('close')"
          >
            <svg viewBox="0 0 24 24" class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
              <path d="M18 6 6 18"></path>
              <path d="m6 6 12 12"></path>
            </svg>
          </button>
        </header>

        <div class="flex-1 overflow-y-auto px-5 py-5">
          <div class="grid grid-cols-3 gap-2">
            <div class="rounded-lg border border-slate-200 px-3 py-2">
              <div class="text-lg font-semibold text-slate-950">{{ sourceStats.total }}</div>
              <div class="text-xs text-slate-500">{{ t('evidence.total_sources') }}</div>
            </div>
            <div class="rounded-lg border border-slate-200 px-3 py-2">
              <div class="text-lg font-semibold text-slate-950">{{ sourceStats.web }}</div>
              <div class="text-xs text-slate-500">{{ t('evidence.web') }}</div>
            </div>
            <div class="rounded-lg border border-slate-200 px-3 py-2">
              <div class="text-lg font-semibold text-slate-950">{{ sourceStats.internal }}</div>
              <div class="text-xs text-slate-500">{{ t('evidence.internal') }}</div>
            </div>
          </div>

          <section v-if="sourceStats.groups.length" class="mt-6">
            <h3 class="text-sm font-semibold text-slate-950">{{ t('evidence.source_list') }}</h3>
            <div class="mt-3 space-y-3">
              <article
                v-for="(group, idx) in sourceStats.groups"
                :key="group.key"
                class="rounded-lg border border-slate-200 p-3"
              >
                <div class="flex items-start justify-between gap-3">
                  <div class="min-w-0">
                    <div class="text-sm font-semibold leading-6 text-slate-950">{{ group.primary.title || sourceLabel(group.primary) }}</div>
                    <div class="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                      <span class="rounded-full bg-slate-100 px-2 py-1 text-slate-600">{{ typeBadge(group.primary) }}</span>
                      <span v-if="showSourceLabel(group.primary)" class="truncate">{{ sourceLabel(group.primary) }}</span>
                      <span v-if="group.sources.length > 1" class="rounded-full bg-blue-50 px-2 py-1 text-blue-700">
                        {{ t('evidence.fragment_count', { count: group.sources.length }) }}
                      </span>
                      <span v-else-if="sourcePageText(group.primary)" class="rounded-full bg-blue-50 px-2 py-1 text-blue-700">{{ sourcePageText(group.primary) }}</span>
                      <span
                        v-if="group.sources.length === 1 && sourceChunkText(group.primary)"
                        class="rounded-full bg-slate-50 px-2 py-1 text-slate-600"
                        :title="sourceLocatorTitle(group.primary)"
                      >{{ sourceChunkText(group.primary) }}</span>
                    </div>
                  </div>
                  <div class="shrink-0 text-xs font-medium text-slate-500">{{ groupCitationLabel(group) || `[${idx + 1}]` }}</div>
                </div>
                <button
                  v-if="canOpenSource(group.primary)"
                  type="button"
                  class="mt-3 inline-flex min-h-11 items-center gap-2 rounded-md text-sm font-medium text-blue-600 hover:text-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  @click="openSource(group.primary)"
                >
                  <svg viewBox="0 0 24 24" class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                    <path d="M14 3h7v7"></path>
                    <path d="M10 14 21 3"></path>
                    <path d="M21 14v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5"></path>
                  </svg>
                  {{ t('evidence.open_source') }}
                </button>
              </article>
            </div>
          </section>

          <section v-if="openQuestions.length" class="mt-6">
            <h3 class="text-sm font-semibold text-slate-950">{{ t('evidence.open_questions') }}</h3>
            <ul class="mt-3 space-y-2">
              <li
                v-for="(item, idx) in openQuestions"
                :key="idx"
                class="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm leading-6 text-amber-900"
              >
                {{ item }}
              </li>
            </ul>
          </section>
        </div>
      </aside>
    </div>
  </Teleport>
</template>
