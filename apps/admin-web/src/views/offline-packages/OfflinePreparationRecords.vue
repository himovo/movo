<template>
  <div class="records-list">
    <p v-if="!groups.length" class="empty-records">{{ t('offline.noCollections') }}</p>
    <button v-for="group in groups" :key="group.key" type="button" class="record-group" @click="selectedKey = group.key">
      <span class="group-title"><strong>{{ group.name }}</strong><span class="group-kind">{{ t(group.kind === 'plugin' ? 'offline.plugin' : 'offline.skill') }}</span></span>
      <span class="group-end"><span class="group-count">{{ t('offline.recordCount', { count: group.records.length }) }}</span><ChevronForwardOutline aria-hidden="true" /></span>
    </button>
    <n-drawer :show="!!selectedGroup" width="min(640px, 100vw)" placement="right" @update:show="selectedKey = null">
      <n-drawer-content :title="selectedGroup ? t('offline.recordDetails', { name: selectedGroup.name }) : ''" closable>
        <div class="drawer-scroll">
          <div v-for="record in selectedGroup?.records || []" :key="record.recordId" class="record-row">
          <div class="record-details">
            <div class="record-meta"><time :datetime="record.createdAt">{{ displayTime(record.createdAt) }}</time><span>{{ t('offline.source') }} · {{ record.source }}</span><span v-if="record.version">{{ record.version }}</span></div>
            <div v-if="declared(record).length" class="record-deps"><code v-for="item in declared(record)" :key="item">{{ item }}</code></div>
            <span v-else class="record-empty">{{ t('offline.noDeclared') }}</span>
          </div>
          <n-button size="small" secondary :loading="downloadingId === record.recordId" :disabled="!!downloadingId" @click="$emit('download', record.recordId)"><template #icon><n-icon><CloudDownloadOutline /></n-icon></template>{{ t('offline.downloadRecord') }}</n-button>
          </div>
        </div>
      </n-drawer-content>
    </n-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { NIcon } from 'naive-ui'
import { ChevronForwardOutline, CloudDownloadOutline } from '@vicons/ionicons5'
import { t } from '@/composables/i18n'
import type { OfflinePackageInventory } from '@/api/offline-packages'

type Record = OfflinePackageInventory['collections'][number]
const props = defineProps<{ records: Record[]; downloadingId: string | null }>()
defineEmits<{ download: [recordId: string] }>()
const selectedKey = ref<string | null>(null)

const groups = computed(() => {
  const byName = new Map<string, { key: string; name: string; kind: string; records: Record[] }>()
  for (const record of props.records) {
    const kind = record.kind === 'plugin' ? 'plugin' : 'skill'
    const name = record.skillName || record.name || record.digest.slice(0, 12)
    const key = `${kind}:${name}`
    if (!byName.has(key)) byName.set(key, { key, name, kind, records: [] })
    byName.get(key)!.records.push(record)
  }
  return [...byName.values()].map(group => ({ ...group, records: group.records.sort((a, b) => b.createdAt.localeCompare(a.createdAt)) }))
    .sort((a, b) => (b.records[0]?.createdAt || '').localeCompare(a.records[0]?.createdAt || ''))
})
const selectedGroup = computed(() => groups.value.find(group => group.key === selectedKey.value) || null)

function declared(record: Record): string[] {
  return ['pip', 'npm', 'apt'].flatMap(kind => (record.declared[kind] || []).map(item => `${kind}: ${item}`))
}

function displayTime(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}
</script>

<style scoped src="./offlinePreparationRecords.css"></style>
