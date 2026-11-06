<template>
  <main class="offline-page">
    <div class="offline-toolbar">
      <div>
        <h1><ArchiveOutline aria-hidden="true" />{{ t('offline.title') }}</h1>
        <p>{{ t('offline.description') }}</p>
        <p>{{ t('offline.scopeHint') }}</p>
      </div>
      <div class="offline-actions">
        <div class="mode-control" :title="t('offline.offlineHint')">
          <CloudOfflineOutline aria-hidden="true" />
          <span>{{ t('offline.offlineOnly') }}</span>
          <n-switch :value="inventory?.offlineOnly || false" :disabled="!inventory || saving || activeTransfer !== null" :aria-label="t('offline.offlineOnly')" @update:value="updateMode" />
        </div>
        <n-button :loading="loading" @click="load"><template #icon><n-icon><RefreshOutline /></n-icon></template>{{ t('offline.refresh') }}</n-button>
        <n-button :loading="activeTransfer === 'export'" :disabled="!inventory || activeTransfer !== null" @click="download"><template #icon><n-icon><CloudDownloadOutline /></n-icon></template>{{ t('offline.export') }}</n-button>
        <n-button type="primary" :loading="activeTransfer === 'import'" :disabled="activeTransfer !== null" @click="fileInput?.click()"><template #icon><n-icon><CloudUploadOutline /></n-icon></template>{{ t('offline.import') }}</n-button>
        <input ref="fileInput" type="file" accept=".zip,application/zip" hidden @change="upload" />
      </div>
    </div>

    <n-spin class="offline-content" :show="loading">
      <section class="offline-card tab-card">
        <div class="offline-tabs" role="tablist" :aria-label="t('offline.title')">
          <button type="button" role="tab" :aria-selected="activeTab === 'packages'" :class="{ active: activeTab === 'packages' }" @click="activeTab = 'packages'"><LayersOutline aria-hidden="true" />{{ t('offline.packagesTab') }}</button>
          <button type="button" role="tab" :aria-selected="activeTab === 'records'" :class="{ active: activeTab === 'records' }" @click="activeTab = 'records'"><TimeOutline aria-hidden="true" />{{ t('offline.collections') }}<span class="record-count">{{ inventory?.collections?.length ?? 0 }}</span></button>
        </div>
        <div v-if="activeTab === 'packages'" class="tab-scroll" role="tabpanel">
          <div class="inventory-head"><strong class="section-title">{{ t('offline.platform') }}</strong><span>{{ inventory ? `${inventory.os} / ${inventory.platform}` : '—' }}</span></div>
          <div v-for="row in rows" :key="row.key" class="package-row">
            <div class="package-name"><span class="package-icon"><component :is="row.icon" aria-hidden="true" /></span><strong>{{ t(row.label) }}</strong></div>
            <span>{{ t('offline.files') }} · {{ inventory ? count(row.keys) : '—' }}</span>
            <span>{{ t('offline.size') }} · {{ inventory ? size(bytes(row.keys)) : '—' }}</span>
          </div>
        </div>
        <div v-else class="tab-scroll" role="tabpanel"><OfflinePreparationRecords :records="inventory?.collections || []" :downloading-id="activeRecordId" @download="downloadRecord" /></div>
      </section>
    </n-spin>
  </main>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { NIcon, useMessage } from 'naive-ui'
import { ArchiveOutline, CloudDownloadOutline, CloudOfflineOutline, CloudUploadOutline, CodeSlashOutline, CubeOutline, ExtensionPuzzleOutline, LayersOutline, LogoNpm, RefreshOutline, TimeOutline } from '@vicons/ionicons5'
import { t } from '@/composables/i18n'
import OfflinePreparationRecords from './OfflinePreparationRecords.vue'
import {
  exportOfflinePackages, fetchOfflinePackages, importOfflinePackages, setOfflineOnly,
  type OfflinePackageInventory,
} from '@/api/offline-packages'

const message = useMessage()
const inventory = ref<OfflinePackageInventory | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const loading = ref(false)
const activeTransfer = ref<'export' | 'record' | 'import' | null>(null)
const activeRecordId = ref<string | null>(null)
const saving = ref(false)
const activeTab = ref<'packages' | 'records'>('packages')
const rows = [
  { key: 'pip', keys: ['pip'], label: 'offline.pip', icon: CodeSlashOutline },
  { key: 'npm', keys: ['npm'], label: 'offline.npm', icon: LogoNpm },
  { key: 'pnpm', keys: ['pnpm', 'pnpm-cache'], label: 'offline.pnpm', icon: CubeOutline },
  { key: 'plugin-archives', keys: ['plugin-archives'], label: 'offline.pluginArchive', icon: ExtensionPuzzleOutline },
  { key: 'apt-archives', keys: ['apt-archives', 'apt-lists'], label: 'offline.apt', icon: ArchiveOutline },
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
  if (activeTransfer.value !== null) return
  activeTransfer.value = 'export'
  try { await exportOfflinePackages() }
  catch { message.error(t('offline.exportFailed')) }
  finally { activeTransfer.value = null }
}

async function downloadRecord(recordId: string) {
  if (activeTransfer.value !== null) return
  activeTransfer.value = 'record'
  activeRecordId.value = recordId
  try { await exportOfflinePackages([recordId]) }
  catch { message.error(t('offline.exportFailed')) }
  finally { activeTransfer.value = null; activeRecordId.value = null }
}

async function upload(event: Event) {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file) return
  if (activeTransfer.value !== null) { target.value = ''; return }
  activeTransfer.value = 'import'
  try {
    inventory.value = await importOfflinePackages(file)
    message.success(t('offline.imported'))
  } catch { message.error(t('offline.importFailed')) }
  finally { activeTransfer.value = null; target.value = '' }
}

onMounted(load)
</script>

<style scoped src="./offlinePackagesPage.css"></style>
