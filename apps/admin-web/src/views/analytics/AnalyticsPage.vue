<template>
  <div ref="pageRef" class="page-stack token-stats-page">

    <div ref="metricsRef" class="metrics-row">
      <n-card class="metric-card metric-card-orange" :bordered="false">
        <div class="metric-label">{{ t('成本统计') }}</div>
        <div class="metric-value">¥ {{ formatCost(summary.totalCost) }}</div>
        <div class="metric-note">{{ t('平均单次 {avg} | 近24h {last24h}', { avg: '¥' + formatCost(summary.avgCost), last24h: '¥' + formatCost(summary.last24hCost) }) }}</div>
        <div class="metric-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none">
            <path d="M12 2v20M17 5H9.5c-2 0-3.5 1.5-3.5 3.5s1.5 3.5 3.5 3.5h5c2 0 3.5 1.5 3.5 3.5s-1.5 3.5-3.5 3.5H6" />
          </svg>
        </div>
      </n-card>
      <n-card class="metric-card metric-card-blue" :bordered="false">
        <div class="metric-label">{{ t('总 Token 消耗') }}</div>
        <div class="metric-value">{{ formatNumber(summary.totalTokens) }}</div>
        <div class="metric-note">{{ t('平均每次请求 {count}', { count: formatNumber(summary.avgTokens) }) }}</div>
        <div class="metric-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none">
            <path d="M4 5h16v12H4z" />
            <path d="M8 21h8" />
            <path d="M12 17v4" />
            <path d="M8 9v5" />
            <path d="M12 11v3" />
            <path d="M16 7v7" />
          </svg>
        </div>
      </n-card>
      <n-card class="metric-card metric-card-green" :bordered="false">
        <div class="metric-label">Prompt</div>
        <div class="metric-value">{{ formatNumber(summary.promptTokens) }}</div>
        <div class="metric-note">{{ t('输入 Token') }}</div>
        <div class="metric-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none">
            <path d="M4 6h16" />
            <path d="M4 12h10" />
            <path d="M4 18h7" />
            <path d="M17 15l3 3-3 3" />
          </svg>
        </div>
      </n-card>
      <n-card class="metric-card metric-card-purple" :bordered="false">
        <div class="metric-label">Completion</div>
        <div class="metric-value">{{ formatNumber(summary.completionTokens) }}</div>
        <div class="metric-note">{{ t('输出 Token') }}</div>
        <div class="metric-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none">
            <path d="M4 6h16v12H4z" />
            <path d="M4 7l8 6 8-6" />
          </svg>
        </div>
      </n-card>
      <n-card class="metric-card metric-card-cyan" :bordered="false">
        <div class="metric-label">{{ t('近 24 小时') }}</div>
        <div class="metric-value">{{ formatNumber(summary.last24hTokens) }}</div>
        <div class="metric-note">{{ t('调用 {count} 次 LLM', { count: formatNumber(summary.last24hCalls) }) }}</div>
        <div class="metric-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none">
            <path d="M12 8v5l3 2" />
            <path d="M21 12a9 9 0 1 1-3-6.7" />
            <path d="M21 4v6h-6" />
          </svg>
        </div>
      </n-card>
    </div>

    <n-card ref="tableCardRef" class="list-card shell-card" :bordered="false" size="large">
      <div class="list-filter-row">
        <div class="filter-toolbar">
          <n-space align="center" :size="10" class="filter-left">
            <n-input v-model:value="filters.q" class="filter-search" clearable :placeholder="t('搜索请求 / 模型 / Trace')" />
            <n-select v-model:value="filters.departmentId" class="filter-select" clearable :options="departmentOptions" :placeholder="t('部门')" />
            <n-select v-model:value="filters.modelName" class="filter-select" clearable :options="modelOptions" :placeholder="t('模型')" />
            <n-select v-model:value="filters.status" class="filter-select-sm" clearable :options="localizedStatusOptions" :placeholder="t('状态')" />
          </n-space>
          <n-space :size="10" class="filter-right">
            <n-button secondary @click="resetFilters">
              <template #icon>
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
                  <path d="M3 3v5h5" />
                </svg>
              </template>
              {{ t('重置') }}
            </n-button>
            <n-button type="primary" :loading="loading" @click="runSearch">
              <template #icon>
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <circle cx="11" cy="11" r="8" />
                  <line x1="21" y1="21" x2="16.65" y2="16.65" />
                </svg>
              </template>
              {{ t('查询') }}
            </n-button>
          </n-space>
        </div>
      </div>

      <div class="list-body">
        <div class="table-body">
          <n-data-table
            :loading="loading"
            :columns="columns"
            :data="items"
            :pagination="false"
            :max-height="tableBodyHeight"
            :bordered="false"
            striped
            :row-key="(row: TokenStatsItem) => row.requestId"
          />
        </div>

        <div ref="tablePaginationRef" class="table-pagination">
          <div class="table-total">{{ t('共 {count} 条记录', { count: formatNumber(total) }) }}</div>
          <n-pagination
            :page="page"
            :page-size="pageSize"
            :item-count="total"
            :page-sizes="[20, 50, 100]"
            show-size-picker
            @update:page="handlePageChange"
            @update:page-size="handlePageSizeChange"
          />
        </div>
      </div>
    </n-card>

    <n-drawer v-model:show="drawerVisible" :width="960" placement="right">
      <n-drawer-content :title="t('{title} (调用明细)', { title: selectedTraceTitle })" closable>
        <div class="drawer-content-wrap">
          <n-data-table
            :loading="drawerLoading"
            :columns="drawerColumns"
            :data="drawerItems"
            :pagination="false"
            :bordered="false"
            :max-height="'calc(100vh - 180px)'"
            striped
            style="flex: 1 1 auto; min-height: 0;"
          />
          <div class="drawer-pagination">
            <div class="table-total">{{ t('共 {count} 条记录', { count: formatNumber(drawerTotal) }) }}</div>
            <n-pagination
              :page="drawerPage"
              :page-size="drawerPageSize"
              :item-count="drawerTotal"
              :page-sizes="[10, 20, 50]"
              show-size-picker
              @update:page="handleDrawerPageChange"
              @update:page-size="handleDrawerPageSizeChange"
            />
          </div>
        </div>
      </n-drawer-content>
    </n-drawer>

    <n-drawer v-model:show="payloadVisible" :width="720" placement="right">
      <n-drawer-content :title="selectedChatTitle" closable>
        <n-spin :show="payloadLoading" style="min-height: 200px;">
          <div v-if="chatHistory && chatHistory.messages && chatHistory.messages.length" class="chat-history-flow">
            <div
              v-for="msg in chatHistory.messages"
              :key="msg.id"
              :class="['message-card-wrapper', msg.role === 'user' ? 'msg-align-right' : 'msg-align-left']"
            >
              <!-- 消息气泡 -->
              <div :class="['message-bubble', msg.role === 'user' ? 'bubble-user' : 'bubble-assistant']" style="width: 100%;">
                <!-- 角色标头 -->
                <div class="bubble-header">
                  <span class="role-badge">{{ msg.role === 'user' ? t('用户 (User)') : t('AI 助手 (Assistant)') }}</span>
                  <span class="msg-time">{{ formatTime(msg.createdAt) }}</span>
                </div>

                <!-- 进度步骤 Timeline (仅在 assistant 角色且有 progress 时显示) -->
                <div v-if="msg.role === 'assistant' && msg.progress && msg.progress.length" class="assistant-timeline-box">
                  <div class="timeline-title">{{ t('执行步骤与进度：') }}</div>
                  <n-timeline size="medium" style="margin-top: 8px;">
                    <n-timeline-item
                      v-for="(step, sIdx) in msg.progress"
                      :key="sIdx"
                      :type="getStepType(step.status)"
                      :title="step.content"
                      :time="formatStepTime(step.timestamp)"
                    />
                  </n-timeline>
                </div>

                <!-- 回复内容 (Markdown) -->
                <div
                  v-if="msg.role === 'assistant'"
                  class="markdown-body"
                  v-html="renderMarkdown(msg.content)"
                />
                <div v-else class="user-text-content">
                  {{ msg.content }}
                </div>

                <!-- 生成的文件下载卡片 -->
                <div v-if="msg.role === 'assistant' && msg.documents && msg.documents.length" class="assistant-documents-box">
                  <div
                    v-for="(doc, docIdx) in msg.documents"
                    :key="docIdx"
                    class="doc-download-card"
                  >
                    <div class="doc-icon-box">
                      <!-- 专属直角 SVG 文件图标 -->
                      <svg v-if="isDocWord(doc.type || doc.kind)" viewBox="0 0 24 24" class="svg-doc-icon word-color">
                        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                        <path d="M14 2v6h6" />
                        <path d="M16 13H8M16 17H8" />
                      </svg>
                      <svg v-else-if="isDocPpt(doc.type || doc.kind)" viewBox="0 0 24 24" class="svg-doc-icon ppt-color">
                        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                        <path d="M14 2v6h6" />
                        <circle cx="10" cy="13" r="2" />
                        <path d="M12 15h4M10 15v3" />
                      </svg>
                      <svg v-else-if="isDocPdf(doc.type || doc.kind)" viewBox="0 0 24 24" class="svg-doc-icon pdf-color">
                        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                        <path d="M14 2v6h6" />
                        <path d="M9 15h6M12 12v6" />
                      </svg>
                      <svg v-else viewBox="0 0 24 24" class="svg-doc-icon default-doc-color">
                        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                        <path d="M14 2v6h6" />
                      </svg>
                    </div>
                    <div class="doc-info-box">
                      <div class="doc-title" :title="doc.title || doc.filename">
                        {{ doc.title || doc.filename || t('未命名文档') }}
                      </div>
                      <div class="doc-meta">
                        {{ doc.filename || t('{type} 文档', { type: (doc.type || doc.kind)?.toUpperCase() || 'DOC' }) }}
                      </div>
                    </div>
                    <div class="doc-action-box">
                      <n-button size="small" type="info" secondary @click="downloadDocument(doc)">
                        {{ t('下载') }}
                      </n-button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <div v-else class="empty-chat-state">
            {{ t('暂无聊天记录') }}
          </div>
        </n-spin>
      </n-drawer-content>
    </n-drawer>
  </div>
</template>

<script setup lang="ts">
import type { DataTableColumns } from 'naive-ui';
import { NButton, NTag, NTimeline, NTimelineItem, useMessage } from 'naive-ui';
import { computed, h, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue';
import { t } from '@/composables/i18n';
import { formatAdminDateTime, formatAdminTime } from '@/composables/adminTimezone';
import { fetchTokenStats, fetchTokenStatsDetail, fetchSessionChatHistory, type TokenStatsItem, type TokenStatsOption, type TokenStatsSummary, type TokenStatsDetail, type ChatMessageItem, type SessionChatHistory } from '@/api/token-stats';

const message = useMessage();
const loading = ref(false);

const summary = ref<TokenStatsSummary>({
  totalCalls: 0,
  totalTokens: 0,
  promptTokens: 0,
  completionTokens: 0,
  avgTokens: 0,
  lastCalledAt: null,
  last24hCalls: 0,
  last24hTokens: 0,
  activeUsers: 0,
  activeDepartments: 0,
  totalCost: 0,
  avgCost: 0,
  last24hCost: 0,
});
const items = ref<TokenStatsItem[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = ref(20);
const tableBodyHeight = ref(320);
const pageRef = ref<HTMLElement | null>(null);
const metricsRef = ref<HTMLElement | null>(null);
const tableCardRef = ref<{ $el?: HTMLElement } | null>(null);
const tablePaginationRef = ref<HTMLElement | null>(null);
let tableResizeObserver: ResizeObserver | null = null;

const departmentOptions = ref<TokenStatsOption[]>([]);
const modelOptions = ref<TokenStatsOption[]>([]);
const statusOptions = ref<TokenStatsOption[]>([]);

function statusLabel(value: string) {
  const key = String(value || '');
  if (key === 'completed') return t('Token状态.完成');
  if (key === 'user_cancelled') return t('Token状态.用户终止');
  if (key === 'runtime_error') return t('Token状态.运行错误');
  if (key === 'network_error') return t('Token状态.网络故障');
  if (key === 'failed') return t('Token状态.运行错误');
  return key || t('未记录');
}

function statusTagType(value: string) {
  const key = String(value || '');
  if (key === 'completed') return 'success';
  if (key === 'user_cancelled') return 'warning';
  return 'error';
}

const localizedStatusOptions = computed(() => {
  return statusOptions.value.map(opt => ({
    ...opt,
    label: statusLabel(opt.value)
  }));
});
const handleViewportResize = () => {
  recalcTableHeight();
};

const filters = reactive({
  q: '',
  departmentId: null as string | null,
  modelName: null as string | null,
  status: null as string | null,
  groupBy: 'user_request',
});

const drawerVisible = ref(false);
const selectedTraceId = ref('');
const selectedTraceTitle = ref('');
const drawerLoading = ref(false);
const drawerItems = ref<TokenStatsItem[]>([]);
const drawerTotal = ref(0);
const drawerPage = ref(1);
const drawerPageSize = ref(20);

const payloadVisible = ref(false);
const payloadLoading = ref(false);
const chatHistory = ref<SessionChatHistory | null>(null);
const selectedChatTitle = ref(t('对话详情'));

async function showPayloadDetails(row: TokenStatsItem) {
  chatHistory.value = null;
  selectedChatTitle.value = t('对话详情');
  payloadLoading.value = true;
  payloadVisible.value = true;
  try {
    const data = await fetchSessionChatHistory(row.requestId, row.sessionId, row.userRequestId || row.requestId);
    chatHistory.value = data;
    if (data.title) {
      let titleText = data.title.trim();
      if (titleText.length > 20) {
        titleText = titleText.slice(0, 20) + '...';
      }
      selectedChatTitle.value = t('{title} (对话详情)', { title: titleText });
    } else {
      selectedChatTitle.value = t('对话详情');
    }
  } catch (err) {
    console.error(err);
    message.error(t('加载对话详情失败'));
    payloadVisible.value = false;
  } finally {
    payloadLoading.value = false;
  }
}

function getStepType(status?: string): 'success' | 'error' | 'warning' | 'info' | 'default' {
  if (!status) return 'default';
  const s = status.toLowerCase();
  if (s === 'completed' || s === 'success' || s === 'done') return 'success';
  if (s === 'failed' || s === 'error') return 'error';
  if (s === 'running' || s === 'active' || s === 'executing') return 'warning';
  return 'info';
}

function formatStepTime(timestamp?: string) {
  return formatAdminTime(timestamp, '');
}

function isDocWord(type?: string): boolean {
  if (!type) return false;
  const t = type.toLowerCase();
  return t === 'docx' || t === 'doc' || t === 'word';
}

function isDocPpt(type?: string): boolean {
  if (!type) return false;
  const t = type.toLowerCase();
  return t === 'pptx' || t === 'ppt' || t === 'powerpoint';
}

function isDocPdf(type?: string): boolean {
  if (!type) return false;
  return type.toLowerCase() === 'pdf';
}

function downloadDocument(doc: any) {
  const url = doc.url;
  if (url) {
    window.open(url, '_blank');
  } else {
    message.warning(t('该文档暂无有效的下载链接'));
  }
}

// 简易 Markdown 解析器，支持列表、粗体、斜体、代码块及表格转换
function renderMarkdown(text?: string): string {
  if (!text) return '';
  let html = text;

  const blockPlaceholders: string[] = [];
  const stashBlock = (blockHtml: string) => {
    const key = `__BLOCK_PLACEHOLDER_${blockPlaceholders.length}__`;
    blockPlaceholders.push(blockHtml);
    return key;
  };

  // 1. 处理代码块 (```)
  html = html.replace(/```([a-zA-Z0-9_-]*)\s*([\s\S]*?)```/g, (_m, lang, code) => {
    const content = String(code || '').trim();
    const escaped = content
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
    const languageLabel = lang ? lang.toUpperCase() : 'TEXT';
    const blockHtml = `
      <div style="margin: 12px 0; background-color: #1e1e1e; border: 1px solid #333; overflow: hidden; font-family: monospace;">
        <div style="background-color: #2d2d2d; padding: 4px 12px; font-size: 11px; color: #aaa; border-bottom: 1px solid #333; display: flex; justify-content: space-between;">
          <span>${languageLabel}</span>
        </div>
        <div style="padding: 12px; overflow-x: auto; color: #d4d4d4; font-size: 13px; line-height: 1.5;">
          <pre style="margin: 0; white-space: pre;">${escaped}</pre>
        </div>
      </div>
    `;
    return stashBlock(blockHtml);
  });

  // 2. 行内代码
  html = html.replace(/`([^`]+)`/g, '<code style="font-family: monospace; font-size: 12px; background-color: #f5f5f5; color: #c7254e; padding: 2px 4px; border: 1px solid #e1e1e8; border-radius: 0px;">$1</code>');

  // 3. 粗体
  html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');

  // 4. 斜体
  html = html.replace(/\*(.*?)\*/g, '<em>$1</em>');

  // 5. 表格处理
  html = html.replace(/\|(.+)\|/g, (match, content) => {
    const cells = content.split('|').map((c: string) => c.trim()).filter((c: string) => c);
    const cellTags = cells.map((c: string) => `<td style="border: 1px solid #ddd; padding: 6px 12px;">${c}</td>`).join('');
    return `<tr>${cellTags}</tr>`;
  });
  html = html.replace(/(<tr>.*<\/tr>\n?)+/g, (match) => {
    const rows = match.split('\n').filter(r => r.trim());
    if (rows.length > 1 && rows[1].includes('---')) {
      const header = rows[0].replace(/<td/g, '<th').replace(/<\/td>/g, '</th>').replace(/border: 1px solid #ddd;/g, 'border: 1px solid #ddd; background-color: #f5f5f5; font-weight: bold; text-align: left;');
      const body = rows.slice(2).join('\n');
      return `<table style="width: 100%; border-collapse: collapse; margin: 16px 0; font-size: 13px;">${header}${body}</table>`;
    }
    return `<table style="width: 100%; border-collapse: collapse; margin: 16px 0; font-size: 13px;">${match}</table>`;
  });

  // 6. 标题 (H1-H4)
  html = html.replace(/^\s*####\s+(.+)$/gim, '<h4 style="font-size: 14px; font-weight: bold; margin-top: 12px; margin-bottom: 6px;">$1</h4>');
  html = html.replace(/^\s*###\s+(.+)$/gim, '<h3 style="font-size: 16px; font-weight: bold; margin-top: 16px; margin-bottom: 8px;">$1</h3>');
  html = html.replace(/^\s*##\s+(.+)$/gim, '<h2 style="font-size: 18px; font-weight: bold; margin-top: 20px; margin-bottom: 10px; border-bottom: 1px solid #eee; padding-bottom: 4px;">$1</h2>');
  html = html.replace(/^\s*#\s+(.+)$/gim, '<h1 style="font-size: 22px; font-weight: bold; margin-top: 24px; margin-bottom: 12px;">$1</h1>');

  // 7. 列表处理
  html = html.replace(/^- (.*$)/gim, '<li style="margin-left: 20px; list-style-type: disc;">$1</li>');
  html = html.replace(/^\d+\. (.*$)/gim, '<li style="margin-left: 20px; list-style-type: decimal;">$1</li>');

  html = html.replace(/(<li style="[^"]*list-style-type: disc;[^"]*">.*<\/li>\n?)+/g, (match) => {
    return `<ul style="margin: 8px 0; padding-left: 0;">${match.replace(/\n/g, '')}</ul>`;
  });
  html = html.replace(/(<li style="[^"]*list-style-type: decimal;[^"]*">.*<\/li>\n?)+/g, (match) => {
    return `<ol style="margin: 8px 0; padding-left: 0;">${match.replace(/\n/g, '')}</ol>`;
  });

  // 8. 换行
  html = html.replace(/\n\n/g, '<br/><br/>');
  html = html.replace(/\n/g, '<br/>');

  // 还原占位代码块
  blockPlaceholders.forEach((block, idx) => {
    html = html.replace(`__BLOCK_PLACEHOLDER_${idx}__`, block);
  });

  return html;
}

const drawerColumns = computed<DataTableColumns<TokenStatsItem>>(() => [
  {
    title: t('时间'),
    key: 'createdAt',
    width: 150,
    render: (row) => formatTime(row.createdAt),
  },
  {
    title: t('模型'),
    key: 'modelName',
    width: 160,
    ellipsis: { tooltip: true },
    render: (row) => row.modelName || t('未记录'),
  },
  {
    title: t('阶段'),
    key: 'stage',
    width: 100,
    render: (row) => row.stage || '—',
  },
  {
    title: t('状态'),
    key: 'status',
    width: 90,
    render: (row) =>
      h(
        NTag,
        {
          size: 'small',
          bordered: false,
          type: statusTagType(row.status),
        },
        { default: () => statusLabel(row.status) },
      ),
  },
  {
    title: t('Tokens'),
    key: 'tokens',
    width: 150,
    render: (row) =>
      h('div', { class: 'token-cell' }, [
        h('div', { class: 'token-total' }, formatNumber(row.totalTokens)),
        h('div', { class: 'token-breakdown' }, `P ${formatNumber(row.promptTokens)}`),
        h('div', { class: 'token-breakdown' }, `C ${formatNumber(row.completionTokens)}`),
      ]),
  },
  {
    title: t('请求 / Prompt'),
    key: 'requestTitle',
    minWidth: 260,
    ellipsis: { tooltip: true },
    render: (row) =>
      h('div', { class: 'request-cell' }, [
        h('div', { class: 'request-title' }, row.requestTitle || t('LLM 调用')),
        h('div', { class: 'request-preview' }, row.promptPreview || t('无 Prompt 预览')),
      ]),
  },
  {
    title: t('操作'),
    key: 'actions',
    width: 150,
    fixed: 'right',
    render: (row) =>
      h(
        NButton,
        {
          size: 'small',
          type: 'primary',
          ghost: true,
          onClick: () => showPayloadDetails(row),
        },
        {
          default: () => t('查看内容'),
          icon: () => h(
            'svg',
            {
              xmlns: 'http://www.w3.org/2000/svg',
              viewBox: '0 0 24 24',
              fill: 'none',
              stroke: 'currentColor',
              strokeWidth: '2',
              strokeLinecap: 'round',
              strokeLinejoin: 'round',
              style: { width: '14px', height: '14px' }
            },
            [
              h('path', { d: 'M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z' }),
              h('circle', { cx: '12', cy: '12', r: '3' }),
            ]
          )
        }
      ),
  },
]);

async function loadDrawerData() {
  if (!selectedTraceId.value) return;
  drawerLoading.value = true;
  try {
    const data = await fetchTokenStats({
      userRequestId: selectedTraceId.value,
      groupBy: 'request',
      offset: (drawerPage.value - 1) * drawerPageSize.value,
      limit: drawerPageSize.value,
    });
    drawerItems.value = data.items;
    drawerTotal.value = data.total;
  } catch (err) {
    console.error(err);
    message.error(t('加载调用明细失败'));
  } finally {
    drawerLoading.value = false;
  }
}

function showTraceDetails(row: TokenStatsItem) {
  selectedTraceId.value = row.userRequestId || row.requestId;
  let shortTitle = row.requestTitle || t('请求调用');
  if (shortTitle.length > 20) {
    shortTitle = shortTitle.slice(0, 20) + '...';
  }
  selectedTraceTitle.value = shortTitle;
  drawerPage.value = 1;
  drawerVisible.value = true;
  void loadDrawerData();
}

function handleDrawerPageChange(nextPage: number) {
  drawerPage.value = nextPage;
  void loadDrawerData();
}

function handleDrawerPageSizeChange(nextSize: number) {
  drawerPageSize.value = nextSize;
  drawerPage.value = 1;
  void loadDrawerData();
}

const columns = computed<DataTableColumns<TokenStatsItem>>(() => [
  {
    title: t('时间'),
    key: 'createdAt',
    width: 150,
    render: (row) => formatTime(row.createdAt),
  },
  {
    title: t('用户'),
    key: 'userName',
    width: 180,
    ellipsis: {
      tooltip: true,
    },
    render: (row) =>
      h('div', { class: 'user-cell' }, [
        h('div', { class: 'user-name' }, row.userName || t('未知用户')),
        h('div', { class: 'user-dept' }, row.departmentName || t('未分配部门')),
      ]),
  },
  {
    title: t('状态'),
    key: 'status',
    width: 100,
    render: (row) =>
      h(
        NTag,
        {
          size: 'small',
          bordered: false,
          type: statusTagType(row.status),
        },
        {
          default: () => statusLabel(row.status),
        },
      ),
  },
  {
    title: t('Tokens'),
    key: 'tokens',
    width: 150,
    render: (row) =>
      h('div', { class: 'token-cell' }, [
        h('div', { class: 'token-total' }, formatNumber(row.totalTokens)),
        h('div', { class: 'token-breakdown' }, `P ${formatNumber(row.promptTokens)}`),
        h('div', { class: 'token-breakdown' }, `C ${formatNumber(row.completionTokens)}`),
      ]),
  },
  {
    title: t('请求'),
    key: 'requestTitle',
    minWidth: 350,
    ellipsis: { tooltip: true },
    render: (row) =>
      h('div', { class: 'request-cell' }, [
        h('div', { class: 'request-title' }, [
          row.calls && row.calls > 1
            ? h(NTag, { size: 'small', type: 'info', bordered: false, style: { marginRight: '8px' } }, { default: () => t('调用 {count} 次 LLM', { count: row.calls ?? 0 }) })
            : null,
          h('span', row.requestTitle || t('LLM 调用')),
        ])
      ]),
  },
  {
    title: t('操作'),
    key: 'actions',
    width: 240,
    fixed: 'right',
    render: (row) => {
      const isMulti = row.calls && row.calls > 1;
      if (isMulti) {
        return h('div', { style: { display: 'flex', gap: '6px' } }, [
          h(
            NButton,
            {
              size: 'small',
              type: 'primary',
              ghost: true,
              onClick: () => showTraceDetails(row),
            },
            {
              default: () => t('调用详情'),
              icon: () => h(
                'svg',
                {
                  xmlns: 'http://www.w3.org/2000/svg',
                  viewBox: '0 0 24 24',
                  fill: 'none',
                  stroke: 'currentColor',
                  strokeWidth: '2',
                  strokeLinecap: 'round',
                  strokeLinejoin: 'round',
                  style: { width: '14px', height: '14px' }
                },
                [
                  h('line', { x1: '8', y1: '6', x2: '21', y2: '6' }),
                  h('line', { x1: '8', y1: '12', x2: '21', y2: '12' }),
                  h('line', { x1: '8', y1: '18', x2: '21', y2: '18' }),
                  h('line', { x1: '3', y1: '6', x2: '3.01', y2: '6' }),
                  h('line', { x1: '3', y1: '12', x2: '3.01', y2: '12' }),
                  h('line', { x1: '3', y1: '18', x2: '3.01', y2: '18' }),
                ]
              )
            }
          ),
          h(
            NButton,
            {
              size: 'small',
              onClick: () => showPayloadDetails(row),
            },
            {
              default: () => t('查看内容'),
              icon: () => h(
                'svg',
                {
                  xmlns: 'http://www.w3.org/2000/svg',
                  viewBox: '0 0 24 24',
                  fill: 'none',
                  stroke: 'currentColor',
                  strokeWidth: '2',
                  strokeLinecap: 'round',
                  strokeLinejoin: 'round',
                  style: { width: '14px', height: '14px' }
                },
                [
                  h('path', { d: 'M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z' }),
                  h('circle', { cx: '12', cy: '12', r: '3' }),
                ]
              )
            }
          ),
        ]);
      } else {
        return h(
          NButton,
          {
            size: 'small',
            type: 'primary',
            ghost: true,
            onClick: () => showPayloadDetails(row),
          },
          {
            default: () => t('查看内容'),
            icon: () => h(
              'svg',
              {
                xmlns: 'http://www.w3.org/2000/svg',
                viewBox: '0 0 24 24',
                fill: 'none',
                stroke: 'currentColor',
                strokeWidth: '2',
                strokeLinecap: 'round',
                strokeLinejoin: 'round',
                style: { width: '14px', height: '14px' }
              },
              [
                h('path', { d: 'M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z' }),
                h('circle', { cx: '12', cy: '12', r: '3' }),
              ]
            )
          }
        );
      }
    },
  },
]);

function formatNumber(value: number) {
  return new Intl.NumberFormat('zh-CN').format(Number(value || 0));
}

function formatCost(value: number) {
  const num = Number(value || 0);
  if (num === 0) return '0.00';
  if (num < 0.01) return num.toFixed(4);
  return num.toFixed(2);
}

function formatTime(value: string | null) {
  return formatAdminDateTime(value, '—');
}

async function loadData() {
  loading.value = true;
  try {
    const data = await fetchTokenStats({
      q: filters.q || '',
      departmentId: filters.departmentId || '',
      modelName: filters.modelName || '',
      status: filters.status || '',
      offset: (page.value - 1) * pageSize.value,
      limit: pageSize.value,
      groupBy: filters.groupBy,
    });
    summary.value = data.summary;
    items.value = data.items;
    total.value = data.total;
    departmentOptions.value = data.filterOptions.departments || [];
    modelOptions.value = data.filterOptions.models || [];
    statusOptions.value = data.filterOptions.statuses || [];
  } catch (error) {
    console.error(error);
    message.error(t('Token 统计加载失败，请稍后重试'));
  } finally {
    loading.value = false;
    await nextTick();
    recalcTableHeight();
  }
}

function recalcTableHeight() {
  const pageEl = pageRef.value;
  const metricsEl = metricsRef.value;
  const tablePaginationEl = tablePaginationRef.value;
  const tableRootEl = tableCardRef.value?.$el as HTMLElement | undefined;
  if (!pageEl || !metricsEl || !tableRootEl || !tablePaginationEl) {
    return;
  }

  const pageHeight = pageEl.clientHeight;
  const metricsHeight = metricsEl.offsetHeight;

  const pageStyle = window.getComputedStyle(pageEl);
  const rowGap = Number.parseFloat(pageStyle.rowGap || pageStyle.gap || '0') || 0;

  // metrics 和 tableCard 之间有 1 个竖向 gap。
  const sectionGaps = rowGap;

  // 获得 list-filter-row 的真实高度
  const filterRowEl = tableRootEl.querySelector('.list-filter-row') as HTMLElement | null;
  const filterHeight = filterRowEl ? filterRowEl.offsetHeight : 0;

  const tableCardOuterHeight = Math.max(0, pageHeight - metricsHeight - sectionGaps);

  const tableContentEl = tableRootEl.querySelector('.n-card__content') as HTMLElement | null;
  if (!tableContentEl) {
    return;
  }

  const contentStyle = window.getComputedStyle(tableContentEl);
  const contentPaddingTop = Number.parseFloat(contentStyle.paddingTop || '0') || 0;
  const contentPaddingBottom = Number.parseFloat(contentStyle.paddingBottom || '0') || 0;

  const available =
    tableCardOuterHeight
    - filterHeight
    - contentPaddingTop
    - contentPaddingBottom
    - tablePaginationEl.offsetHeight
    - 60; // 减去表头及预留安全高度，适当缩小 n-scrollbar-container 高度防止极小像素溢出

  tableBodyHeight.value = Math.max(220, Math.floor(available));
}

function runSearch() {
  page.value = 1;
  void loadData();
}

function resetFilters() {
  filters.q = '';
  filters.departmentId = null;
  filters.modelName = null;
  filters.status = null;
  filters.groupBy = 'user_request';
  page.value = 1;
  void loadData();
}

function handlePageChange(nextPage: number) {
  page.value = nextPage;
  void loadData();
}

function handlePageSizeChange(nextSize: number) {
  pageSize.value = nextSize;
  page.value = 1;
  void loadData();
}

onMounted(() => {
  window.addEventListener('resize', handleViewportResize);
  nextTick(() => {
    recalcTableHeight();
    if ('ResizeObserver' in window) {
      tableResizeObserver = new ResizeObserver(() => recalcTableHeight());
      if (pageRef.value) {
        tableResizeObserver.observe(pageRef.value);
      }
      if (metricsRef.value) {
        tableResizeObserver.observe(metricsRef.value);
      }
      if (tableCardRef.value?.$el) {
        tableResizeObserver.observe(tableCardRef.value.$el);
      }
      if (tablePaginationRef.value) {
        tableResizeObserver.observe(tablePaginationRef.value);
      }
    }
  });
  void loadData();
});

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleViewportResize);
  if (tableResizeObserver) {
    tableResizeObserver.disconnect();
    tableResizeObserver = null;
  }
});

watch(
  [items, total, page, pageSize, loading],
  () => {
    nextTick(() => recalcTableHeight());
  },
  { deep: true },
);
</script>

<style scoped>
.token-stats-page {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 72px);
  min-height: 0;
  min-width: 0;
  gap: 6px;
  overflow: hidden;
  padding: 12px;
}

.metrics-row {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 12px;
  flex: 0 0 auto;
}

.metric-card {
  position: relative;
  min-height: 112px;
  overflow: hidden;
  border-radius: 8px;
  color: #fff;
  box-shadow: 0 8px 18px rgba(29, 48, 94, 0.12);
}

.metric-card :deep(.n-card__content) {
  position: relative;
  z-index: 1;
  padding: 20px 20px 18px !important;
}

.metric-card-blue {
  background: linear-gradient(135deg, #366aff 0%, #4a97ff 100%);
}

.metric-card-green {
  background: linear-gradient(135deg, #12b981 0%, #27c7a0 100%);
}

.metric-card-purple {
  background: linear-gradient(135deg, #7c5cf6 0%, #a376f4 100%);
}

.metric-card-orange {
  background: linear-gradient(135deg, #f47a3d 0%, #f5a044 100%);
}

.metric-card-cyan {
  background: linear-gradient(135deg, #0ea5e9 0%, #26c6da 100%);
}

.metric-label {
  color: rgba(255, 255, 255, 0.86);
  font-size: 13px;
  font-weight: 600;
}

.metric-value {
  margin-top: 6px;
  color: #fff;
  font-size: 28px;
  font-weight: 800;
  line-height: 1.2;
}

.metric-note {
  margin-top: 6px;
  color: rgba(255, 255, 255, 0.8);
  font-size: 12px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.metric-icon {
  position: absolute;
  right: 14px;
  bottom: 12px;
  width: 42px;
  height: 42px;
  color: rgba(255, 255, 255, 0.28);
}

.metric-icon svg {
  width: 100%;
  height: 100%;
  stroke: currentColor;
  stroke-width: 1.7;
  stroke-linecap: round;
  stroke-linejoin: round;
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
  padding: 16px 20px 12px !important;
}

.list-filter-row {
  padding: 0 20px 14px;
  margin: 0 -20px 14px;
  border-bottom: 1px solid #edf1f7;
}

.filter-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
}

.filter-left {
  flex-wrap: wrap;
}

.filter-right {
  flex-wrap: wrap;
}

.filter-search {
  width: 320px;
}

.filter-select {
  width: 168px;
}

.filter-select-sm {
  width: 132px;
}

.list-body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.table-pagination {
  flex: 0 0 auto;
  margin-top: auto;
  padding: 8px 12px 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.table-body {
  flex: 1 1 auto;
  min-height: 0;
  overflow: hidden;
}

.table-body :deep(.n-data-table) {
  height: 100%;
}

.table-total {
  color: #66757c;
  font-size: 13px;
}

.user-name {
  color: #1f2b4d;
  font-weight: 600;
}

.user-dept {
  margin-top: 2px;
  color: #6d7d86;
  font-size: 12px;
}

.token-total {
  color: #1f2b4d;
  font-weight: 700;
}

.token-breakdown {
  margin-top: 2px;
  color: #6d7d86;
  font-size: 12px;
}

.request-title {
  color: #1f2b4d;
  font-weight: 600;
  white-space: normal;
  word-break: break-all;
}

.request-preview {
  margin-top: 2px;
  color: #6d7d86;
  font-size: 12px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

@media (max-width: 1400px) {
  .metrics-row {
    grid-template-columns: repeat(5, minmax(150px, 1fr));
    gap: 10px;
  }

  .metric-card :deep(.n-card__content) {
    padding: 16px 18px 14px !important;
  }

  .metric-value {
    font-size: 25px;
  }
}

@media (max-height: 860px) {
  .token-stats-page {
    padding: 10px 12px;
    gap: 6px;
  }

  .metric-card {
    min-height: 86px;
  }

  .metric-card :deep(.n-card__content) {
    padding: 12px 18px 10px !important;
  }

  .metric-label {
    font-size: 12px;
  }

  .metric-value {
    margin-top: 4px;
    font-size: 24px;
    line-height: 1.1;
  }

  .metric-note {
    margin-top: 5px;
    font-size: 12px;
  }

  .metric-icon {
    right: 12px;
    bottom: 10px;
    width: 32px;
    height: 32px;
  }

  .list-card :deep(.n-card__content) {
    padding: 12px 20px 10px !important;
  }

  .list-filter-row {
    padding-bottom: 10px;
    margin-bottom: 10px;
  }
}

.group-toggle {
  flex: 0 0 auto;
}

.drawer-content-wrap {
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 12px;
  overflow: hidden;
}

.drawer-pagination {
  flex: 0 0 auto;
  margin-top: auto;
  padding-top: 10px;
  border-top: 1px solid #eceff5;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.chat-history-flow {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 8px 4px;
}

.message-card-wrapper {
  display: flex;
  width: 100%;
}

.msg-align-left {
  justify-content: flex-start;
}

.msg-align-right {
  justify-content: flex-end;
}

.message-bubble {
  max-width: 100%;
  border: 1px solid #e2e8f0;
  padding: 14px 16px;
  background-color: #fff;
  border-radius: 0 !important; /* 直角要求 */
  box-shadow: 0 1px 3px rgba(0,0,0,0.05);
}

.bubble-user {
  background-color: #f0f7ff;
  border-color: #bfdbfe;
  color: #1e3a8a;
  border-left: 4px solid #3b82f6; /* 加强边缘区分 */
}

.bubble-assistant {
  background-color: #fff;
  border-color: #e2e8f0;
  color: #334155;
  border-left: 4px solid #10b981;
}

.bubble-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
  font-size: 12px;
  border-bottom: 1px dashed #e2e8f0;
  padding-bottom: 6px;
}

.role-badge {
  font-weight: bold;
}

.bubble-user .role-badge {
  color: #2563eb;
}

.bubble-assistant .role-badge {
  color: #059669;
}

.msg-time {
  color: #94a3b8;
}

.user-text-content {
  font-size: 14px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
}

.assistant-timeline-box {
  margin-bottom: 16px;
  background: #f8fafc;
  border: 1px solid #f1f5f9;
  padding: 12px;
  font-size: 13px;
  border-radius: 0 !important; /* 直角要求 */
}

.timeline-title {
  font-weight: 600;
  color: #475569;
  margin-bottom: 8px;
}

.markdown-body {
  font-size: 14px;
  line-height: 1.6;
  word-break: break-all;
}

.markdown-body :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 12px 0;
}

.markdown-body :deep(th), .markdown-body :deep(td) {
  border: 1px solid #cbd5e1;
  padding: 8px 12px;
}

.markdown-body :deep(th) {
  background-color: #f1f5f9;
}

.assistant-documents-box {
  margin-top: 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.doc-download-card {
  display: flex;
  align-items: center;
  gap: 12px;
  border: 1px solid #bfdbfe;
  background-color: #f0f9ff;
  padding: 10px 14px;
  border-radius: 0 !important; /* 直角要求 */
}

.doc-icon-box {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  background-color: #fff;
  border: 1px solid #e2e8f0;
}

.svg-doc-icon {
  width: 28px;
  height: 28px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.word-color {
  color: #2563eb;
}

.ppt-color {
  color: #ea580c;
}

.pdf-color {
  color: #dc2626;
}

.default-doc-color {
  color: #64748b;
}

.doc-info-box {
  flex: 1;
  min-width: 0;
}

.doc-title {
  font-size: 14px;
  font-weight: 600;
  color: #1e293b;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.doc-meta {
  font-size: 11px;
  color: #64748b;
  margin-top: 2px;
}

.doc-action-box {
  flex-shrink: 0;
}

.empty-chat-state {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 200px;
  color: #94a3b8;
  font-size: 14px;
}

:deep(.n-drawer),
:deep(.n-drawer-content),
:deep(.n-drawer-content-wrapper),
:deep(.n-drawer-body-content-wrapper) {
  border-radius: 0 !important;
}
</style>
