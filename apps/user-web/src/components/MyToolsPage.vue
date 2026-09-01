<template>
  <div class="tools-page">
    <template v-if="!editorVisible">
      <header class="tools-header">
        <div class="tools-header-left">
          <n-button secondary @click="emit('back')">
            <template #icon><n-icon><ArrowBackOutline /></n-icon></template>
            {{ t('返回对话') }}
          </n-button>
          <h1>{{ t('我的 Tools') }}</h1>
        </div>
      </header>

      <div class="metrics-row">
        <n-card v-for="item in metricCards" :key="item.key" class="metric-card" :bordered="false" size="small">
          <div class="metric-main">
            <span class="metric-icon" :class="`metric-icon-${item.key}`" v-html="item.icon"></span>
            <div class="metric-body">
              <div class="metric-label">{{ item.label }}</div>
              <div class="metric-value">{{ item.value }}</div>
            </div>
          </div>
          <div class="metric-note">{{ item.note }}</div>
        </n-card>
      </div>

      <n-card class="list-card shell-card" :bordered="false" size="large">
        <div class="list-filter-row">
          <div class="filter-toolbar">
            <n-space align="center" :size="10" class="filter-left">
              <n-input v-model:value="filters.keyword" clearable :placeholder="t('搜索名称、描述或 URL')" class="keyword-input" />
              <n-select v-model:value="filters.type" clearable :options="typeOptions" :placeholder="t('类型')" style="width: 140px" />
              <n-select v-model:value="filters.status" clearable :options="statusOptions" :placeholder="t('状态')" style="width: 140px" />
            </n-space>
            <n-space :size="10" class="filter-right">
              <n-button secondary @click="loadRows">
                <template #icon><n-icon><RefreshOutline /></n-icon></template>
                {{ t('刷新') }}
              </n-button>
              <n-button @click="openCreate('mcp')">
                <template #icon><n-icon><BuildOutline /></n-icon></template>
                {{ t('新增 MCP 服务') }}
              </n-button>
              <n-button type="primary" strong @click="openCreate('http')">
                <template #icon><n-icon><AddOutline /></n-icon></template>
                {{ t('新增 HTTP 工具') }}
              </n-button>
            </n-space>
          </div>
        </div>

        <div class="list-body">
          <n-spin :show="loading">
            <div v-if="filteredRows.length" class="tool-grid">
              <button v-for="row in filteredRows" :key="row.id" class="tool-card" type="button" @click="openEdit(row)">
                <div class="card-head">
                  <div class="card-tags">
                    <n-tag :type="row.type === 'mcp' ? 'info' : 'success'" size="small" :bordered="false">
                      {{ row.type === 'mcp' ? t('MCP 服务') : t('HTTP 工具') }}
                    </n-tag>
                    <n-tag :type="row.status === 'active' ? 'success' : 'default'" size="small" :bordered="false">
                      {{ row.status === 'active' ? t('已启用') : t('已禁用') }}
                    </n-tag>
                    <n-tag
                      :type="row.lastTestStatus === 'passed' ? 'success' : row.lastTestStatus === 'failed' ? 'error' : 'default'"
                      size="small"
                      :bordered="false"
                    >
                      {{ row.lastTestStatus === 'passed' ? t('测试通过') : row.lastTestStatus === 'failed' ? t('测试失败') : t('未测试') }}
                    </n-tag>
                  </div>
              </div>
                <div class="card-title">{{ row.name || t('未命名工具') }}</div>
                <div class="card-desc">{{ row.description || t('未填写工具说明') }}</div>
                <div class="tag-row">
                  <n-tag v-for="tag in row.tags" :key="tag" size="small" :bordered="false" class="tool-tag">{{ tag }}</n-tag>
                  <span v-if="!row.tags.length" class="no-tag">{{ t('无标签') }}</span>
                </div>
                <div class="card-footrow">
                  <span class="card-footnote">{{ formatUpdatedTime(row) }}</span>
                  <n-space :size="8" align="center" @click.stop>
                    <span class="status-switch-label">{{ row.status === 'active' ? t('启用') : t('禁用') }}</span>
                    <n-switch
                      :value="row.status === 'active'"
                      size="small"
                      @update:value="(value: boolean) => toggleStatus(row, value)"
                    />
                    <n-button class="delete-btn" size="small" tertiary type="error" @click.stop="askDelete(row)">
                      <template #icon><n-icon><TrashOutline /></n-icon></template>
                      {{ t('删除') }}
                    </n-button>
                  </n-space>
                </div>
              </button>
            </div>

            <div v-else class="empty-shell">
              <div class="empty-visual">
                <span>API</span>
                <span>MCP</span>
                <span>HTTP</span>
              </div>
              <div class="empty-title">{{ t('暂未配置 Tool') }}</div>
              <div class="empty-desc">{{ t('连接第一个 HTTP 工具或 MCP 服务，仅当前用户可用。') }}</div>
              <n-space justify="center">
                <n-button type="primary" @click="openCreate('http')">
                  <template #icon><n-icon><AddOutline /></n-icon></template>
                  {{ t('新增 HTTP 工具') }}
                </n-button>
                <n-button @click="openCreate('mcp')">
                  <template #icon><n-icon><BuildOutline /></n-icon></template>
                  {{ t('新增 MCP 服务') }}
                </n-button>
              </n-space>
            </div>
          </n-spin>
        </div>
      </n-card>
    </template>

    <template v-else>
      <header class="tools-header">
        <div class="tools-header-left">
          <n-button secondary @click="backToList">
            <template #icon><n-icon><ArrowBackOutline /></n-icon></template>
            {{ t('返回') }}
          </n-button>
          <h1>{{ editingId ? t('编辑 Tool') : t('新增 Tool') }}</h1>
        </div>
        <n-space>
          <n-button type="primary" :loading="saving" @click="saveTool">
            <template #icon><n-icon><SaveOutline /></n-icon></template>
            {{ t('保存') }}
          </n-button>
        </n-space>
      </header>

      <n-card class="step-overview shell-card" :bordered="false">
        <n-steps :current="activeStep" size="small" @update:current="handleStepChange">
          <n-step v-for="step in steps" :key="step.key" :title="step.title" :description="step.description" />
        </n-steps>
      </n-card>

      <div class="editor-layout">
        <n-card class="editor-card shell-card" :bordered="false" size="large">
          <template #header>
            <div class="editor-card-header">
              <div>
                <div class="content-title">{{ currentStep?.title }}</div>
                <div class="muted">{{ currentStep?.description }}</div>
              </div>
              <n-space :size="8" align="center">
                <n-tag :type="form.type === 'mcp' ? 'info' : 'success'" round>
                  {{ form.type === 'mcp' ? t('MCP 服务') : t('HTTP 工具') }}
                </n-tag>
                <n-tag round>{{ t('第 {step} / {total} 步', { step: activeStep, total: steps.length }) }}</n-tag>
              </n-space>
            </div>
          </template>

          <n-form ref="formRef" :model="form" :rules="rules" label-placement="top">
          <section v-if="activeKey === 'base'" class="step-panel">
            <n-grid :cols="2" :x-gap="16">
              <n-form-item-gi :label="t('连接类型')" path="type">
                <n-radio-group v-model:value="form.type" :disabled="!!editingId" @update:value="resetStepsForType">
                  <n-radio-button value="http">{{ t('HTTP 工具') }}</n-radio-button>
                  <n-radio-button value="mcp">{{ t('MCP 服务') }}</n-radio-button>
                </n-radio-group>
              </n-form-item-gi>
              <n-form-item-gi :label="t('启用状态')">
                <n-switch v-model:value="enabledSwitch">
                  <template #checked>{{ t('启用') }}</template>
                  <template #unchecked>{{ t('停用') }}</template>
                </n-switch>
              </n-form-item-gi>
            </n-grid>

            <n-form-item :label="t('名称')" path="name">
              <n-input v-model:value="form.name" :placeholder="t('例如：CRM 客户查询')" />
            </n-form-item>
            <n-form-item :label="t('工具说明')" path="description">
              <div class="description-wrap">
                <n-input v-model:value="form.description" type="textarea" :autosize="{ minRows: 3, maxRows: 5 }" :placeholder="t('说明这个工具能做什么。')" />
                <n-button secondary :loading="generatingDescription" @click="generateDescription">
                  <template #icon><n-icon><SparklesOutline /></n-icon></template>
                  {{ t('AI 生成描述') }}
                </n-button>
              </div>
            </n-form-item>
            <n-form-item :label="t('标签')">
              <n-dynamic-tags v-model:value="form.tags" />
            </n-form-item>
          </section>

          <section v-if="activeKey === 'request'" class="step-panel">
            <template v-if="form.type === 'http'">
              <n-grid :cols="4" :x-gap="16">
                <n-form-item-gi :span="3" :label="t('请求地址')" path="config.url">
                  <n-input v-model:value="form.config.url" placeholder="https://api.example.com/customers/{customerId}" />
                </n-form-item-gi>
                <n-form-item-gi :label="t('请求方法')">
                  <n-select v-model:value="form.config.method" :options="methodOptions" />
                </n-form-item-gi>
              </n-grid>
            </template>
            <template v-else>
              <n-form-item :label="t('MCP 服务地址')" path="config.endpoint">
                <n-input v-model:value="form.config.endpoint" placeholder="https://mcp.example.com/mcp" />
              </n-form-item>
            </template>

            <n-grid :cols="3" :x-gap="16">
              <n-form-item-gi :label="t('鉴权方式')">
                <n-select v-model:value="form.config.authType" :options="authOptions" />
              </n-form-item-gi>
              <n-form-item-gi v-if="form.config.authType === 'api_key'" :label="t('Header 名称')">
                <n-input v-model:value="form.config.apiKeyHeader" placeholder="X-API-Key" />
              </n-form-item-gi>
              <n-form-item-gi v-if="form.config.authType !== 'none'" :span="form.config.authType === 'api_key' ? 1 : 2" label="Token / Key">
                <n-input v-model:value="form.config.authToken" type="password" show-password-on="click" />
              </n-form-item-gi>
            </n-grid>
          </section>

          <section v-if="activeKey === 'input'" class="step-panel">
            <div class="section-head">
              <div>
                <div class="section-title">{{ t('参数列表') }}</div>
                <div class="muted">{{ t('配置名称、描述、类型和传入位置，帮助 Agent 正确组装请求。') }}</div>
              </div>
              <n-button type="primary" ghost @click="addInputNode()">
                <template #icon><n-icon><AddOutline /></n-icon></template>
                {{ t('添加参数') }}
              </n-button>
            </div>
            <SchemaEditor
              mode="input"
              :nodes="inputSchema"
              @add-child="addInputNode"
              @remove="removeInputNode"
            />
          </section>

          <section v-if="activeKey === 'output'" class="step-panel">
            <div class="section-head">
              <div></div>
              <n-space :size="8">
                <n-button type="primary" secondary :disabled="!canInferOutputSchema" @click="inferOutputSchemaFromTest">
                  <template #icon><n-icon><SparklesOutline /></n-icon></template>
                  {{ t('一键生成出参') }}
                </n-button>
                <n-button type="primary" ghost @click="addOutputNode()">
                  <template #icon><n-icon><AddOutline /></n-icon></template>
                  {{ t('添加字段') }}
                </n-button>
              </n-space>
            </div>
            <SchemaEditor
              mode="output"
              :nodes="outputSchema"
              @add-child="addOutputNode"
              @remove="removeOutputNode"
            />
          </section>

          <section v-if="activeKey === 'mcpTools'" class="step-panel">
            <div class="section-head">
              <div>
                <div class="section-title">{{ t('发现 MCP 工具') }}</div>
                <div class="muted">{{ t('保存 MCP 服务后发现远程服务暴露的 tools，并选择允许 Agent 使用的项。') }}</div>
              </div>
              <n-button type="primary" :disabled="!editingId" :loading="discovering" @click="discoverTools">
                <template #icon><n-icon><SearchOutline /></n-icon></template>
                {{ t('发现 MCP Tools') }}
              </n-button>
            </div>
            <n-alert v-if="!editingId" type="warning" :bordered="false">{{ t('请先保存 MCP 服务，再发现远程 tools。') }}</n-alert>
            <div class="mcp-tools">
              <n-space vertical>
                <n-checkbox
                  v-for="tool in discoveredTools"
                  :key="tool.name"
                  :checked="selectedMcpToolNames.includes(tool.name)"
                  @update:checked="(checked: boolean) => toggleMcpTool(tool.name, checked)"
                >
                  {{ tool.name }} <span class="muted">{{ tool.description }}</span>
                </n-checkbox>
              </n-space>
              <span v-if="!discoveredTools.length" class="muted">{{ t('还没有发现 MCP tools。') }}</span>
            </div>
          </section>

        </n-form>

          <template #footer>
            <div class="step-actions">
              <n-button v-if="activeStep > 1" @click="goPrevStep">
                <template #icon><n-icon><ChevronBackOutline /></n-icon></template>
                {{ t('上一步') }}
              </n-button>
              <n-button v-if="activeStep < steps.length" type="primary" @click="goNextStep">
                <template #icon><n-icon><ChevronForwardOutline /></n-icon></template>
                {{ t('下一步') }}
              </n-button>
              <n-button secondary :loading="saving" @click="saveTool">
                <template #icon><n-icon><SaveOutline /></n-icon></template>
                {{ t('保存草稿') }}
              </n-button>
              <n-button v-if="activeStep === steps.length" type="primary" :loading="saving" @click="saveTool">
                <template #icon><n-icon><CheckmarkDoneOutline /></n-icon></template>
                {{ t('完成并保存') }}
              </n-button>
            </div>
          </template>
        </n-card>

        <n-card class="debug-card shell-card" :bordered="false" size="large">
          <div class="aside-title-row">
            <div>
              <div class="content-title">{{ t('调试测试') }}</div>
              <div class="muted">{{ testResultText ? (testResultOk ? t('最近测试已通过') : t('最近测试失败')) : t('可直接测试当前草稿') }}</div>
            </div>
            <n-tag :type="testResultText ? (testResultOk ? 'success' : 'error') : 'default'" round>
              {{ testResultText ? (testResultOk ? t('已通过') : t('失败')) : t('未测试') }}
            </n-tag>
          </div>

          <div class="debug-overview">
            <span>{{ form.type === 'mcp' ? 'MCP' : String(form.config.method || 'GET') }}</span>
            <strong>{{ debugEndpointText }}</strong>
          </div>

          <template v-if="form.type === 'http'">
            <div v-for="group in groupedDebugNodes" :key="group.location" class="debug-param-group">
              <div v-if="group.nodes.length" class="debug-group-title">{{ group.label }}</div>
              <div v-for="node in group.nodes" :key="node.id" class="debug-param-row">
                <label>
                  {{ node.name || t('未命名参数') }}
                  <span v-if="node.required">*</span>
                </label>
                <n-input v-model:value="debugValues[node.id]" size="small" :placeholder="node.description || node.type" />
              </div>
            </div>
            <n-empty v-if="flatInputNodes.length === 0" :description="t('暂无入参')" size="small" />
          </template>
          <template v-else>
            <n-form-item :label="t('MCP 工具')">
              <n-select v-model:value="debugMcpToolName" :options="mcpToolOptions" filterable size="small" />
            </n-form-item>
            <n-form-item :label="t('参数 JSON')">
              <n-input v-model:value="debugMcpArguments" type="textarea" :autosize="{ minRows: 4, maxRows: 8 }" placeholder='{"key":"value"}' />
            </n-form-item>
          </template>

          <n-button block type="primary" :loading="testing" @click="runTest">
            <template #icon><n-icon><PlayOutline /></n-icon></template>
            {{ t('运行测试') }}
          </n-button>

          <div v-if="testResult" class="test-summary">
            <div class="test-metrics-row">
              <div>
                <span>{{ t('状态') }}</span>
                <strong :class="testResultOk ? 'success-text' : 'error-text'">{{ testResult.message || (testResultOk ? t('测试通过') : t('测试失败')) }}</strong>
              </div>
              <div>
                <span>{{ t('耗时') }}</span>
                <strong>{{ testResult.durationMs ?? '-' }} ms</strong>
              </div>
            </div>
            <div v-if="testResult.responseSummary || testResult.message" class="response-summary">
              {{ String(testResult.responseSummary || testResult.message) }}
            </div>
          </div>

          <div v-if="testResultText || Object.keys(lastRequest).length" class="debug-json-scroll">
            <div class="result-panel">
              <div class="result-title">{{ t('调用预览') }}</div>
              <pre class="json-pre-panel"><code>{{ JSON.stringify(debugRequestPreview, null, 2) }}</code></pre>
            </div>
            <div v-if="testResultText" class="result-panel">
              <div class="result-title result-title-row">
                <span>{{ t('响应体') }}</span>
                <n-button v-if="canInferOutputSchema" size="small" type="primary" secondary @click="inferOutputSchemaFromTest">
                  <template #icon><n-icon><SparklesOutline /></n-icon></template>
                  {{ t('生成出参') }}
                </n-button>
              </div>
              <pre class="json-pre-panel"><code>{{ testResultText }}</code></pre>
            </div>
          </div>
        </n-card>
      </div>
    </template>

    <n-modal
      v-model:show="deleteConfirmVisible"
      preset="dialog"
      type="warning"
      :title="t('删除 Tool')"
      :positive-text="t('删除')"
      :negative-text="t('取消')"
      :positive-button-props="{ type: 'error', loading: deleting }"
      @positive-click="confirmDelete"
    >
      {{ t('确定删除「{name}」吗？删除后不可恢复。', { name: pendingDeleteRow?.name || t('未命名工具') }) }}
    </n-modal>

    <n-modal
      v-model:show="statusConfirmVisible"
      preset="dialog"
      type="warning"
      :title="pendingStatusValue ? t('启用 Tool') : t('禁用 Tool')"
      :positive-text="pendingStatusValue ? t('确认启用') : t('确认禁用')"
      :negative-text="t('取消')"
      :positive-button-props="{ type: pendingStatusValue ? 'primary' : 'warning', loading: statusUpdating }"
      @positive-click="confirmToggleStatus"
    >
      {{ pendingStatusText }}
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { t } from '../composables/i18n'
import { computed, defineComponent, h, onMounted, ref, watch } from 'vue'
import {
  NAlert,
  NButton,
  NCard,
  NCheckbox,
  NDynamicTags,
  NEmpty,
  NForm,
  NFormItem,
  NFormItemGi,
  NGrid,
  NIcon,
  NInput,
  NModal,
  NRadioButton,
  NRadioGroup,
  NSelect,
  NSpace,
  NStep,
  NSteps,
  NSpin,
  NSwitch,
  NTag,
  useMessage,
  type FormInst,
  type FormRules,
} from 'naive-ui'
import {
  AddOutline,
  ArrowBackOutline,
  BuildOutline,
  CheckmarkDoneOutline,
  ChevronBackOutline,
  ChevronForwardOutline,
  PlayOutline,
  RefreshOutline,
  SaveOutline,
  SearchOutline,
  SparklesOutline,
  TrashOutline,
} from '@vicons/ionicons5'
import {
  createTool,
  deleteTool,
  discoverMcpTools,
  fetchTools,
  generateToolDescription,
  patchTool,
  testTool,
  testDraftTool,
  updateTool,
  type ExternalToolItem,
  type ToolPayload,
  type ToolType,
} from '../api/tools'
import { formatAppShortDateTime, parseAppDate } from '../composables/appTimezone'
import { enabledMcpToolNames, mcpActivationError, nextMcpToolSelection, toolStatusConfirmText } from '../utils/toolActivation'

type SchemaType = 'String' | 'Integer' | 'Number' | 'Boolean' | 'Object' | 'Array' | 'ArrayObject'
type ParamLocation = 'Header' | 'Query' | 'Body' | 'Path'
type ResponseMode = 'summarized' | 'original' | 'answer'

interface SchemaNode {
  id: string
  name: string
  description: string
  type: SchemaType
  location?: ParamLocation
  required?: boolean
  responseMode?: ResponseMode
  children?: SchemaNode[]
}

interface FlatSchemaNode extends SchemaNode {
  depth: number
}

const SchemaEditor = defineComponent({
  name: 'SchemaEditor',
  props: {
    nodes: { type: Array as () => SchemaNode[], required: true },
    mode: { type: String as () => 'input' | 'output', required: true },
  },
  emits: ['add-child', 'remove'],
  setup(schemaProps, { emit }) {
    const schemaTypeOptions = ['String', 'Integer', 'Number', 'Boolean', 'Object', 'Array', 'ArrayObject']
      .map((value) => ({ label: value, value }))
    const locationOptions = ['Header', 'Query', 'Body', 'Path'].map((value) => ({ label: value, value }))
    const responseModeOptions = computed(() => [
      { label: t('大模型总结'), value: 'summarized' },
      { label: t('原始返回'), value: 'original' },
      { label: t('主要答案'), value: 'answer' },
    ])

    function flatten(nodes: SchemaNode[], depth = 0): Array<{ node: SchemaNode; depth: number }> {
      return nodes.flatMap((node) => [
        { node, depth },
        ...flatten(node.children || [], depth + 1),
      ])
    }

    return () => {
      const flat = flatten(schemaProps.nodes)
      if (!flat.length) {
        return h(NEmpty, { description: schemaProps.mode === 'input' ? t('还没有定义入参') : t('还没有定义出参') })
      }
      return h('div', { class: 'schema-editor' }, [
        h(
          'div',
          { class: ['schema-grid', 'schema-head', schemaProps.mode === 'input' ? 'input-grid' : 'output-grid'] },
          (schemaProps.mode === 'input'
            ? [t('参数名称'), t('参数描述'), t('类型'), t('传入位置'), t('必填'), t('操作')]
            : [t('字段名称'), t('字段描述'), t('类型'), t('使用方式'), t('操作')]
          ).map((text) => h('span', text)),
        ),
        flat.map(({ node, depth }) => h(
          'div',
          { key: node.id, class: ['schema-grid', schemaProps.mode === 'input' ? 'input-grid' : 'output-grid'] },
          [
            h(NInput, {
              value: node.name,
              placeholder: depth > 0 && node.type === 'Array' ? '[Array Item]' : t('请输入'),
              style: { marginLeft: `${depth * 24}px`, width: `calc(100% - ${depth * 24}px)` },
              'onUpdate:value': (value: string) => { node.name = value.replace(/[^a-zA-Z0-9_[\] ]/g, '') },
            }),
            h(NInput, {
              value: node.description,
              placeholder: schemaProps.mode === 'input' ? t('帮助 Agent 理解如何提取参数') : t('帮助 Agent 理解返回字段'),
              'onUpdate:value': (value: string) => { node.description = value },
            }),
            h(NSelect, {
              value: node.type,
              options: schemaTypeOptions,
              'onUpdate:value': (value: SchemaType) => {
                node.type = value
                if (value === 'Array' && node.children?.length) {
                  node.children.forEach((child) => { child.name = '[Array Item]' })
                }
              },
            }),
            schemaProps.mode === 'input'
              ? h(NSelect, {
                value: node.location || 'Query',
                options: locationOptions,
                'onUpdate:value': (value: ParamLocation) => { node.location = value },
              })
              : h(NSelect, {
                value: node.responseMode || 'summarized',
                options: responseModeOptions.value,
                'onUpdate:value': (value: ResponseMode) => { node.responseMode = value },
              }),
            schemaProps.mode === 'input'
              ? h(NSwitch, {
                value: Boolean(node.required),
                'onUpdate:value': (value: boolean) => { node.required = value },
              })
              : null,
            h('div', { class: 'schema-actions' }, [
              h(NButton, {
                size: 'small',
                quaternary: true,
                disabled: !['Object', 'Array', 'ArrayObject'].includes(node.type),
                onClick: () => emit('add-child', node.id),
              }, {
                icon: () => h(NIcon, null, { default: () => h(AddOutline) }),
                default: () => t('子项'),
              }),
              h(NButton, {
                size: 'small',
                quaternary: true,
                type: 'error',
                onClick: () => emit('remove', node.id),
              }, {
                icon: () => h(NIcon, null, { default: () => h(TrashOutline) }),
                default: () => t('删除'),
              }),
            ]),
          ],
        )),
      ])
    }
  },
})

const props = defineProps<{
  userId: string | null
  mainId: string
}>()

const emit = defineEmits<{ back: [] }>()
const message = useMessage()

const rows = ref<ExternalToolItem[]>([])
const loading = ref(false)
const saving = ref(false)
const deleting = ref(false)
const statusUpdating = ref(false)
const testing = ref(false)
const discovering = ref(false)
const generatingDescription = ref(false)
const editorVisible = ref(false)
const deleteConfirmVisible = ref(false)
const statusConfirmVisible = ref(false)
const editingId = ref('')
const activeStep = ref(1)
const pendingDeleteRow = ref<ExternalToolItem | null>(null)
const pendingStatusRow = ref<ExternalToolItem | null>(null)
const pendingStatusValue = ref(false)
const pendingStatusText = ref('')
const formRef = ref<FormInst | null>(null)
const inputSchema = ref<SchemaNode[]>([])
const outputSchema = ref<SchemaNode[]>([])
const debugValues = ref<Record<string, string>>({})
const debugMcpToolName = ref('')
const debugMcpArguments = ref('{}')
const lastRequest = ref<Record<string, any>>({})
const testResult = ref<Record<string, any> | null>(null)
const testResultText = ref('')
const testResultOk = ref(false)
const discoveredTools = ref<ExternalToolItem['discoveredTools']>([])

const form = ref<ToolPayload>(emptyForm('http'))
const selectedMcpToolNames = computed(() => enabledMcpToolNames(form.value.config))
const enabledSwitch = computed({
  get: () => form.value.status === 'active',
  set: (value: boolean) => {
    if ((form.value.status === 'active') === value) return
    const nextStatus = value ? 'active' : 'disabled'
    const error = mcpActivationError({ ...form.value, status: nextStatus })
    if (error) {
      message.warning(error)
      return
    }
    if (!window.confirm(toolStatusConfirmText({ ...form.value, discoveredTools: discoveredTools.value }, value))) return
    form.value.status = nextStatus
  },
})

const filters = ref({
  keyword: '',
  type: null as ToolType | null,
  status: null as 'active' | 'disabled' | null,
})

const typeOptions = computed(() => [
  { label: t('HTTP 工具'), value: 'http' },
  { label: t('MCP 服务'), value: 'mcp' },
])
const statusOptions = computed(() => [
  { label: t('启用'), value: 'active' },
  { label: t('禁用'), value: 'disabled' },
])
const methodOptions = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'].map((value) => ({ label: value, value }))
const authOptions = computed(() => [
  { label: t('无需鉴权'), value: 'none' },
  { label: 'Bearer Token', value: 'bearer' },
  { label: 'API Key Header', value: 'api_key' },
])
const steps = computed(() => {
  if (form.value.type === 'mcp') {
    return [
      { key: 'base', title: t('基础信息'), description: t('名称与说明') },
      { key: 'request', title: t('连接配置'), description: t('地址、鉴权和 Headers') },
      { key: 'mcpTools', title: t('发现工具'), description: t('读取远程 MCP 工具 Schema') },
    ]
  }
  return [
    { key: 'base', title: t('基础信息'), description: t('名称与说明') },
    { key: 'request', title: t('请求配置'), description: t('URL、请求方法、鉴权和 Headers') },
    { key: 'input', title: t('入参定义'), description: t('Agent 调用时需要填写的参数') },
    { key: 'output', title: t('出参定义'), description: t('响应字段含义和使用方式') },
  ]
})
const activeKey = computed(() => steps.value[activeStep.value - 1]?.key || 'base')
const currentStep = computed(() => steps.value[activeStep.value - 1])
const flatInputNodes = computed<FlatSchemaNode[]>(() => flattenSchema(inputSchema.value))
const groupedDebugNodes = computed(() => {
  const groups = [
    { location: 'Path', label: 'Path', nodes: [] as FlatSchemaNode[] },
    { location: 'Query', label: 'Query', nodes: [] as FlatSchemaNode[] },
    { location: 'Header', label: 'Header', nodes: [] as FlatSchemaNode[] },
    { location: 'Body', label: 'Body', nodes: [] as FlatSchemaNode[] },
  ]
  for (const node of flatInputNodes.value) {
    const group = groups.find((item) => item.location === (node.location || 'Query'))
    group?.nodes.push(node)
  }
  return groups
})
const mcpToolOptions = computed(() => discoveredTools.value.map((tool) => ({ label: tool.name, value: tool.name })))
const debugEndpointText = computed(() => String(form.value.type === 'mcp' ? form.value.config.endpoint || t('未配置地址') : form.value.config.url || t('未配置地址')))
const debugRequestPreview = computed(() => {
  if (!Object.keys(lastRequest.value).length) return {}
  if (form.value.type === 'mcp') {
    return {
      toolId: editingId.value || null,
      toolName: debugMcpToolName.value,
      request: { arguments: lastRequest.value.arguments || {} },
    }
  }
  return buildHttpExecutionPreview(lastRequest.value)
})
const canInferOutputSchema = computed(() => form.value.type === 'http' && Boolean(extractTestResponseBody()))

const rules: FormRules = {
  name: [{ required: true, message: t('请填写名称'), trigger: ['input', 'blur'] }],
  description: [{ required: true, message: t('请填写工具说明'), trigger: ['input', 'blur'] }],
}

const filteredRows = computed(() => {
  const keyword = filters.value.keyword.trim().toLowerCase()
  return rows.value
    .filter((row) => {
      const keywordHit = !keyword
        || row.name.toLowerCase().includes(keyword)
        || row.description.toLowerCase().includes(keyword)
        || row.usageHint.toLowerCase().includes(keyword)
        || String(row.config?.url || row.config?.endpoint || '').toLowerCase().includes(keyword)
      return keywordHit
        && (!filters.value.type || row.type === filters.value.type)
        && (!filters.value.status || row.status === filters.value.status)
    })
    .sort((a, b) => timeValue(a.createdAt) - timeValue(b.createdAt))
})

const metricCards = computed(() => {
  const total = rows.value.length
  const enabled = rows.value.filter((row) => row.status === 'active').length
  const mcp = rows.value.filter((row) => row.type === 'mcp').length
  const passed = rows.value.filter((row) => row.lastTestStatus === 'passed').length
  return [
    { key: 'total', icon: '<svg viewBox="0 0 24 24"><path d="M14.7 6.3a4 4 0 0 0-5.66 5.66l-5.3 5.3a2 2 0 1 0 2.83 2.83l5.3-5.3a4 4 0 0 0 5.66-5.66" /></svg>', label: t('Tool 总数'), value: total, note: t('当前空间下我的全部工具') },
    { key: 'enabled', icon: '<svg viewBox="0 0 24 24"><path d="M20 6 9 17l-5-5" /></svg>', label: t('已启用'), value: enabled, note: total ? t('启用率 {percent}%', { percent: Math.round((enabled / total) * 100) }) : t('当前暂无工具') },
    { key: 'mcp', icon: '<svg viewBox="0 0 24 24"><path d="M12 3v6" /><path d="M6 15h12" /><circle cx="12" cy="12" r="3" /><circle cx="6" cy="18" r="3" /><circle cx="18" cy="18" r="3" /></svg>', label: t('MCP 服务'), value: mcp, note: t('远程 MCP 服务数量') },
    { key: 'pass', icon: '<svg viewBox="0 0 24 24"><path d="M9 12l2 2 4-4" /><circle cx="12" cy="12" r="9" /></svg>', label: t('测试通过'), value: passed, note: t('最近测试通过数量') },
  ]
})

function formatToolTime(value?: string | null, fallback = t('暂无记录')) {
  return formatAppShortDateTime(value, fallback)
}

function timeValue(value?: string | null) {
  return parseAppDate(value)?.getTime() || 0
}

function formatUpdatedTime(row: ExternalToolItem) {
  const displayTime = formatToolTime(row.updatedAt, '')
  return displayTime ? t('更新时间：{time}', { time: displayTime }) : t('更新时间：暂无记录')
}

function emptyForm(type: ToolType): ToolPayload {
  return {
    name: '',
    type,
    description: '',
    usageHint: '',
    tags: [],
    status: 'disabled',
    config: {
      method: 'GET',
      url: '',
      endpoint: '',
      authType: 'none',
      apiKeyHeader: 'X-API-Key',
      authToken: '',
      timeoutSeconds: 20,
      inputSchema: [],
      outputSchema: [],
      resultPath: '',
      enabledToolNames: [],
    },
  }
}

function parseJson(text: string, fallback: any) {
  const trimmed = String(text || '').trim()
  if (!trimmed) return fallback
  return JSON.parse(trimmed)
}

function uid() {
  return `schema_${Date.now()}_${Math.random().toString(16).slice(2, 8)}`
}

function normalizeSchemaNode(value: any, mode: 'input' | 'output'): SchemaNode | null {
  if (!value || typeof value !== 'object') return null
  const rawType = String(value.type || 'String')
  const type = ['String', 'Integer', 'Number', 'Boolean', 'Object', 'Array', 'ArrayObject'].includes(rawType)
    ? rawType as SchemaType
    : 'String'
  const children = Array.isArray(value.children)
    ? value.children.map((item: any) => normalizeSchemaNode(item, mode)).filter(Boolean) as SchemaNode[]
    : []
  return {
    id: String(value.id || uid()),
    name: String(value.name || ''),
    description: String(value.description || value.desc || ''),
    type,
    location: mode === 'input' ? String(value.location || 'Query') as ParamLocation : undefined,
    required: mode === 'input' ? Boolean(value.required ?? value.require ?? true) : false,
    responseMode: mode === 'output' ? String(value.responseMode || value.response_mode || 'summarized') as ResponseMode : undefined,
    children,
  }
}

function normalizeSchema(value: any, mode: 'input' | 'output'): SchemaNode[] {
  return Array.isArray(value)
    ? value.map((item) => normalizeSchemaNode(item, mode)).filter(Boolean) as SchemaNode[]
    : []
}

function serializeSchema(nodes: SchemaNode[], mode: 'input' | 'output'): any[] {
  return nodes.map((node) => {
    const payload: Record<string, any> = {
      name: node.name,
      description: node.description,
      type: node.type,
      children: serializeSchema(node.children || [], mode),
    }
    if (mode === 'input') {
      payload.location = node.location || 'Query'
      payload.required = Boolean(node.required)
    } else {
      payload.responseMode = node.responseMode || 'summarized'
    }
    return payload
  })
}

function flattenSchema(nodes: SchemaNode[], depth = 0): FlatSchemaNode[] {
  return nodes.flatMap((node) => [
    { ...node, depth },
    ...flattenSchema(node.children || [], depth + 1),
  ])
}

function findSchemaNode(nodes: SchemaNode[], id: string): SchemaNode | null {
  for (const node of nodes) {
    if (node.id === id) return node
    const child = findSchemaNode(node.children || [], id)
    if (child) return child
  }
  return null
}

function removeSchemaNode(nodes: SchemaNode[], id: string): boolean {
  const index = nodes.findIndex((node) => node.id === id)
  if (index >= 0) {
    nodes.splice(index, 1)
    return true
  }
  return nodes.some((node) => removeSchemaNode(node.children || [], id))
}

function newSchemaNode(partial: Partial<SchemaNode> = {}): SchemaNode {
  return {
    id: uid(),
    name: '',
    description: '',
    type: 'String',
    location: 'Query',
    required: true,
    responseMode: 'summarized',
    children: [],
    ...partial,
  }
}

function addInputNode(parentId?: string) {
  if (!parentId) {
    inputSchema.value.push(newSchemaNode())
    return
  }
  const parent = findSchemaNode(inputSchema.value, parentId)
  if (parent) {
    parent.children ||= []
    parent.children.push(newSchemaNode({ name: parent.type === 'Array' ? '[Array Item]' : '', location: parent.location || 'Body' }))
  }
}

function removeInputNode(id: string) {
  removeSchemaNode(inputSchema.value, id)
}

function addOutputNode(parentId?: string) {
  if (!parentId) {
    outputSchema.value.push(newSchemaNode({ location: undefined, required: false }))
    return
  }
  const parent = findSchemaNode(outputSchema.value, parentId)
  if (parent) {
    parent.children ||= []
    parent.children.push(newSchemaNode({
      name: parent.type === 'Array' ? '[Array Item]' : '',
      location: undefined,
      required: false,
      responseMode: parent.responseMode || 'summarized',
    }))
  }
}

function removeOutputNode(id: string) {
  removeSchemaNode(outputSchema.value, id)
}

function buildPayload(): ToolPayload {
  return {
    ...form.value,
    config: {
      ...form.value.config,
      inputSchema: serializeSchema(inputSchema.value, 'input'),
      outputSchema: serializeSchema(outputSchema.value, 'output'),
      enabledToolNames: Array.isArray(form.value.config.enabledToolNames) ? form.value.config.enabledToolNames : [],
    },
  }
}

function parseDebugValue(value: string, type: SchemaType) {
  if (type === 'Number' || type === 'Integer') return Number(value)
  if (type === 'Boolean') return value === 'true'
  if (type === 'Object' || type === 'Array' || type === 'ArrayObject') {
    try {
      return JSON.parse(value || (type === 'Object' ? '{}' : '[]'))
    } catch {
      return value
    }
  }
  return value
}

function buildHttpTestInput() {
  const query: Record<string, unknown> = {}
  const body: Record<string, unknown> = {}
  const headers: Record<string, unknown> = {}
  const path: Record<string, unknown> = {}
  for (const node of flatInputNodes.value) {
    if (!node.name) continue
    const value = parseDebugValue(debugValues.value[node.id] || '', node.type)
    if (node.location === 'Body') body[node.name] = value
    else if (node.location === 'Header') headers[node.name] = value
    else if (node.location === 'Path') path[node.name] = value
    else query[node.name] = value
  }
  return { query, body, headers, path }
}

function getUrlPath(value: unknown) {
  const text = String(value || '').trim()
  if (!text) return ''
  try {
    const parsed = new URL(text)
    return `${parsed.pathname.replace(/^\/+/, '')}${parsed.search || ''}`
  } catch {
    return text.replace(/^\/+/, '')
  }
}

function buildHttpExecutionPreview(input: Record<string, any>) {
  const params = flatInputNodes.value
    .filter((node) => node.name)
    .map((node) => {
      const location = node.location || 'Query'
      const bucket = location === 'Body'
        ? input.body
        : location === 'Header'
          ? input.headers
          : location === 'Path'
            ? input.path
            : input.query
      const values = bucket && typeof bucket === 'object' ? bucket as Record<string, unknown> : {}
      return {
        _id: node.id,
        children: node.children || [],
        name: node.name,
        desc: node.description || '',
        type: node.type || 'String',
        location,
        require: Boolean(node.required),
        value: values[node.name],
      }
    })
  return {
    toolId: editingId.value || null,
    toolName: form.value.name || '',
    path: getUrlPath(form.value.config.url),
    method: String(form.value.config.method || 'GET').toUpperCase(),
    request: { params },
  }
}

function inferSchemaType(value: unknown): SchemaType {
  if (Array.isArray(value)) return 'Array'
  if (value === null || value === undefined) return 'String'
  if (typeof value === 'boolean') return 'Boolean'
  if (typeof value === 'number') return Number.isInteger(value) ? 'Integer' : 'Number'
  if (typeof value === 'object') return 'Object'
  return 'String'
}

function readableType(type: SchemaType) {
  const labels: Record<SchemaType, string> = {
    String: '文本',
    Integer: '整数',
    Number: '数值',
    Boolean: '布尔值',
    Object: '对象',
    Array: '数组',
    ArrayObject: '对象数组',
  }
  return labels[type] || type
}

function splitFieldTokens(value: string) {
  return String(value || '')
    .replace(/([a-z0-9])([A-Z])/g, '$1_$2')
    .split(/[^a-zA-Z0-9]+/)
    .map((part) => part.toLowerCase())
    .filter(Boolean)
}

function commonFieldMeaning(name: string, path: string) {
  const tokens = splitFieldTokens(`${path}_${name}`)
  const tokenSet = new Set(tokens)
  const joined = tokens.join('_')
  if (tokenSet.has('id') || joined.endsWith('_id')) return '通常表示记录或实体的唯一标识'
  if (tokenSet.has('name')) return '通常表示名称'
  if (tokenSet.has('title')) return '通常表示标题'
  if (tokenSet.has('status') || tokenSet.has('state')) return '通常表示状态'
  if (tokenSet.has('type') || tokenSet.has('category')) return '通常表示类型或分类'
  if (tokenSet.has('count') || tokenSet.has('total') || tokenSet.has('num') || tokenSet.has('quantity')) return '通常表示数量或统计值'
  if (tokenSet.has('amount') || tokenSet.has('price') || tokenSet.has('cost') || tokenSet.has('fee')) return '通常表示金额或价格'
  if (tokenSet.has('date') || tokenSet.has('time') || tokenSet.has('created') || tokenSet.has('updated')) return '通常表示日期或时间'
  if (tokenSet.has('url') || tokenSet.has('link') || tokenSet.has('uri')) return '通常表示链接地址'
  if (tokenSet.has('desc') || tokenSet.has('description') || tokenSet.has('summary')) return '通常表示描述或摘要'
  if (tokenSet.has('content') || tokenSet.has('text')) return '通常表示正文内容'
  if (tokenSet.has('message') || tokenSet.has('msg')) return '通常表示消息文本'
  if (tokenSet.has('code')) return '通常表示编码或返回码'
  if (tokenSet.has('score') || tokenSet.has('rate') || tokenSet.has('ratio')) return '通常表示分值、比例或评分'
  return ''
}

function sampleArrayItem(values: unknown[]): unknown {
  const objectItems = values.filter((item) => item && typeof item === 'object' && !Array.isArray(item))
  if (!objectItems.length) return values.find((item) => item !== null && item !== undefined)
  return objectItems.slice(0, 10).reduce<Record<string, unknown>>((merged, item) => {
    Object.assign(merged, item as Record<string, unknown>)
    return merged
  }, {})
}

function childFieldSummary(value: unknown) {
  let record: Record<string, unknown> | null = null
  if (Array.isArray(value)) {
    const sample = sampleArrayItem(value)
    if (sample && typeof sample === 'object' && !Array.isArray(sample)) record = sample as Record<string, unknown>
  } else if (value && typeof value === 'object') {
    record = value as Record<string, unknown>
  }
  if (!record) return ''
  const keys = Object.keys(record).filter(Boolean).slice(0, 6)
  if (!keys.length) return ''
  return `，包含 ${keys.join('、')}${Object.keys(record).length > keys.length ? ' 等' : ''} 子字段`
}

function schemaDescriptionForValue(name: string, value: unknown, path = name) {
  const type = inferSchemaType(value)
  const fieldPath = path || name
  const meaning = commonFieldMeaning(name, fieldPath)
  if (Array.isArray(value)) return `数组字段 \`${fieldPath}\`${childFieldSummary(value)}，用于描述列表型响应数据`
  if (value && typeof value === 'object') return `对象字段 \`${fieldPath}\`${childFieldSummary(value)}，用于承载结构化响应数据`
  return `响应字段 \`${fieldPath}\`，类型为${readableType(type)}${meaning ? `，${meaning}` : ''}`
}

function inferNodesFromRecord(record: Record<string, unknown>, prefix = ''): SchemaNode[] {
  return Object.entries(record)
    .filter(([name]) => String(name || '').trim())
    .map(([name, value]) => inferNodeFromValue(name, value, prefix ? `${prefix}.${name}` : name))
}

function inferNodeFromValue(name: string, value: unknown, path = name): SchemaNode {
  const type = inferSchemaType(value)
  const node = newSchemaNode({
    name,
    type,
    location: undefined,
    required: false,
    responseMode: type === 'Object' || type === 'Array' ? 'summarized' : 'original',
    description: schemaDescriptionForValue(name, value, path),
    children: [],
  })
  if (type === 'Object' && value && typeof value === 'object' && !Array.isArray(value)) {
    node.children = inferNodesFromRecord(value as Record<string, unknown>, path)
  } else if (type === 'Array' && Array.isArray(value)) {
    const sample = sampleArrayItem(value)
    if (sample && typeof sample === 'object' && !Array.isArray(sample)) {
      node.children = inferNodesFromRecord(sample as Record<string, unknown>, `${path}[]`)
    }
  }
  return node
}

function parseResultPath(path: string): string[] {
  return String(path || '')
    .replace(/\[(\d+)\]/g, '.$1')
    .split('.')
    .map((part) => part.trim())
    .filter(Boolean)
}

function resolvePath(value: unknown, path: string): unknown {
  let current = value
  for (const part of parseResultPath(path)) {
    if (Array.isArray(current)) {
      const index = Number(part)
      if (!Number.isInteger(index) || index < 0 || index >= current.length) return undefined
      current = current[index]
    } else if (current && typeof current === 'object') {
      const record = current as Record<string, unknown>
      if (!(part in record)) return undefined
      current = record[part]
    } else {
      return undefined
    }
  }
  return current
}

function wrapNodesWithResultPath(nodes: SchemaNode[], value: unknown, path: string): SchemaNode[] {
  const parts = parseResultPath(path).filter((part) => !/^\d+$/.test(part))
  if (!parts.length) return nodes
  let childNodes = nodes
  let childValue = value
  for (let index = parts.length - 1; index >= 0; index -= 1) {
    const isLeaf = index === parts.length - 1
    const nodeValue = isLeaf ? childValue : {}
    childNodes = [
      newSchemaNode({
        name: parts[index],
        type: isLeaf ? inferSchemaType(nodeValue) : 'Object',
        location: undefined,
        required: false,
        responseMode: 'summarized',
        description: isLeaf
          ? schemaDescriptionForValue(parts[index], nodeValue, parts.slice(0, index + 1).join('.'))
          : `对象字段 \`${parts.slice(0, index + 1).join('.')}\`，主要结果路径中的结构化响应数据`,
        children: childNodes,
      }),
    ]
    childValue = {}
  }
  return childNodes
}

function extractTestResponseBody(): unknown {
  if (!testResult.value) return undefined
  if ('raw' in testResult.value) return testResult.value.raw
  return undefined
}

function schemaFromTestResponse(): SchemaNode[] {
  const raw = extractTestResponseBody()
  if (raw === undefined || raw === null) return []
  const resultPath = String(form.value.config.resultPath || '').trim()
  const selected = resultPath ? resolvePath(raw, resultPath) : raw
  if (selected === undefined || selected === null) return []
  let nodes: SchemaNode[]
  if (Array.isArray(selected)) {
    const sample = sampleArrayItem(selected)
    if (sample && typeof sample === 'object' && !Array.isArray(sample)) {
      nodes = inferNodesFromRecord(sample as Record<string, unknown>, resultPath ? `${resultPath}[]` : '')
    } else {
      nodes = [inferNodeFromValue('items', selected, resultPath || 'items')]
    }
  } else if (selected && typeof selected === 'object') {
    nodes = inferNodesFromRecord(selected as Record<string, unknown>, resultPath)
  } else {
    nodes = [inferNodeFromValue('value', selected, resultPath || 'value')]
  }
  return resultPath ? wrapNodesWithResultPath(nodes, selected, resultPath) : nodes
}

function isAutoGeneratedDescription(value: unknown) {
  const text = String(value || '').trim()
  return !text || text.startsWith('响应字段 `') || text.startsWith('对象字段 `') || text.startsWith('数组字段 `')
}

function countSchemaNodes(nodes: SchemaNode[]): number {
  return nodes.reduce(
    (total, node) => total + 1 + countSchemaNodes(node.children || []),
    0,
  )
}

function mergeSchemaNodes(target: SchemaNode[], incoming: SchemaNode[]): number {
  let added = 0
  for (const node of incoming) {
    const existing = target.find((item) => item.name === node.name)
    if (!existing) {
      target.push(node)
      added += countSchemaNodes([node])
      continue
    }
    if (!existing.type || existing.type === 'String') existing.type = node.type
    if (isAutoGeneratedDescription(existing.description)) existing.description = node.description
    if (!existing.responseMode) existing.responseMode = node.responseMode
    existing.children ||= []
    added += mergeSchemaNodes(existing.children, node.children || [])
  }
  return added
}

function inferOutputSchemaFromTest() {
  const inferred = schemaFromTestResponse()
  if (!inferred.length) {
    message.warning(t('当前测试响应无法生成出参定义'))
    return
  }
  const added = mergeSchemaNodes(outputSchema.value, inferred)
  if (added > 0) {
    message.success(t('已添加 {count} 个出参字段', { count: added }))
  } else {
    message.info(t('出参定义已包含响应中的字段'))
  }
}

function hydrateEditor(row: ExternalToolItem) {
  form.value = {
    name: row.name,
    type: row.type,
    description: row.description,
    usageHint: row.usageHint,
    tags: [...row.tags],
    status: row.status,
    config: { ...emptyForm(row.type).config, ...(row.config || {}) },
  }
  inputSchema.value = normalizeSchema(form.value.config.inputSchema || [], 'input')
  outputSchema.value = normalizeSchema(form.value.config.outputSchema || [], 'output')
  discoveredTools.value = Array.isArray(row.discoveredTools) ? row.discoveredTools : []
  form.value.config.enabledToolNames = enabledMcpToolNames(form.value.config)
  debugValues.value = {}
  debugMcpToolName.value = discoveredTools.value[0]?.name || ''
  debugMcpArguments.value = '{}'
  lastRequest.value = {}
  testResultText.value = ''
  testResult.value = null
  testResultOk.value = false
}

function openCreate(type: ToolType) {
  editingId.value = ''
  activeStep.value = 1
  form.value = emptyForm(type)
  inputSchema.value = []
  outputSchema.value = []
  discoveredTools.value = []
  debugValues.value = {}
  debugMcpToolName.value = ''
  debugMcpArguments.value = '{}'
  lastRequest.value = {}
  testResultText.value = ''
  testResult.value = null
  editorVisible.value = true
}

function openEdit(row: ExternalToolItem) {
  editingId.value = row.id
  activeStep.value = 1
  hydrateEditor(row)
  editorVisible.value = true
}

function backToList() {
  editorVisible.value = false
  activeStep.value = 1
  void loadRows()
}

function handleStepChange(step: number) {
  if (step < 1 || step > steps.value.length) return
  activeStep.value = step
}

function goPrevStep() {
  if (activeStep.value > 1) activeStep.value -= 1
}

function goNextStep() {
  if (activeStep.value < steps.value.length) activeStep.value += 1
}

function resetStepsForType() {
  if (activeStep.value > steps.value.length) {
    activeStep.value = steps.value.length
  }
  form.value.config.enabledToolNames = Array.isArray(form.value.config.enabledToolNames) ? form.value.config.enabledToolNames : []
}

async function loadRows() {
  if (!props.userId) return
  loading.value = true
  try {
    rows.value = await fetchTools(props.userId, props.mainId)
  } catch (error: any) {
    message.error(error?.response?.data?.detail || t('加载工具连接失败'))
  } finally {
    loading.value = false
  }
}

async function saveTool() {
  if (!props.userId) return
  try {
    await formRef.value?.validate()
    const payload = buildPayload()
    const activationError = mcpActivationError(payload)
    if (activationError) {
      message.warning(activationError)
      activeStep.value = steps.value.findIndex((step) => step.key === 'mcpTools') + 1 || activeStep.value
      return
    }
    saving.value = true
    const saved = editingId.value
      ? await updateTool(editingId.value, props.userId, props.mainId, payload)
      : await createTool(props.userId, props.mainId, payload)
    editingId.value = saved.id
    hydrateEditor(saved)
    message.success(t('Tool 已保存'))
    await loadRows()
  } catch (error: any) {
    if (error?.message) message.error(error.response?.data?.detail || error.message || t('保存失败'))
  } finally {
    saving.value = false
  }
}

async function generateDescription() {
  if (!form.value.name.trim()) {
    message.warning(t('请先填写名称'))
    return
  }
  generatingDescription.value = true
  try {
    const result = await generateToolDescription({
      name: form.value.name,
      type: form.value.type,
      existingDescription: form.value.description,
    })
    form.value.description = String(result.description || '').trim()
  } catch (error: any) {
    message.error(error?.response?.data?.detail || t('生成失败'))
  } finally {
    generatingDescription.value = false
  }
}

async function discoverTools() {
  if (!props.userId || !editingId.value) return
  discovering.value = true
  try {
    const result = await discoverMcpTools(editingId.value, props.userId, props.mainId)
    discoveredTools.value = result.tools || []
    const discoveredNames = new Set(discoveredTools.value.map((item) => String(item.name || '').trim()).filter(Boolean))
    form.value.config.enabledToolNames = selectedMcpToolNames.value.filter((name) => discoveredNames.has(name))
    if (mcpActivationError(buildPayload())) {
      form.value.status = 'disabled'
    }
    message.success(result.message || t('发现 {count} 个 MCP tools', { count: discoveredTools.value.length }))
    await loadRows()
  } catch (error: any) {
    message.error(error?.response?.data?.detail || t('发现 MCP tools 失败'))
  } finally {
    discovering.value = false
  }
}

async function runTest() {
  if (!props.userId) return
  testing.value = true
  const startedAt = performance.now()
  try {
    const input = form.value.type === 'mcp'
      ? {
        toolName: debugMcpToolName.value,
        arguments: parseJson(debugMcpArguments.value, {}),
      }
      : buildHttpTestInput()
    lastRequest.value = input
    const payload = buildPayload()
    const result = editingId.value
      ? await testTool(editingId.value, props.userId, props.mainId, input)
      : await testDraftTool(props.userId, props.mainId, payload, input)
    testResult.value = result
    testResultOk.value = result.success !== false && result.status !== 'failed'
    testResultText.value = JSON.stringify(result, null, 2)
    await loadRows()
  } catch (error: any) {
    const configuredTimeout = Number(form.value.config.timeoutSeconds || 15)
    const rawMessage = String(error?.response?.data?.detail || error?.message || '').trim()
    const isTimeout = error?.code === 'ECONNABORTED' || /timeout|timed out|超时/i.test(rawMessage)
    const errorMessage = isTimeout
      ? t('请求超时：超过 {seconds} 秒未收到响应', { seconds: configuredTimeout })
      : (rawMessage || t('测试失败'))
    testResultOk.value = false
    testResult.value = {
      success: false,
      status: 'failed',
      errorCode: isTimeout ? 'timeout' : 'request_failed',
      message: errorMessage,
      responseSummary: errorMessage,
      durationMs: Math.round(performance.now() - startedAt),
    }
    testResultText.value = JSON.stringify(testResult.value, null, 2)
  } finally {
    testing.value = false
  }
}

function toggleMcpTool(name: string, checked: boolean) {
  const next = nextMcpToolSelection(selectedMcpToolNames.value, name, checked)
  if (next.error) {
    message.warning(next.error)
    return
  }
  form.value.config.enabledToolNames = next.names
}

async function toggleStatus(row: ExternalToolItem, enabled: boolean) {
  if (!props.userId) return
  const error = mcpActivationError({ ...row, status: enabled ? 'active' : 'disabled' })
  if (error) {
    message.warning(error)
    return
  }
  pendingStatusRow.value = row
  pendingStatusValue.value = enabled
  pendingStatusText.value = toolStatusConfirmText(row, enabled)
  statusConfirmVisible.value = true
}

async function confirmToggleStatus() {
  if (!props.userId || !pendingStatusRow.value) return false
  statusUpdating.value = true
  try {
    await patchTool(pendingStatusRow.value.id, props.userId, props.mainId, { status: pendingStatusValue.value ? 'active' : 'disabled' })
    message.success(pendingStatusValue.value ? t('Tool 已启用') : t('Tool 已禁用'))
    statusConfirmVisible.value = false
    pendingStatusRow.value = null
    await loadRows()
  } catch (error: any) {
    message.error(error?.response?.data?.detail || t('状态更新失败'))
    return false
  } finally {
    statusUpdating.value = false
  }
  return true
}

function askDelete(row: ExternalToolItem) {
  pendingDeleteRow.value = row
  deleteConfirmVisible.value = true
}

async function confirmDelete() {
  if (!props.userId || !pendingDeleteRow.value) return false
  deleting.value = true
  try {
    await deleteTool(pendingDeleteRow.value.id, props.userId, props.mainId)
    message.success(t('Tool 已删除'))
    pendingDeleteRow.value = null
    deleteConfirmVisible.value = false
    await loadRows()
  } catch (error: any) {
    message.error(error?.response?.data?.detail || t('删除失败'))
    return false
  } finally {
    deleting.value = false
  }
  return true
}

onMounted(loadRows)
watch(() => [props.userId, props.mainId], () => {
  void loadRows()
})
</script>

<style scoped>
.tools-page {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
  background: #f6f8fc;
  padding: 12px;
}

.tools-header {
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

.tools-header h1 {
  margin: 0;
  color: #101c3d;
  font-size: 20px;
  line-height: 1.2;
  font-weight: 800;
}

.tools-header-left {
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

.metrics-row {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.metric-card,
.list-card {
  border-radius: 8px;
}

.list-card {
  width: 100%;
  margin: 0;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.step-overview {
  flex: 0 0 auto;
  padding: 2px 6px;
}

.editor-card {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.editor-layout {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(700px, 1fr) 420px;
  gap: 16px;
}

.editor-card :deep(.n-card__content) {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: auto;
}

.editor-card :deep(.n-form) {
  min-height: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
}

.debug-card {
  min-height: 0;
  overflow: hidden;
}

.debug-card :deep(.n-card__content) {
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-height: 0;
  overflow: auto;
}

.editor-card-header,
.section-head,
.aside-title-row,
.step-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
}

.content-title,
.section-title {
  color: #17233d;
  font-size: 16px;
  font-weight: 800;
}

.step-panel {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-height: 0;
  flex: 1;
}

.step-actions {
  justify-content: flex-end;
}

.debug-overview {
  display: flex;
  align-items: center;
  gap: 10px;
  border: 1px solid #e6edf7;
  border-radius: 8px;
  background: #f8fbff;
  padding: 10px 12px;
}

.debug-overview span {
  flex: 0 0 auto;
  color: #2563eb;
  font-size: 12px;
  font-weight: 800;
}

.debug-overview strong {
  min-width: 0;
  color: #17233d;
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.debug-param-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.debug-group-title {
  color: #64748b;
  font-size: 12px;
  font-weight: 800;
}

.debug-param-row {
  display: grid;
  grid-template-columns: 112px minmax(0, 1fr);
  gap: 8px;
  align-items: center;
}

.debug-param-row label {
  min-width: 0;
  color: #34415a;
  font-size: 12px;
  font-weight: 700;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.debug-param-row label span {
  color: #dc2626;
}

.test-summary {
  overflow: hidden;
  border: 1px solid #e6edf7;
  border-radius: 8px;
  background: #f8fbff;
}

.test-metrics-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: stretch;
}

.test-metrics-row > div {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  padding: 9px 12px;
}

.test-metrics-row > div:last-child {
  border-left: 1px solid #e6edf7;
}

.test-metrics-row span {
  flex: none;
  color: #64748b;
  font-size: 12px;
}

.test-metrics-row strong {
  min-width: 0;
  font-size: 12px;
  overflow-wrap: anywhere;
}

.success-text {
  color: #16a34a;
}

.error-text {
  color: #dc2626;
}

.response-summary {
  padding: 9px 12px;
  border-top: 1px solid #e6edf7;
  color: #475569;
  font-size: 12px;
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.debug-json-scroll {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 0;
}

.result-panel {
  border: 1px solid #e6edf7;
  border-radius: 8px;
  background: #fbfdff;
  overflow: hidden;
}

.result-title {
  padding: 8px 10px;
  border-bottom: 1px solid #edf2f8;
  color: #334155;
  font-size: 12px;
  font-weight: 800;
}

.result-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.json-pre-panel {
  margin: 0;
  max-height: 220px;
  overflow: auto;
  padding: 10px;
  color: #17233d;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
}

.schema-editor {
  flex: 1;
  min-height: 180px;
  max-height: calc(100vh - 450px);
  display: flex;
  flex-direction: column;
  gap: 8px;
  overflow: auto;
  padding-bottom: 2px;
}

.schema-editor :deep(.schema-grid) {
  display: grid;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border: 1px solid #e7edf7;
  border-radius: 8px;
  background: #fff;
  width: 100%;
}

.schema-editor :deep(.schema-grid.input-grid) {
  min-width: 900px;
  grid-template-columns: 180px minmax(260px, 1fr) 140px 140px 72px 132px;
}

.schema-editor :deep(.schema-grid.output-grid) {
  min-width: 820px;
  grid-template-columns: 180px minmax(300px, 1fr) 140px 140px 132px;
}

.schema-editor :deep(.schema-grid .n-input),
.schema-editor :deep(.schema-grid .n-base-selection) {
  min-width: 0;
}

.schema-editor :deep(.schema-head) {
  color: #6a7890;
  font-size: 12px;
  font-weight: 700;
  background: #f7f9fd;
  border-color: #eef2f8;
}

.schema-editor :deep(.schema-actions) {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 4px;
}

.list-card :deep(.n-card__content) {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.metric-card {
  border: 1px solid #e6ebf5;
  background: #fff;
  box-shadow: 0 4px 12px rgba(29, 54, 110, 0.04);
}

.metric-main {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.metric-body {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.metric-icon {
  width: 44px;
  height: 44px;
  border-radius: 50%;
  display: grid;
  place-items: center;
}

.metric-icon :deep(svg) {
  width: 20px;
  height: 20px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.metric-icon-total { color: #2d63ff; background: #eaf0ff; }
.metric-icon-enabled { color: #0f9964; background: #e8f8ef; }
.metric-icon-mcp { color: #7456e0; background: #f0ebff; }
.metric-icon-pass { color: #d9860a; background: #fff2df; }

.metric-label {
  color: #606f8a;
  font-size: 12px;
  line-height: 1.3;
}

.metric-value {
  color: #0f1f45;
  font-size: 24px;
  font-weight: 600;
  line-height: 1.1;
}

.metric-note {
  margin-top: 6px;
  color: #708099;
  font-size: 12px;
}

.filter-toolbar {
  align-items: center;
  display: flex;
  justify-content: space-between;
  gap: 14px;
}

.filter-left,
.filter-right {
  flex-wrap: wrap;
}

.keyword-input {
  width: 360px;
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

.tool-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 12px;
}

.tool-card {
  min-height: 188px;
  padding: 14px;
  border: 1px solid rgba(28, 45, 82, 0.08);
  border-radius: 8px;
  background: #fff;
  box-shadow: 0 8px 18px rgba(15, 31, 69, 0.06), 0 1px 2px rgba(15, 31, 69, 0.04);
  display: flex;
  flex-direction: column;
  gap: 10px;
  text-align: left;
  cursor: pointer;
  transition: border-color 0.2s ease, box-shadow 0.2s ease, transform 0.2s ease;
}

.tool-card:hover {
  border-color: rgba(54, 106, 255, 0.36);
  box-shadow: 0 14px 34px rgba(33, 58, 126, 0.14), 0 4px 10px rgba(33, 58, 126, 0.08);
  transform: translateY(-2px);
}

.card-head,
.card-footrow {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.card-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.card-footnote,
.no-tag,
.muted {
  color: #7a8797;
  font-size: 12px;
}

.status-switch-label {
  color: #5f6f85;
  font-size: 12px;
  white-space: nowrap;
}

.card-title {
  color: #17233d;
  font-size: 16px;
  font-weight: 800;
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

.tag-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  min-height: 24px;
}

.card-footrow {
  margin-top: auto;
}

.card-footnote {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.delete-btn {
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.16s ease;
}

.tool-card:hover .delete-btn {
  opacity: 1;
  pointer-events: auto;
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
}

.empty-visual {
  display: flex;
  gap: 8px;
}

.empty-visual span {
  width: 54px;
  height: 36px;
  border-radius: 10px;
  border: 1px solid #d8e2f2;
  background: #fff;
  color: #2d63ff;
  display: grid;
  place-items: center;
  font-weight: 700;
  font-size: 12px;
}

.empty-title {
  color: #101c3d;
  font-size: 24px;
  line-height: 1.2;
  font-weight: 800;
}

.empty-desc {
  color: #65748c;
  font-size: 14px;
}

.tool-modal {
  width: min(920px, calc(100vw - 32px));
}

.description-wrap,
.mcp-tools {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.test-result {
  margin: 0;
  max-height: 220px;
  overflow: auto;
  white-space: pre-wrap;
}

@media (max-width: 1200px) {
  .metrics-row,
  .tool-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 768px) {
  .metrics-row,
  .tool-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .filter-toolbar {
    flex-direction: column;
    align-items: stretch;
  }

  .keyword-input {
    width: 100%;
  }
}
</style>
