<template>
  <main class="deployment-page">
    <Teleport v-if="headerActionsReady" to="#header-actions-teleport-target">
      <div class="page-actions">
        <n-button secondary :loading="loading" @click="load">{{ t('deployment.refresh') }}</n-button>
        <n-button type="primary" :disabled="!status" @click="copyDiagnostics">{{ t('deployment.copy') }}</n-button>
      </div>
    </Teleport>

    <n-alert v-if="loadError" type="info" :bordered="false" class="load-error">{{ t('deployment.loadFailed') }}</n-alert>
    <div v-if="loading && !status" class="loading-panel"><n-spin size="medium" /><span>{{ t('deployment.loading') }}</span></div>

    <template v-if="status">
      <section class="summary-card">
        <div class="summary-main">
          <div class="summary-state"><span class="state-dot" :class="counts.issues ? 'warning' : 'good'"></span>{{ counts.issues ? t('deployment.unhealthy') : t('deployment.healthy') }}<span class="checked-at">{{ t('deployment.checkedAt') }} · {{ displayTime(status.checkedAt) }}</span></div>
        </div>
        <div class="summary-metrics">
          <div><span>{{ t('deployment.upgradedAt') }}</span><strong>{{ displayTime(status.deployment.upgradedAt) }}</strong></div>
          <div><span>{{ t('deployment.version') }}</span><strong class="mono" :title="status.deployment.commit || ''">{{ displayVersion }}</strong></div>
          <div><span>{{ t('deployment.runningCount') }}</span><strong>{{ counts.running }}</strong></div>
          <div><span>{{ t('deployment.issueCount') }}</span><strong :class="{ danger: counts.issues }">{{ counts.issues }}</strong></div>
          <div><span>{{ t('deployment.disabledCount') }}</span><strong>{{ counts.disabled }}</strong></div>
          <div><span>{{ t('deployment.mismatchCount') }}</span><strong :class="{ danger: counts.mismatches }">{{ status.deployment.upgradedAt ? counts.mismatches : '—' }}</strong></div>
        </div>
      </section>

      <section class="inventory-card">
        <div class="inventory-tabs" role="tablist" :aria-label="t('deployment.images')">
          <button type="button" role="tab" :aria-selected="activeTab === 'services'" :class="{ active: activeTab === 'services' }" @click="activeTab = 'services'">{{ t('deployment.services') }}</button>
          <button type="button" role="tab" :aria-selected="activeTab === 'runtime'" :class="{ active: activeTab === 'runtime' }" @click="activeTab = 'runtime'">{{ t('deployment.runtimeImage') }}</button>
        </div>
        <div v-if="activeTab === 'services'" class="table-scroll" role="tabpanel">
          <table>
            <thead><tr>
              <th>{{ t('deployment.name') }}</th><th>{{ t('deployment.state') }}</th><th>{{ t('deployment.health') }}</th>
              <th>{{ t('deployment.image') }}</th><th>{{ t('deployment.imageId') }}</th><th>{{ t('deployment.startedAt') }}</th><th>{{ t('deployment.restarts') }}</th>
            </tr></thead>
            <tbody>
              <template v-for="group in groups" :key="group.key">
                <tr class="group-row"><td colspan="7">{{ t(group.key) }}</td></tr>
                <tr v-for="service in group.services" :key="service.name" class="service-row" tabindex="0" @click="selected = service" @keydown.enter="selected = service">
                  <td class="service-name">{{ service.name }}<span v-if="service.versionMismatch" class="mismatch-mark" :title="t('deployment.mismatch')">!</span></td>
                  <td><span class="status-pill" :class="serviceTone(service)">{{ stateLabel(service.status) }}</span></td>
                  <td>{{ healthLabel(service.health) }}</td>
                  <td class="image-cell" :title="service.image || ''">{{ service.image || '—' }}</td>
                  <td class="mono" :title="service.imageId || ''">{{ shortId(service.imageId) }}</td>
                  <td>{{ displayTime(service.startedAt) }}</td>
                  <td>{{ service.restarts ?? '—' }}</td>
                </tr>
              </template>
            </tbody>
          </table>
        </div>
        <div v-else class="runtime-panel" role="tabpanel">
          <div><span>{{ t('deployment.image') }}</span><strong class="mono">{{ status.scriptImage.image || '—' }}</strong></div>
          <div><span>{{ t('deployment.imageId') }}</span><strong class="mono" :title="status.scriptImage.imageId">{{ status.scriptImage.imageId || '—' }}</strong></div>
          <div><span>{{ t('deployment.state') }}</span><strong><span class="status-pill" :class="status.scriptImage.available ? 'good' : 'muted'">{{ status.scriptImage.available ? t('deployment.available') : t('deployment.notAvailable') }}</span></strong></div>
        </div>
      </section>
    </template>
    <template v-else-if="loadError">
      <section class="summary-card">
        <div class="summary-state"><span class="state-dot neutral"></span>{{ t('deployment.unknownState') }}<span class="checked-at">{{ t('deployment.checkedAt') }} · —</span></div>
        <div class="summary-metrics">
          <div><span>{{ t('deployment.upgradedAt') }}</span><strong>—</strong></div>
          <div><span>{{ t('deployment.version') }}</span><strong>—</strong></div>
          <div><span>{{ t('deployment.runningCount') }}</span><strong>—</strong></div>
          <div><span>{{ t('deployment.issueCount') }}</span><strong>—</strong></div>
          <div><span>{{ t('deployment.disabledCount') }}</span><strong>—</strong></div>
          <div><span>{{ t('deployment.mismatchCount') }}</span><strong>—</strong></div>
        </div>
      </section>
      <section class="inventory-card">
        <div class="inventory-tabs" role="tablist" :aria-label="t('deployment.images')">
          <button type="button" role="tab" :aria-selected="activeTab === 'services'" :class="{ active: activeTab === 'services' }" @click="activeTab = 'services'">{{ t('deployment.services') }}</button>
          <button type="button" role="tab" :aria-selected="activeTab === 'runtime'" :class="{ active: activeTab === 'runtime' }" @click="activeTab = 'runtime'">{{ t('deployment.runtimeImage') }}</button>
        </div>
        <div v-if="activeTab === 'services'" class="inventory-empty" role="tabpanel"><div class="empty-glyph">◇</div><strong>{{ t('deployment.emptyTitle') }}</strong><p>{{ t('deployment.emptyDescription') }}</p></div>
        <div v-else class="runtime-panel" role="tabpanel"><div><span>{{ t('deployment.image') }}</span><strong>—</strong></div><div><span>{{ t('deployment.imageId') }}</span><strong>—</strong></div><div><span>{{ t('deployment.state') }}</span><strong>{{ t('deployment.unknownState') }}</strong></div></div>
      </section>
    </template>

    <n-drawer :show="!!selected" width="min(560px, 100vw)" placement="right" @update:show="closeDetails">
      <n-drawer-content :title="t('deployment.details')" closable>
        <template v-if="selected">
          <h2 class="drawer-service">{{ selected.name }}</h2>
          <dl class="detail-list">
            <template v-for="item in detailRows" :key="item.label">
              <dt>{{ item.label }}</dt><dd :class="{ mono: item.mono }">{{ item.value }}<n-button v-if="item.copy && item.value !== '—'" text size="tiny" class="copy-inline" @click="copyValue(item.value)">{{ t('deployment.copyValue') }}</n-button></dd>
            </template>
          </dl>
        </template>
      </n-drawer-content>
    </n-drawer>

    <n-modal v-model:show="showManualCopy">
      <n-card class="manual-copy-card" :title="t('deployment.manualCopyTitle')" closable @close="showManualCopy = false">
        <p>{{ t('deployment.manualCopyHint') }}</p>
        <textarea ref="manualCopyField" readonly :value="manualCopyValue" @focus="selectManualCopy" @click="selectManualCopy"></textarea>
        <div class="manual-copy-actions"><n-button @click="selectManualCopy">{{ t('deployment.selectAll') }}</n-button></div>
      </n-card>
    </n-modal>
  </main>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { useMessage } from 'naive-ui'
import { fetchDeploymentStatus, type DeploymentService, type DeploymentStatus } from '@/api/deployment-status'
import { t } from '@/composables/i18n'
import { formatAdminShortDateTime } from '@/composables/adminTimezone'
import { diagnostics, INFRASTRUCTURE, serviceCounts, serviceTone, shortId } from './deploymentStatusView'
import { copyText } from './copyText'

const message = useMessage()
const status = ref<DeploymentStatus | null>(null)
const selected = ref<DeploymentService | null>(null)
const loading = ref(false)
const loadError = ref(false)
const headerActionsReady = ref(false)
const activeTab = ref<'services' | 'runtime'>('services')
const showManualCopy = ref(false)
const manualCopyValue = ref('')
const manualCopyField = ref<HTMLTextAreaElement | null>(null)
const displayVersion = computed(() => {
  if (!status.value) return t('deployment.unknown')
  const deployment = status.value.deployment
  if ((deployment.revisions?.length ?? 0) > 1) return t('deployment.mixedRevisions')
  if (deployment.commit) return deployment.commit.slice(0, 12)
  if (deployment.version && deployment.version !== 'latest') return deployment.version
  const imageId = status.value.services.find(service => service.name === 'admin-api')?.imageId
  return imageId ? shortId(imageId) : t('deployment.unknown')
})
const counts = computed(() => status.value ? serviceCounts(status.value) : { running: 0, issues: 0, disabled: 0, mismatches: 0 })
const groups = computed(() => status.value ? [
  { key: 'deployment.core', services: status.value.services.filter(service => !INFRASTRUCTURE.has(service.name)) },
  { key: 'deployment.infrastructure', services: status.value.services.filter(service => INFRASTRUCTURE.has(service.name)) },
] : [])

function displayTime(value?: string | null) {
  return value && !value.startsWith('0001-') ? formatAdminShortDateTime(value) : '—'
}

function stateLabel(value: string) {
  const key = ['running', 'exited', 'created', 'restarting', 'paused', 'dead', 'missing', 'disabled'].includes(value) ? value : 'unknown'
  return t(key === 'unknown' ? 'deployment.unknownState' : `deployment.${key}`)
}

function healthLabel(value?: string) {
  if (!value || value === 'unknown') return t('deployment.noHealthcheck')
  return t(`deployment.${value}`)
}

function closeDetails(value: boolean) {
  if (!value) selected.value = null
}

const detailRows = computed(() => selected.value ? [
  { label: t('deployment.state'), value: stateLabel(selected.value.status) },
  { label: t('deployment.health'), value: healthLabel(selected.value.health) },
  { label: t('deployment.image'), value: selected.value.image || '—', mono: true },
  { label: t('deployment.imageId'), value: selected.value.imageId || '—', mono: true, copy: true },
  { label: t('deployment.revision'), value: selected.value.revision || '—', mono: true, copy: true },
  { label: t('deployment.mismatchCount'), value: selected.value.versionMismatch ? t('deployment.mismatch') : '—' },
  { label: t('deployment.containerId'), value: selected.value.containerId || '—', mono: true, copy: true },
  { label: t('deployment.createdAt'), value: displayTime(selected.value.createdAt) },
  { label: t('deployment.startedAt'), value: displayTime(selected.value.startedAt) },
  { label: t('deployment.restarts'), value: String(selected.value.restarts ?? '—') },
] : [])

async function load() {
  loading.value = true
  loadError.value = false
  try { status.value = await fetchDeploymentStatus() }
  catch { loadError.value = true }
  finally { loading.value = false }
}

async function copyDiagnostics() {
  if (!status.value) return
  const value = diagnostics(status.value)
  if (await copyText(value)) {
    message.success(t('deployment.copied'))
  } else {
    await openManualCopy(value)
  }
}

async function copyValue(value: string) {
  if (await copyText(value)) {
    message.success(t('deployment.copiedValue'))
  } else {
    await openManualCopy(value)
  }
}

async function openManualCopy(value: string) {
  manualCopyValue.value = value
  showManualCopy.value = true
  await nextTick()
  manualCopyField.value?.select()
}

function selectManualCopy() {
  manualCopyField.value?.select()
}

onMounted(() => {
  headerActionsReady.value = !!document.querySelector('#header-actions-teleport-target')
  load()
})
</script>

<style scoped src="./deploymentStatusPage.css"></style>
