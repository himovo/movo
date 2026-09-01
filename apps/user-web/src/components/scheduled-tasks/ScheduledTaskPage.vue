<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  NButton,
  NCard,
  NIcon,
  NInput,
  NPopconfirm,
  NSpace,
  NSpin,
  NSwitch,
  NTag,
  useMessage,
} from 'naive-ui'
import { ArrowBackOutline } from '@vicons/ionicons5'
import { formatAppDateTime, getAppTimezone, parseAppDate } from '../../composables/appTimezone'
import type { SessionSummary } from '../../api/sessions'
import {
  createScheduledJob,
  deleteScheduledJob,
  listScheduledJobs,
  runScheduledJobNow,
  updateScheduledJob,
  type ScheduledJob,
  type ScheduledJobDraft,
} from '../../api/scheduledTasks'
import ScheduledTaskEditor from './ScheduledTaskEditor.vue'
import { getLocale, t } from '../../composables/i18n'

const props = defineProps<{
  token: string
  sessions: SessionSummary[]
  currentSessionId?: string | null
  timezone: string
  initialPrompt?: string
  createRequestKey?: number
}>()

const emit = defineEmits<{
  (e: 'back'): void
  (e: 'open-session', id: string): void
}>()

const message = useMessage()
const jobs = ref<ScheduledJob[]>([])
const loading = ref(false)
const saving = ref(false)
const editorOpen = ref(false)
const editingJob = ref<ScheduledJob | null>(null)
const editorInitialPrompt = ref('')
const editorInitialSessionId = ref<string | null>(null)
let refreshTimer: ReturnType<typeof setInterval> | null = null

const filterKeyword = ref('')

const sessionTitleById = computed(
  () => new Map(props.sessions.map((item) => [item.id, item.title || t('新对话')])),
)

const filteredJobs = computed(() => {
  const kw = filterKeyword.value.trim().toLowerCase()
  if (!kw) return jobs.value
  return jobs.value.filter(
    (job) =>
      job.name.toLowerCase().includes(kw) || job.prompt.toLowerCase().includes(kw),
  )
})

async function load(silent = false) {
  if (!props.token) return
  if (!silent) loading.value = true
  try {
    jobs.value = await listScheduledJobs(props.token)
  } catch (error: any) {
    message.error(
      error?.response?.data?.detail || error?.message || t('加载定时任务失败'),
    )
  } finally {
    if (!silent) loading.value = false
  }
}

function createNew(
  prompt = '',
  sessionId: string | null = props.currentSessionId || null,
) {
  editingJob.value = null
  editorInitialPrompt.value = prompt
  editorInitialSessionId.value = sessionId
  editorOpen.value = true
}

function edit(job: ScheduledJob) {
  editingJob.value = job
  editorOpen.value = true
}

async function save(draft: ScheduledJobDraft) {
  saving.value = true
  try {
    if (editingJob.value) await updateScheduledJob(props.token, editingJob.value.id, draft)
    else await createScheduledJob(props.token, draft)
    editorOpen.value = false
    message.success(editingJob.value ? t('定时任务已更新') : t('定时任务已创建'))
    await load()
  } catch (error: any) {
    message.error(
      error?.response?.data?.detail || error?.message || t('保存失败'),
    )
  } finally {
    saving.value = false
  }
}

async function toggle(job: ScheduledJob, enabled: boolean) {
  try {
    await updateScheduledJob(props.token, job.id, { enabled })
    await load()
  } catch (error: any) {
    message.error(
      error?.response?.data?.detail || error?.message || t('更新失败'),
    )
  }
}

async function runNow(job: ScheduledJob) {
  try {
    await runScheduledJobNow(props.token, job.id)
    message.success(t('已开始执行'))
    await load()
  } catch (error: any) {
    message.error(
      error?.response?.data?.detail || error?.message || t('启动失败'),
    )
  }
}

async function remove(job: ScheduledJob) {
  try {
    await deleteScheduledJob(props.token, job.id)
    await load()
    message.success(t('定时任务已删除'))
  } catch (error: any) {
    message.error(
      error?.response?.data?.detail || error?.message || t('删除失败'),
    )
  }
}

function scheduleText(job: ScheduledJob) {
  const at = parseAppDate(job.run_at) || new Date(job.run_at)
  const time = new Intl.DateTimeFormat(getLocale() === 'zh' ? 'zh-CN' : 'en-US', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: getAppTimezone(),
  }).format(at)
  if (job.schedule_kind === 'once') return t('单次 · {time}', { time: formatAppDateTime(job.run_at) })
  if (job.schedule_kind === 'daily') return t('每天 {time}', { time })
  const labels = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
  const separator = getLocale() === 'zh' ? '、' : ', '
  return t('每周{days} {time}', { days: job.weekdays.map((day) => t(labels[day])).join(separator), time })
}

function statusText(job: ScheduledJob) {
  if (!job.enabled) return t('已停用')
  if (job.last_run_status === 'running') return t('正在运行')
  if (job.last_run_status === 'failed') return t('最近执行失败')
  if (job.next_run_at) return t('下次 {time}', { time: formatAppDateTime(job.next_run_at) })
  return t('等待安排')
}

onMounted(() => {
  void load()
  refreshTimer = setInterval(() => {
    if (document.visibilityState !== 'hidden') void load(true)
  }, 5000)
  if (props.createRequestKey && props.initialPrompt)
    createNew(props.initialPrompt, props.currentSessionId || null)
})

onBeforeUnmount(() => {
  if (refreshTimer) clearInterval(refreshTimer)
})

watch(
  () => props.createRequestKey,
  (next, previous) => {
    if (next !== previous && next)
      createNew(props.initialPrompt || '', props.currentSessionId || null)
  },
)
</script>

<template>
  <div class="page-stack tasks-page">
    <!-- 头部区域，风格与 MyToolsPage / MySkillsPage 一致 -->
    <header class="tasks-header">
      <div class="tasks-header-left">
        <n-button secondary @click="emit('back')">
          <template #icon><n-icon><ArrowBackOutline /></n-icon></template>
          {{ t('返回对话') }}
        </n-button>
        <h1>{{ t('定时任务') }}</h1>
      </div>
    </header>

    <!-- 列表主面板 Shell Card （注意：无顶部统计卡片） -->
    <n-card class="list-card shell-card" :bordered="false" size="large">
      <!-- 过滤与操作工具栏 -->
      <div class="list-filter-row">
        <div class="filter-toolbar">
          <n-space align="center" :size="10" class="filter-left">
            <n-input
              v-model:value="filterKeyword"
              clearable
              :placeholder="t('搜索任务名称或提示词...')"
              class="keyword-input"
            />
          </n-space>
          <n-space :size="10" class="filter-right">
            <n-button secondary @click="load()">
              <template #icon>
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                >
                  <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
                  <path d="M3 3v5h5" />
                  <path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16" />
                  <path d="M16 16h5v5" />
                </svg>
              </template>
              {{ t('刷新') }}
            </n-button>
            <n-button type="primary" strong @click="createNew()">
              <template #icon>
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                >
                  <path d="M5 12h14" />
                  <path d="M12 5v14" />
                </svg>
              </template>
              {{ t('创建定时任务') }}
            </n-button>
          </n-space>
        </div>
      </div>

      <!-- 列表内容区 -->
      <div class="list-body">
        <n-spin :show="loading">
          <div v-if="filteredJobs.length" class="task-grid">
            <article
              v-for="job in filteredJobs"
              :key="job.id"
              class="task-card"
              :class="{ 'task-card-disabled': !job.enabled }"
            >
              <div class="card-head">
                <div class="card-tags">
                  <n-tag
                    size="small"
                    :bordered="false"
                    :type="job.enabled ? 'success' : 'default'"
                  >
                    {{ job.enabled ? t('已启用') : t('已停用') }}
                  </n-tag>
                  <n-tag
                    v-if="job.last_run_status === 'running'"
                    size="small"
                    :bordered="false"
                    type="info"
                  >
                    <span class="inline-flex items-center gap-1">
                      <span class="h-1.5 w-1.5 animate-pulse rounded-full bg-blue-500"></span>
                      {{ t('运行中') }}
                    </span>
                  </n-tag>
                  <n-tag
                    v-else-if="job.last_run_status === 'failed'"
                    size="small"
                    :bordered="false"
                    type="error"
                  >
                    {{ t('最近失败') }}
                  </n-tag>
                </div>
                <span class="card-time">{{ scheduleText(job) }}</span>
              </div>

              <div class="card-title">{{ job.name }}</div>
              <div class="card-desc">{{ job.prompt }}</div>

              <div class="card-meta">
                <span class="meta-item">{{ job.timezone }}</span>
                <span class="meta-divider">•</span>
                <button
                  v-if="job.session_mode === 'fixed' && job.session_id"
                  type="button"
                  class="session-link"
                  @click="emit('open-session', job.session_id)"
                >
                  {{ sessionTitleById.get(job.session_id) || t('目标会话') }}
                </button>
                <span v-else class="meta-item">{{ t('每次新建会话') }}</span>
                <span class="meta-divider">•</span>
                <span class="meta-item">{{ statusText(job) }}</span>
              </div>

              <div class="card-footrow">
                <div class="card-actions">
                  <div class="card-switch" @click.stop>
                    <span class="card-switch-label">{{ job.enabled ? t('已启用') : t('已停用') }}</span>
                    <n-switch
                      size="small"
                      :value="job.enabled"
                      @update:value="(value) => toggle(job, value)"
                    />
                  </div>
                  <n-button
                    class="icon-only-btn"
                    size="small"
                    quaternary
                    circle
                    :title="t('立即运行')"
                    @click="runNow(job)"
                  >
                    <svg viewBox="0 0 24 24" aria-hidden="true">
                      <polygon points="5 3 19 12 5 21 5 3" />
                    </svg>
                  </n-button>
                  <n-button
                    class="icon-only-btn"
                    size="small"
                    quaternary
                    circle
                    :title="t('编辑任务')"
                    @click="edit(job)"
                  >
                    <svg viewBox="0 0 24 24" aria-hidden="true">
                      <path d="M12 20h9" />
                      <path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z" />
                    </svg>
                  </n-button>
                  <n-popconfirm @positive-click="remove(job)">
                    <template #trigger>
                      <n-button
                        class="icon-only-btn delete-btn"
                        size="small"
                        quaternary
                        circle
                        :title="t('删除任务')"
                      >
                        <svg viewBox="0 0 24 24" aria-hidden="true">
                          <path d="M3 6h18" />
                          <path d="M8 6V4h8v2" />
                          <path d="M6 6l1 14h10l1-14" />
                          <path d="M10 11v6" />
                          <path d="M14 11v6" />
                        </svg>
                      </n-button>
                    </template>
                    {{ t('确定删除这个定时任务吗？') }}
                  </n-popconfirm>
                </div>
              </div>
            </article>
          </div>

          <div v-else class="empty-shell">
            <div class="empty-visual">
              <span>CRON</span>
              <span>TIME</span>
              <span>TASK</span>
            </div>
            <div class="empty-title">{{ t('还没有定时任务') }}</div>
            <div class="empty-desc">{{ t('创建定时任务，让 AI 在指定时间自动为您发起会话并完成工作。') }}</div>
            <n-space justify="center">
              <n-button type="primary" @click="createNew()">{{ t('创建第一个任务') }}</n-button>
            </n-space>
          </div>
        </n-spin>
      </div>
    </n-card>

    <ScheduledTaskEditor
      :open="editorOpen"
      :saving="saving"
      :job="editingJob"
      :sessions="sessions"
      :initial-prompt="editingJob ? '' : editorInitialPrompt"
      :initial-session-id="editingJob ? null : editorInitialSessionId"
      :timezone="timezone"
      @close="editorOpen = false"
      @save="save"
    />
  </div>
</template>

<style scoped>
.tasks-page {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
  background: #f6f8fc;
  padding: 12px;
}

.tasks-header {
  width: 100%;
  padding: 14px 18px;
  border: 1px solid #e6ebf5;
  border-radius: 8px;
  background: #fff;
  box-shadow: 0 4px 12px rgba(29, 54, 110, 0.04);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.tasks-header h1 {
  margin: 0;
  color: #101c3d;
  font-size: 20px;
  line-height: 1.2;
  font-weight: 800;
}

.tasks-header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.shell-card {
  border-radius: 14px;
  border: 1px solid #e6ebf5;
  background: #fff;
  box-shadow: 0 6px 20px rgba(16, 38, 84, 0.05);
}

.list-card {
  width: 100%;
  margin: 0;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.list-card :deep(.n-card__content) {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.filter-toolbar {
  align-items: center;
  display: flex;
  justify-content: space-between;
  gap: 14px;
}

.filter-left {
  flex-wrap: wrap;
}

.keyword-input {
  width: 360px;
}

.filter-right {
  flex-wrap: wrap;
}

.list-filter-row {
  padding: 0 44px 12px;
  margin: 0 -44px 12px;
  border-bottom: 1px solid #edf1f7;
}

.list-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
}

.task-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 12px;
}

.task-card {
  min-height: 200px;
  padding: 16px;
  border: 1px solid rgba(28, 45, 82, 0.08);
  border-radius: 8px;
  background: #fff;
  box-shadow:
    0 8px 18px rgba(15, 31, 69, 0.06),
    0 1px 2px rgba(15, 31, 69, 0.04);
  display: flex;
  flex-direction: column;
  gap: 10px;
  text-align: left;
  transition:
    border-color 0.2s ease,
    box-shadow 0.2s ease,
    transform 0.2s ease;
}

.task-card:hover {
  border-color: rgba(54, 106, 255, 0.36);
  box-shadow:
    0 14px 34px rgba(33, 58, 126, 0.14),
    0 4px 10px rgba(33, 58, 126, 0.08);
  transform: translateY(-2px);
}

.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.card-tags {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.card-time {
  color: #7a8797;
  font-size: 12px;
}

.card-title {
  color: #17233d;
  font-size: 16px;
  font-weight: 800;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.card-desc {
  color: #5f6f85;
  font-size: 13px;
  line-height: 1.55;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
  overflow: hidden;
}

.card-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #708099;
  flex-wrap: wrap;
  margin-top: 2px;
}

.meta-item {
  color: #65748c;
}

.meta-divider {
  color: #cbd5e1;
}

.session-link {
  color: #2d63ff;
  font-weight: 500;
  cursor: pointer;
  background: none;
  border: none;
  padding: 0;
  font-size: 12px;
}

.session-link:hover {
  text-decoration: underline;
}

.card-footrow {
  margin-top: auto;
  display: flex;
  justify-content: flex-end;
  padding-top: 6px;
}

.card-actions {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-left: auto;
}

.card-switch {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 4px 10px;
  border-radius: 999px;
  background: #f6f9ff;
  border: 1px solid #e3ebfb;
}

.card-switch-label {
  color: #4a5d7c;
  font-size: 12px;
  line-height: 1;
}

.icon-only-btn :deep(svg) {
  width: 15px;
  height: 15px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.delete-btn:hover {
  color: #d03050;
}

.task-card-disabled {
  background: linear-gradient(180deg, #fbfcfe, #f6f8fc);
  border-color: rgba(28, 45, 82, 0.06);
}

.task-card-disabled .card-title,
.task-card-disabled .card-desc,
.task-card-disabled .card-time {
  opacity: 0.72;
}

.empty-shell {
  min-height: 320px;
  border: 1px dashed #d8e2f2;
  border-radius: 12px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  text-align: center;
  background: linear-gradient(180deg, #fbfdff, #fff);
  margin: 20px 0;
}

.empty-visual {
  display: flex;
  gap: 8px;
}

.empty-visual span {
  width: 54px;
  height: 28px;
  border-radius: 6px;
  background: #eef4ff;
  color: #3b82f6;
  font-size: 11px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  letter-spacing: 0.5px;
}

.empty-title {
  color: #1e293b;
  font-size: 16px;
  font-weight: 700;
}

.empty-desc {
  color: #64748b;
  font-size: 13px;
  max-width: 400px;
}
</style>
