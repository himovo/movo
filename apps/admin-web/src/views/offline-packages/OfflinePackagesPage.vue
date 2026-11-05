<template>
  <main class="offline-page">
    <div class="offline-toolbar">
      <div>
        <h1>{{ t('offline.title') }}</h1>
        <p>{{ t('offline.description') }}</p>
        <p>{{ t('offline.scopeHint') }}</p>
      </div>
      <div class="offline-actions">
        <n-button :loading="loading" @click="load">{{ t('offline.refresh') }}</n-button>
        <n-button :loading="transferring" :disabled="!inventory" @click="download">{{ t('offline.export') }}</n-button>
        <n-button :loading="transferring" :disabled="!selectedRecords.length" @click="downloadSelected">{{ t('offline.exportSelected') }}</n-button>
        <n-button type="primary" :loading="transferring" @click="fileInput?.click()">{{ t('offline.import') }}</n-button>
        <input ref="fileInput" type="file" accept=".zip,application/zip" hidden @change="upload" />
      </div>
    </div>

    <n-spin :show="loading">
      <section class="offline-card mode-card">
        <div>
          <strong>{{ t('offline.offlineOnly') }}</strong>
          <p>{{ t('offline.offlineHint') }}</p>
        </div>
        <n-switch :value="inventory?.offlineOnly || false" :disabled="!inventory || saving" @update:value="updateMode" />
      </section>
      <section class="offline-card">
        <div class="inventory-head"><strong>{{ t('offline.platform') }}</strong><span>{{ inventory ? `${inventory.os} / ${inventory.platform}` : '—' }}</span></div>
        <div class="package-table">
          <div v-for="row in rows" :key="row.key" class="package-row">
            <strong>{{ t(row.label) }}</strong>
            <span>{{ t('offline.files') }} · {{ inventory ? count(row.keys) : '—' }}</span>
            <span>{{ t('offline.size') }} · {{ inventory ? size(bytes(row.keys)) : '—' }}</span>
          </div>
        </div>
      </section>
      <section class="offline-card">
        <strong>{{ t('offline.collections') }}</strong>
        <p v-if="!inventory?.collections?.length" class="empty-records">{{ t('offline.noCollections') }}</p>
        <div v-for="collection in inventory?.collections || []" :key="collection.recordId" class="collection-row">
          <div class="collection-head">
            <n-checkbox :checked="selectedRecords.includes(collection.recordId)" @update:checked="toggleRecord(collection.recordId, $event)" />
            <strong class="mono">{{ collection.skillName || collection.name || collection.digest.slice(0, 12) }}{{ collection.version ? `@${collection.version}` : '' }}</strong>
            <span>{{ collection.createdAt.slice(0, 19).replace('T', ' ') }}</span>
            <span>{{ t('offline.source') }} · {{ collection.source }}</span>
          </div>
          <div class="collection-deps">
            <span>{{ t('offline.declared') }}</span>
            <code v-for="kind in ['pip', 'npm', 'apt']" :key="kind" v-show="collection.declared[kind]?.length">{{ kind }}: {{ collection.declared[kind]?.join(', ') }}</code>
          </div>
        </div>
      </section>
    </n-spin>
  </main>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useMessage } from 'naive-ui'
import { t } from '@/composables/i18n'
import {
  exportOfflinePackages, fetchOfflinePackages, importOfflinePackages, setOfflineOnly,
  type OfflinePackageInventory,
} from '@/api/offline-packages'

const message = useMessage()
const inventory = ref<OfflinePackageInventory | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const loading = ref(false)
const transferring = ref(false)
const saving = ref(false)
const selectedRecords = ref<string[]>([])
const rows = [
  { key: 'pip', keys: ['pip'], label: 'offline.pip' },
  { key: 'npm', keys: ['npm'], label: 'offline.npm' },
  { key: 'pnpm', keys: ['pnpm', 'pnpm-cache'], label: 'offline.pnpm' },
  { key: 'plugin-archives', keys: ['plugin-archives'], label: 'offline.pluginArchive' },
  { key: 'apt-archives', keys: ['apt-archives', 'apt-lists'], label: 'offline.apt' },
] as const

function count(keys: readonly string[]): number {
  return keys.reduce((total, key) => total + (inventory.value?.counts[key] || 0), 0)
}

function bytes(keys: readonly string[]): number {
  return keys.reduce((total, key) => total + (inventory.value?.sizes[key] || 0), 0)
}

function size(bytes: number): string {
  return bytes < 1024 * 1024 ? `${(bytes / 1024).toFixed(1)} KB` : `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

async function load() {
  loading.value = true
  try { inventory.value = await fetchOfflinePackages() }
  catch { message.error(t('offline.loadFailed')) }
  finally { loading.value = false }
}

async function updateMode(value: boolean) {
  saving.value = true
  try { inventory.value = await setOfflineOnly(value) }
  catch { message.error(t('offline.saveFailed')) }
  finally { saving.value = false }
}

async function download() {
  transferring.value = true
  try { await exportOfflinePackages() }
  catch { message.error(t('offline.exportFailed')) }
  finally { transferring.value = false }
}

async function downloadSelected() {
  transferring.value = true
  try { await exportOfflinePackages(selectedRecords.value) }
  catch { message.error(t('offline.exportFailed')) }
  finally { transferring.value = false }
}

function toggleRecord(id: string, selected: boolean) {
  selectedRecords.value = selected
    ? [...selectedRecords.value, id]
    : selectedRecords.value.filter(value => value !== id)
}

async function upload(event: Event) {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file) return
  transferring.value = true
  try {
    inventory.value = await importOfflinePackages(file)
    message.success(t('offline.imported'))
  } catch { message.error(t('offline.importFailed')) }
  finally { transferring.value = false; target.value = '' }
}

onMounted(load)
</script>

<style scoped>
.offline-page { display: grid; align-content: start; gap: 20px; height: 100%; overflow: auto; padding: 24px; background: #f7f9fd; color: #1d2b46; }
.offline-toolbar { display: flex; justify-content: space-between; align-items: center; gap: 20px; }
.offline-toolbar h1 { margin: 0; font-size: 22px; }
.offline-toolbar p, .mode-card p { margin: 7px 0 0; color: #718099; font-size: 13px; }
.offline-actions { display: flex; flex-wrap: wrap; gap: 8px; }
.offline-card { padding: 24px; border: 1px solid #dfe7f3; border-radius: 16px; background: #fff; box-shadow: 0 5px 18px rgba(30,55,90,.04); }
.mode-card, .inventory-head, .package-row { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.inventory-head { margin-bottom: 18px; }
.inventory-head span { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; color: #718099; }
.package-row { padding: 16px 0; border-top: 1px solid #edf1f7; }
.package-row > * { flex: 1; }
.package-row span { color: #66758e; }
.empty-records { margin: 16px 0 0; color: #718099; }
.collection-row { padding: 16px 0; border-top: 1px solid #edf1f7; }
.collection-row:first-of-type { margin-top: 16px; }
.collection-head { display: flex; flex-wrap: wrap; gap: 10px 24px; color: #66758e; font-size: 13px; }
.collection-head strong { color: #1d2b46; }
.collection-deps { display: grid; gap: 6px; margin-top: 10px; color: #718099; font-size: 12px; }
.collection-deps code { overflow-wrap: anywhere; color: #405477; font: 12px/1.5 ui-monospace, SFMono-Regular, Menlo, monospace; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
@media (max-width: 800px) { .offline-page { padding: 12px; }.offline-toolbar { align-items: flex-start; flex-direction: column; }.package-row { align-items: flex-start; flex-direction: column; gap: 6px; } }
</style>
