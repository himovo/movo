<template>
  <div class="tool-edit-page">
    <div class="edit-layout">
      <div class="edit-main">
        <n-card :bordered="false" class="step-overview shell-card">
          <n-steps class="clickable-steps" :current="activeStep" size="small" @update:current="handleStepChange">
            <n-step v-for="step in steps" :key="step.key" :title="step.title" :description="step.description" />
          </n-steps>
        </n-card>

        <n-card :bordered="false" class="content-card shell-card">
          <template #header>
            <div class="content-card-header">
              <div>
                <div class="content-title">{{ currentStep?.title }}</div>
                <div class="section-muted">{{ currentStep?.description }}</div>
              </div>
              <n-space :size="8" align="center">
                <n-tag :type="form.type === 'mcp' ? 'info' : 'success'" round>
                  {{ form.type === 'mcp' ? t('legacy.mcp_service') : t('legacy.http_tool') }}
                </n-tag>
                <n-tag round>
                  {{ t('legacy.step', { step: activeStep, total: steps.length }) }}
                </n-tag>
              </n-space>
            </div>
          </template>

          <template #footer>
            <div class="step-actions">
              <n-button secondary @click="backToList">
                <template #icon><ToolIcon name="back" /></template>
                {{ t('legacy.back') }}
              </n-button>
              <n-button v-if="activeStep > 1" @click="goPrevStep">
                <template #icon><ToolIcon name="back" /></template>
                {{ t('legacy.previous') }}
              </n-button>
              <n-button v-if="activeStep < steps.length" type="primary" @click="goNextStep">
                <template #icon><ToolIcon name="next" /></template>
                {{ t('legacy.next') }}
              </n-button>
              <n-button secondary :loading="saving" @click="saveDraft">
                <template #icon><ToolIcon name="save" /></template>
                {{ t('legacy.save_draft') }}
              </n-button>
              <n-button v-if="activeStep === steps.length" type="primary" :loading="saving" @click="saveTool">
                <template #icon><ToolIcon name="check" /></template>
                {{ t('legacy.finish_save') }}
              </n-button>
            </div>
          </template>

          <div v-if="loading" class="loading-placeholder">
            <n-skeleton text :repeat="6" />
          </div>
          <template v-else>
            <n-form ref="formRef" :model="form" :rules="rules" label-placement="top">
              <section v-if="activeKey === 'base'" class="step-panel">
                <n-form-item v-if="isCreate" :label="t('legacy.connection_type')" path="type">
                  <n-radio-group v-model:value="form.type" @update:value="changeType">
                    <n-radio-button value="http">{{ t('legacy.http_interface_tool') }}</n-radio-button>
                    <n-radio-button value="mcp">{{ t('legacy.remote_mcp_service') }}</n-radio-button>
                  </n-radio-group>
                </n-form-item>

                <n-grid :cols="2" :x-gap="18">
                  <n-form-item-gi :label="t('legacy.name_1be7ae4')" path="name">
                    <n-input v-model:value="form.name" :placeholder="t('legacy.example_crm_customer_query')" />
                  </n-form-item-gi>
                  <n-form-item-gi :label="t('legacy.status_5691b37')">
                    <n-switch v-model:value="enabledSwitch">
                      <template #checked>{{ t('legacy.active') }}</template>
                      <template #unchecked>{{ t('legacy.disabled') }}</template>
                    </n-switch>
                  </n-form-item-gi>
                </n-grid>

                <n-form-item :label="t('legacy.tool_description')" path="description">
                  <div class="description-input-wrap">
                    <n-button class="generate-desc-button" quaternary circle :loading="generatingDescription" @click="generateDescriptionFromName" :title="t('legacy.ai_generate_description')">
                      <ToolIcon v-if="!generatingDescription" name="sparkles" />
                    </n-button>
                    <n-input v-model:value="form.description" type="textarea" :autosize="{ minRows: 3, maxRows: 5 }" :placeholder="t('legacy.describe_what_this_tool_does')" />
                  </div>
                </n-form-item>
                <n-form-item :label="t('legacy.tags')">
                  <n-dynamic-tags v-model:value="form.tags" />
                </n-form-item>
              </section>

              <section v-if="activeKey === 'request'" class="step-panel">
                <template v-if="form.type === 'http'">
                  <n-grid :cols="4" :x-gap="18">
                    <n-form-item-gi :span="3" :label="t('legacy.request_url')" path="config.url">
                      <n-input v-model:value="form.config.url" :placeholder="t('https://api.example.com/customers/{customerId}')" />
                    </n-form-item-gi>
                    <n-form-item-gi :label="t('legacy.request_method')">
                      <n-select v-model:value="form.config.method" :options="methodOptions" />
                    </n-form-item-gi>
                  </n-grid>
                </template>
                <template v-else>
                  <n-form-item :label="t('legacy.mcp_endpoint')" path="config.endpoint">
                    <n-input v-model:value="form.config.endpoint" :placeholder="t('https://mcp.example.com/mcp')" />
                  </n-form-item>
                </template>

                <n-grid :cols="3" :x-gap="18">
                  <n-form-item-gi :label="t('legacy.authentication')">
                    <n-select v-model:value="form.config.authType" :options="authOptions" />
                  </n-form-item-gi>
                  <n-form-item-gi v-if="form.config.authType === 'api_key'" :label="t('legacy.header_name')" path="config.apiKeyHeader" required>
                    <n-input v-model:value="form.config.apiKeyHeader" :placeholder="t('X-API-Key')" />
                  </n-form-item-gi>
                  <n-form-item-gi v-if="form.config.authType !== 'none'" :span="form.config.authType === 'api_key' ? 1 : 2" :label="t('Token / Key')" path="config.authToken" required>
                    <n-input v-model:value="form.config.authToken" type="password" show-password-on="click" />
                  </n-form-item-gi>
                </n-grid>

                <n-grid :cols="3" :x-gap="18">
                  <n-form-item-gi :label="t('legacy.timeout_seconds')">
                    <n-input-number v-model:value="form.config.timeoutSeconds" :min="1" :max="120" />
                  </n-form-item-gi>
                </n-grid>

                <div class="section-head">
                  <div>
                    <div class="section-title">{{ t('legacy.fixed_headers') }}</div>
                    <div class="section-muted">{{ t('legacy.used_for_tenant_channel_or_internal_auth_header_info') }}</div>
                  </div>
                  <n-button size="small" @click="addHeader">
                    <template #icon><ToolIcon name="add" /></template>
                    {{ t('legacy.add_header') }}
                  </n-button>
                </div>
                <div class="compact-table">
                  <div class="compact-row compact-head header-grid">
                    <span>{{ t('legacy.header_name') }}</span>
                    <span>{{ t('legacy.value') }}</span>
                    <span></span>
                  </div>
                  <div v-for="item in headerRows" :key="item.id" class="compact-row header-grid">
                    <n-input v-model:value="item.name" placeholder="X-Tenant" />
                    <n-input v-model:value="item.value" placeholder="default" />
                    <n-button quaternary type="error" @click="removeHeader(item.id)">
                      <template #icon><ToolIcon name="trash" /></template>
                      {{ t('legacy.delete') }}
                    </n-button>
                  </div>
                  <n-empty v-if="headerRows.length === 0" :description="t('legacy.no_fixed_headers')" size="small" />
                </div>
              </section>

              <section v-if="activeKey === 'input'" class="step-panel flex-panel">
                <div class="section-head">
                  <div></div>
                  <n-button type="primary" ghost @click="addInputNode()">
                    <template #icon><ToolIcon name="add" /></template>
                    {{ t('legacy.add_parameter') }}
                  </n-button>
                </div>
                <SchemaEditor
                  mode="input"
                  :nodes="inputSchema"
                  @add-child="addInputNode"
                  @remove="removeInputNode"
                />
              </section>

              <section v-if="activeKey === 'output'" class="step-panel flex-panel">
                <div class="section-head">
                  <div></div>
                  <n-space :size="8">
                    <n-button :disabled="!canInferOutputSchema" @click="inferOutputSchemaFromTest">
                      <template #icon><ToolIcon name="schema" /></template>
                      {{ t('legacy.generate_from_response') }}
                    </n-button>
                    <n-button type="primary" ghost @click="addOutputNode()">
                      <template #icon><ToolIcon name="add" /></template>
                      {{ t('legacy.add_field_f2772f0') }}
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
                    <div class="section-title">{{ t('legacy.discover_mcp_tools') }}</div>
                    <div class="section-muted">{{ t('legacy.after_saving_connection_discover_tools_exposed_by_remote_services') }}</div>
                  </div>
                  <n-button type="primary" :loading="discovering" :disabled="!toolId" @click="discoverTools">
                    <template #icon><ToolIcon name="search" /></template>
                    {{ t('legacy.discover_tools') }}
                  </n-button>
                </div>

                <n-alert v-if="!toolId" type="warning" :bordered="false">{{ t('legacy.please_save_mcp_service_first_then_discover_remote_tools') }}</n-alert>
                <div v-else class="mcp-tool-list">
                  <div v-for="tool in discoveredTools" :key="tool.name" class="mcp-tool-card">
                    <div class="mcp-tool-main">
                      <n-checkbox :checked="enabledToolNames.includes(tool.name)" @update:checked="(checked: boolean) => toggleMcpTool(tool.name, checked)" />
                      <div>
                        <div class="mcp-tool-name">{{ tool.name }}</div>
                        <div class="section-muted">{{ tool.description || t('legacy.no_description') }}</div>
                      </div>
                    </div>
                    <n-collapse>
                      <n-collapse-item :title="t('legacy.input_schema')" :name="tool.name">
                        <n-code :code="JSON.stringify(tool.inputSchema || {}, null, 2)" language="json" word-wrap />
                      </n-collapse-item>
                    </n-collapse>
                  </div>
                  <n-empty v-if="discoveredTools.length === 0" :description="t('legacy.no_mcp_tools_discovered_yet')" />
                </div>
              </section>

              <section v-if="activeKey === 'debug'" class="step-panel">
                <div class="debug-grid">
                  <div class="debug-left">
                    <div class="section-head">
                      <div>
                        <div class="section-title">{{ t('legacy.test_input') }}</div>
                        <div class="section-muted">{{ t('legacy.fill_in_a_real_call_according_to_the_input') }}</div>
                      </div>
                      <n-button type="primary" :loading="testing" :disabled="!toolId" @click="runDebug">
                        <template #icon><ToolIcon name="play" /></template>
                        {{ t('legacy.run_test') }}
                      </n-button>
                    </div>
                    <n-alert v-if="!toolId" type="warning" :bordered="false">{{ t('legacy.please_save_the_tool_first_before_running_test') }}</n-alert>

                    <template v-if="form.type === 'http'">
                      <div v-for="node in flatInputNodes" :key="node.id" class="debug-param-row">
                        <label>
                          {{ node.name || t('legacy.unnamed_parameter') }}
                          <span v-if="node.required">*</span>
                        </label>
                        <n-input v-model:value="debugValues[node.id]" :placeholder="node.description || node.type" />
                      </div>
                      <n-empty v-if="flatInputNodes.length === 0" :description="t('legacy.please_add_parameters_in_the_input_definition_first')" size="small" />
                    </template>
                    <template v-else>
                      <n-form-item :label="t('legacy.mcp_tool')">
                        <n-select v-model:value="debugMcpToolName" :options="mcpToolOptions" filterable />
                      </n-form-item>
                      <n-form-item :label="t('legacy.parameters_json')">
                        <n-input v-model:value="debugMcpArguments" type="textarea" :autosize="{ minRows: 8, maxRows: 14 }" :placeholder="t('mcp_placeholder')" />
                      </n-form-item>
                    </template>
                  </div>

                  <div class="debug-right">
                    <div class="result-panel">
                      <div class="result-title">{{ t('legacy.request_body') }}</div>
                      <n-code :code="JSON.stringify(lastRequest, null, 2)" language="json" word-wrap />
                    </div>
                    <div class="result-panel">
                      <div class="result-title result-title-row">
                        <span>{{ t('legacy.response_body') }}</span>
                        <n-button v-if="canInferOutputSchema" size="tiny" secondary @click="inferOutputSchemaFromTest">
                          <template #icon><ToolIcon name="schema" /></template>
                          {{ t('legacy.generate_output') }}
                        </n-button>
                      </div>
                      <n-code :code="JSON.stringify(testResult || {}, null, 2)" language="json" word-wrap />
                    </div>
                  </div>
                </div>
              </section>
            </n-form>
          </template>
        </n-card>
      </div>

      <n-card :bordered="false" class="aside-card shell-card">
        <div class="debug-aside">
          <div class="debug-workspace">
            <div class="aside-title-row">
              <div>
                <div class="aside-title">{{ t('legacy.debug_test') }}</div>
                <div class="aside-desc">{{ testStatusText }}</div>
              </div>
              <n-tag :type="testStatusTagType" round>{{ testStatusLabel }}</n-tag>
            </div>

            <div class="debug-overview">
              <span>{{ form.type === 'mcp' ? 'MCP' : String(form.config.method || 'GET') }}</span>
              <strong>{{ debugEndpointText }}</strong>
            </div>

            <div class="aside-subtitle compact-title">{{ t('legacy.test_input') }}</div>
            <template v-if="form.type === 'http'">
              <div v-for="group in groupedDebugNodes" :key="group.location" class="debug-param-group">
                <div v-if="group.nodes.length" class="debug-group-title">{{ group.label }}</div>
                <div v-for="node in group.nodes" :key="node.id" class="debug-param-row compact">
                  <label>
                    {{ node.name || t('legacy.unnamed_parameter') }}
                    <span v-if="node.required">*</span>
                  </label>
                  <n-input v-model:value="debugValues[node.id]" size="small" :placeholder="node.description || node.type" />
                </div>
              </div>
              <n-empty v-if="flatInputNodes.length === 0" :description="t('legacy.no_parameters')" size="small" />
            </template>
            <template v-else>
              <n-form-item :label="t('legacy.mcp_tool')">
                <n-select v-model:value="debugMcpToolName" :options="mcpToolOptions" filterable size="small" />
              </n-form-item>
              <n-form-item :label="t('legacy.parameters_json')">
                <n-input v-model:value="debugMcpArguments" type="textarea" :autosize="{ minRows: 4, maxRows: 8 }" :placeholder="t('mcp_placeholder')" />
              </n-form-item>
            </template>

            <n-button block type="primary" :loading="testing" @click="runDebug">
              <template #icon><ToolIcon name="play" /></template>
              {{ t('legacy.run_test') }}
            </n-button>

            <div v-if="testResult" class="test-summary">
              <div class="test-metrics-row">
                <div>
                  <span>{{ t('legacy.status') }}</span>
                  <strong :class="testResult.success ? 'success-text' : 'error-text'">{{ testResult.message || '-' }}</strong>
                </div>
                <div>
                  <span>{{ t('legacy.duration') }}</span>
                  <strong>{{ testResult.durationMs ?? '-' }} ms</strong>
                </div>
              </div>
              <div class="response-summary">{{ String(testResult.responseSummary || testResult.message || '') }}</div>
              <n-button v-if="canInferOutputSchema" block secondary size="small" @click="inferOutputSchemaFromTest">
                <template #icon><ToolIcon name="schema" /></template>
                {{ t('legacy.generate_output_definition') }}
              </n-button>
            </div>

            <div v-if="testResult || Object.keys(lastRequest).length" class="debug-json-scroll">
              <n-collapse class="debug-collapse" accordion>
                <n-collapse-item name="request">
                  <template #header>
                    <div class="json-panel-header">
                      <span>{{ t('legacy.call_preview') }}</span>
                      <n-button quaternary circle size="tiny" :title="t('legacy.copy_preview')" @click.stop="copyJson(debugRequestPreview, t('legacy.call_preview_copied'))">
                        <ToolIcon name="copy" />
                      </n-button>
                    </div>
                  </template>
                  <pre class="json-pre-panel"><code class="json-code-panel">{{ JSON.stringify(debugRequestPreview, null, 2) }}</code></pre>
                </n-collapse-item>
                <n-collapse-item v-if="testResult" name="response">
                  <template #header>
                    <div class="json-panel-header">
                      <span>{{ t('legacy.response_body') }}</span>
                      <n-button quaternary circle size="tiny" :title="t('legacy.copy_response')" @click.stop="copyJson(testResult, t('legacy.response_body_copied'))">
                        <ToolIcon name="copy" />
                      </n-button>
                    </div>
                  </template>
                  <pre class="json-pre-panel"><code class="json-code-panel">{{ JSON.stringify(testResult, null, 2) }}</code></pre>
                </n-collapse-item>
              </n-collapse>
            </div>
          </div>
        </div>
      </n-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, defineComponent, h, onMounted, reactive, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { t } from '@/composables/i18n';
import type { FormInst, FormRules } from 'naive-ui';
import {
  NAlert,
  NButton,
  NCard,
  NCheckbox,
  NCode,
  NCollapse,
  NCollapseItem,
  NDynamicTags,
  NEmpty,
  NForm,
  NFormItem,
  NFormItemGi,
  NGrid,
  NInput,
  NInputNumber,
  NRadioButton,
  NRadioGroup,
  NSelect,
  NSkeleton,
  NSpace,
  NStep,
  NSteps,
  NSwitch,
  NTag,
  useMessage,
} from 'naive-ui';
import {
  createTool,
  discoverMcpTools,
  fetchTool,
  generateToolDescription,
  testTool,
  updateTool,
  type ExternalToolItem,
  type ToolPayload,
  type ToolType,
} from '@/api/tools';
import { mcpActivationError, nextMcpToolSelection, toolStatusConfirmText } from '@/utils/toolActivation';

type SchemaType = 'String' | 'Integer' | 'Number' | 'Boolean' | 'Object' | 'Array' | 'ArrayObject';
type ParamLocation = 'Header' | 'Query' | 'Body' | 'Path';
type ResponseMode = 'summarized' | 'original' | 'answer';

interface HeaderRow {
  id: string;
  name: string;
  value: string;
}

interface SchemaNode {
  id: string;
  name: string;
  description: string;
  type: SchemaType;
  location?: ParamLocation;
  required?: boolean;
  responseMode?: ResponseMode;
  children?: SchemaNode[];
}

interface FlatInputNode extends SchemaNode {
  depth: number;
}

type ToolIconName = 'add' | 'back' | 'check' | 'copy' | 'next' | 'play' | 'save' | 'schema' | 'search' | 'sparkles' | 'trash';

const toolIconPaths: Record<ToolIconName, string[]> = {
  add: ['M12 5v14', 'M5 12h14'],
  back: ['M15 18l-6-6 6-6'],
  check: ['M20 6L9 17l-5-5'],
  copy: ['M8 8h10a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2V10a2 2 0 0 1 2-2z', 'M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8h2'],
  next: ['M9 18l6-6-6-6'],
  play: ['M8 5v14l11-7-11-7z'],
  save: ['M5 4h12l2 2v14H5z', 'M8 4v6h8V4', 'M8 20v-6h8v6'],
  schema: ['M4 5h6v6H4z', 'M14 5h6v6h-6z', 'M4 15h6v6H4z', 'M14 15h6v6h-6z', 'M10 8h4', 'M10 18h4'],
  search: ['M11 19a8 8 0 1 1 0-16 8 8 0 0 1 0 16z', 'M21 21l-4.35-4.35'],
  sparkles: ['M13 2l1.7 5.3L20 9l-5.3 1.7L13 16l-1.7-5.3L6 9l5.3-1.7L13 2z', 'M5 14l.9 2.1L8 17l-2.1.9L5 20l-.9-2.1L2 17l2.1-.9L5 14z'],
  trash: ['M3 6h18', 'M8 6V4h8v2', 'M6 6l1 15h10l1-15', 'M10 11v6', 'M14 11v6'],
};

const ToolIcon = defineComponent({
  name: 'ToolIcon',
  props: {
    name: { type: String as () => ToolIconName, required: true },
  },
  setup(props) {
    return () => h(
      'svg',
      {
        class: 'tool-icon',
        viewBox: '0 0 24 24',
        fill: 'none',
        stroke: 'currentColor',
        'stroke-width': 2,
        'stroke-linecap': 'round',
        'stroke-linejoin': 'round',
        'aria-hidden': 'true',
      },
      toolIconPaths[props.name].map((path) => h('path', { d: path })),
    );
  },
});

const SchemaEditor = defineComponent({
  name: 'SchemaEditor',
  props: {
    nodes: { type: Array as () => SchemaNode[], required: true },
    mode: { type: String as () => 'input' | 'output', required: true },
  },
  emits: ['add-child', 'remove'],
  setup(props, { emit }) {
    const typeOptions = [
      'String',
      'Integer',
      'Number',
      'Boolean',
      'Object',
      'Array',
      'ArrayObject',
    ].map((value) => ({ label: value, value }));
    const locationOptions = ['Header', 'Query', 'Body', 'Path'].map((value) => ({ label: value, value }));
    const responseModeOptions = computed(() => [
      { label: t('legacy.llm_summary'), value: 'summarized' },
      { label: t('legacy.original_response'), value: 'original' },
      { label: t('legacy.main_answer'), value: 'answer' },
    ]);

    function flatten(nodes: SchemaNode[], depth = 0): Array<{ node: SchemaNode; depth: number }> {
      return nodes.flatMap((node) => [
        { node, depth },
        ...flatten(node.children || [], depth + 1),
      ]);
    }

    return () => {
      const flat = flatten(props.nodes);
      if (!flat.length) {
        return h(NEmpty, { description: props.mode === 'input' ? t('legacy.no_input_parameters_defined_yet') : t('legacy.no_output_parameters_defined_yet') });
      }
      return h('div', { class: 'schema-editor' }, [
        h('div', { class: ['schema-grid', 'schema-head', props.mode === 'input' ? 'input-grid' : 'output-grid'] }, props.mode === 'input'
          ? [t('legacy.parameter_name'), t('legacy.description_463de98'), t('legacy.type'), t('legacy.location'), t('legacy.required'), t('legacy.actions')].map((text) => h('span', text))
          : [t('legacy.field_name'), t('legacy.description_805453d'), t('legacy.type'), t('legacy.usage_mode'), t('legacy.actions')].map((text) => h('span', text))),
        flat.map(({ node, depth }) => h('div', { key: node.id, class: ['schema-grid', props.mode === 'input' ? 'input-grid' : 'output-grid'] }, [
          h(NInput, {
            value: node.name,
            placeholder: depth > 0 && node.type === 'Array' ? '[Array Item]' : t('legacy.please_enter'),
            style: { marginLeft: `${depth * 24}px`, width: `calc(100% - ${depth * 24}px)` },
            'onUpdate:value': (value: string) => { node.name = value.replace(/[^a-zA-Z0-9_]/g, ''); },
          }),
          h(NInput, {
            value: node.description,
            placeholder: props.mode === 'input' ? t('legacy.help_agent_understand_how_to_extract_parameter') : t('legacy.help_agent_understand_return_field'),
            'onUpdate:value': (value: string) => { node.description = value; },
          }),
          h(NSelect, {
            value: node.type,
            options: typeOptions,
            'onUpdate:value': (value: SchemaType) => {
              node.type = value;
              if (value === 'Array' && node.children?.length) {
                node.children.forEach((child) => { child.name = '[Array Item]'; });
              }
            },
          }),
          props.mode === 'input'
            ? h(NSelect, {
              value: node.location || 'Query',
              options: locationOptions,
              'onUpdate:value': (value: ParamLocation) => { node.location = value; },
            })
            : h(NSelect, {
              value: node.responseMode || 'summarized',
              options: responseModeOptions.value,
              'onUpdate:value': (value: ResponseMode) => { node.responseMode = value; },
            }),
          props.mode === 'input'
            ? h(NSwitch, {
              value: Boolean(node.required),
              'onUpdate:value': (value: boolean) => { node.required = value; },
            })
            : null,
          h('div', { class: 'schema-actions' }, [
            h(NButton, {
              size: 'small',
              quaternary: true,
              disabled: !['Object', 'Array', 'ArrayObject'].includes(node.type),
              onClick: () => emit('add-child', node.id),
            }, { icon: () => h(ToolIcon, { name: 'add' }), default: () => t('legacy.child') }),
            h(NButton, { size: 'small', quaternary: true, type: 'error', onClick: () => emit('remove', node.id) }, { icon: () => h(ToolIcon, { name: 'trash' }), default: () => t('legacy.delete') }),
          ]),
        ])),
      ]);
    };
  },
});

const router = useRouter();
const route = useRoute();
const message = useMessage();
const formRef = ref<FormInst | null>(null);

const loading = ref(false);
const saving = ref(false);
const discovering = ref(false);
const testing = ref(false);
const generatingDescription = ref(false);
const activeStep = ref(1);
const toolId = ref('');

const headerRows = ref<HeaderRow[]>([]);
const inputSchema = ref<SchemaNode[]>([]);
const outputSchema = ref<SchemaNode[]>([]);
const discoveredTools = ref<ExternalToolItem['discoveredTools']>([]);
const enabledToolNames = ref<string[]>([]);
const debugValues = reactive<Record<string, string>>({});
const debugMcpToolName = ref('');
const debugMcpArguments = ref('{}');
const lastRequest = ref<Record<string, unknown>>({});
const testResult = ref<Record<string, any> | null>(null);
const lastTestConfigSignature = ref('');

const form = reactive<ToolPayload>({
  name: '',
  type: 'http',
  description: '',
  usageHint: '',
  tags: [],
  status: 'disabled',
  config: {},
});

const rules: FormRules = {
  name: { required: true, message: t('legacy.please_enter_tool_name'), trigger: 'blur' },
  type: { required: true, message: t('legacy.please_select_tool_type'), trigger: 'change' },
  description: { required: true, message: t('legacy.please_enter_tool_description'), trigger: 'blur' },
  'config.url': {
    validator: (_rule, value) => {
      if (form.type !== 'http') return true;
      return String(value || '').trim() ? true : new Error(t('legacy.please_enter_request_url'));
    },
    trigger: ['blur', 'change'],
  },
  'config.endpoint': {
    validator: (_rule, value) => {
      if (form.type !== 'mcp') return true;
      return String(value || '').trim() ? true : new Error(t('legacy.please_enter_mcp_endpoint'));
    },
    trigger: ['blur', 'change'],
  },
  'config.apiKeyHeader': {
    validator: () => {
      if (form.config.authType !== 'api_key') return true;
      return String(form.config.apiKeyHeader || '').trim() ? true : new Error(t('legacy.please_enter_the_header_name'));
    },
    trigger: ['blur', 'change'],
  },
  'config.authToken': {
    validator: () => {
      if (form.config.authType === 'none') return true;
      return String(form.config.authToken || '').trim() ? true : new Error(t('legacy.please_enter_the_token_key'));
    },
    trigger: ['blur', 'change'],
  },
};

const methodOptions = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'].map((value) => ({ label: value, value }));
const authOptions = computed(() => [
  { label: t('legacy.none'), value: 'none' },
  { label: t('legacy.bearer_token'), value: 'bearer' },
  { label: t('legacy.api_key_header'), value: 'api_key' },
]);

const isCreate = computed(() => !route.params.id);
const enabledSwitch = computed({
  get: () => form.status === 'active',
  set: (value: boolean) => {
    if ((form.status === 'active') === value) return;
    const nextStatus = value ? 'active' : 'disabled';
    const error = mcpActivationError({ ...form, status: nextStatus });
    if (error) {
      message.warning(error);
      return;
    }
    if (!window.confirm(toolStatusConfirmText({ ...form, discoveredTools: discoveredTools.value }, value))) return;
    form.status = nextStatus;
  },
});
const steps = computed(() => {
  if (form.type === 'mcp') {
    return [
      { key: 'base', title: t('legacy.basic_info'), description: t('legacy.name_description') },
      { key: 'request', title: t('legacy.connection_config'), description: t('legacy.url_auth_headers') },
      { key: 'mcpTools', title: t('legacy.discover_tools'), description: t('legacy.fetch_remote_mcp_tool_schema') },
    ];
  }
  return [
    { key: 'base', title: t('legacy.basic_info'), description: t('legacy.name_description') },
    { key: 'request', title: t('legacy.request_config'), description: t('legacy.url_method_auth_headers') },
    { key: 'input', title: t('legacy.input_definition'), description: t('legacy.parameters_agent_needs_to_pass') },
    { key: 'output', title: t('legacy.output_definition'), description: t('legacy.meaning_usage_of_response_fields') },
  ];
});
const activeKey = computed(() => steps.value[activeStep.value - 1]?.key || 'base');
const currentStep = computed(() => steps.value[activeStep.value - 1]);
const flatInputNodes = computed<FlatInputNode[]>(() => flattenSchema(inputSchema.value));
const mcpToolOptions = computed(() => discoveredTools.value.map((tool) => ({ label: tool.name, value: tool.name })));
const groupedDebugNodes = computed(() => {
  const groups = [
    { location: 'Path', label: 'Path', nodes: [] as FlatInputNode[] },
    { location: 'Query', label: 'Query', nodes: [] as FlatInputNode[] },
    { location: 'Header', label: 'Header', nodes: [] as FlatInputNode[] },
    { location: 'Body', label: 'Body', nodes: [] as FlatInputNode[] },
  ];
  for (const node of flatInputNodes.value) {
    const group = groups.find((item) => item.location === (node.location || 'Query'));
    group?.nodes.push(node);
  }
  return groups;
});
const debugEndpointText = computed(() => {
  const value = form.type === 'mcp' ? form.config.endpoint : form.config.url;
  return String(value || t('legacy.no_endpoint_configured'));
});
const debugRequestPreview = computed(() => {
  if (!Object.keys(lastRequest.value).length) return {};
  if (form.type === 'mcp') {
    return {
      toolId: toolId.value || null,
      toolName: debugMcpToolName.value,
      request: {
        arguments: lastRequest.value.arguments || {},
      },
    };
  }
  return buildHttpExecutionPreview(lastRequest.value);
});
const currentConfigSignature = computed(() => JSON.stringify(buildPayload()));
const canInferOutputSchema = computed(() => form.type === 'http' && Boolean(extractTestResponseBody()));
const testConfigDirty = computed(() => Boolean(testResult.value) && lastTestConfigSignature.value !== currentConfigSignature.value);
const testStatusLabel = computed(() => {
  if (testConfigDirty.value) return t('legacy.retest_needed');
  if (!testResult.value) return t('legacy.untested');
  return testResult.value.success ? t('legacy.passed_4b3c965') : t('legacy.failed');
});
const testStatusText = computed(() => {
  if (testConfigDirty.value) return t('legacy.config_changed');
  if (!testResult.value) return t('legacy.ready_to_test_current_draft');
  return String(testResult.value.message || '');
});
const testStatusTagType = computed(() => {
  if (testConfigDirty.value) return 'warning';
  if (!testResult.value) return 'default';
  return testResult.value.success ? 'success' : 'error';
});

function uid() {
  return Math.random().toString(36).slice(2, 10);
}

async function copyJson(value: unknown, successText: string) {
  const text = JSON.stringify(value || {}, null, 2);
  try {
    await navigator.clipboard.writeText(text);
    message.success(successText);
  } catch {
    message.error(t('legacy.copy_failed'));
  }
}

function defaultConfig(type: ToolType) {
  return type === 'mcp'
    ? { endpoint: '', authType: 'none', headers: {}, timeoutSeconds: 20, enabledToolNames: [] }
    : {
      url: '',
      method: 'GET',
      authType: 'none',
      headers: {},
      timeoutSeconds: 15,
      resultPath: '',
      inputSchema: [],
      outputSchema: [],
    };
}

function resetForType(type: ToolType) {
  form.type = type;
  form.status = 'disabled';
  form.config = defaultConfig(type);
  headerRows.value = [];
  inputSchema.value = [];
  outputSchema.value = [];
  discoveredTools.value = [];
  enabledToolNames.value = [];
  activeStep.value = 1;
}

function changeType(value: string) {
  resetForType(value === 'mcp' ? 'mcp' : 'http');
}

function backToList() {
  router.push('/tools');
}

function headersToObject() {
  const headers: Record<string, string> = {};
  for (const item of headerRows.value) {
    const name = item.name.trim();
    if (name) headers[name] = item.value;
  }
  return headers;
}

function objectToHeaders(headers: Record<string, unknown> = {}) {
  headerRows.value = Object.entries(headers).map(([name, value]) => ({ id: uid(), name, value: String(value ?? '') }));
}

function normalizeNodes(nodes: any[]): SchemaNode[] {
  return (Array.isArray(nodes) ? nodes : []).map((node) => ({
    id: String(node.id || uid()),
    name: String(node.name || ''),
    description: String(node.description || node.desc || ''),
    type: normalizeType(node.type),
    location: normalizeLocation(node.location),
    required: Boolean(node.required ?? node.require),
    responseMode: normalizeResponseMode(node.responseMode),
    children: normalizeNodes(node.children || []),
  }));
}

function normalizeType(value: unknown): SchemaType {
  return ['String', 'Integer', 'Number', 'Boolean', 'Object', 'Array', 'ArrayObject'].includes(String(value))
    ? String(value) as SchemaType
    : 'String';
}

function normalizeLocation(value: unknown): ParamLocation {
  return ['Header', 'Query', 'Body', 'Path'].includes(String(value)) ? String(value) as ParamLocation : 'Query';
}

function normalizeResponseMode(value: unknown): ResponseMode {
  return ['summarized', 'original', 'answer'].includes(String(value)) ? String(value) as ResponseMode : 'summarized';
}

function inferSchemaType(value: unknown): SchemaType {
  if (Array.isArray(value)) return 'Array';
  if (value === null || value === undefined) return 'String';
  if (typeof value === 'boolean') return 'Boolean';
  if (typeof value === 'number') return Number.isInteger(value) ? 'Integer' : 'Number';
  if (typeof value === 'object') return 'Object';
  return 'String';
}

function readableType(type: SchemaType) {
  const labels: Record<SchemaType, string> = {
    String: t('legacy.text_f1573e7'),
    Integer: t('legacy.integer_2a59217'),
    Number: t('legacy.number_5c785eb'),
    Boolean: t('legacy.boolean_0defa35'),
    Object: t('legacy.object_7db0748'),
    Array: t('legacy.array_d166572'),
    ArrayObject: t('legacy.array_of_objects'),
  };
  return labels[type] || type;
}

function splitFieldTokens(value: string) {
  return String(value || '')
    .replace(/([a-z0-9])([A-Z])/g, '$1_$2')
    .split(/[^a-zA-Z0-9]+/)
    .map((part) => part.toLowerCase())
    .filter(Boolean);
}

function commonFieldMeaning(name: string, path: string) {
  const tokens = splitFieldTokens(`${path}_${name}`);
  const tokenSet = new Set(tokens);
  const joined = tokens.join('_');
  if (tokenSet.has('id') || joined.endsWith('_id')) return t('legacy.usually_identifies_a_record_or_entity');
  if (tokenSet.has('name')) return t('legacy.usually_represents_a_name');
  if (tokenSet.has('title')) return t('legacy.usually_represents_a_title');
  if (tokenSet.has('status') || tokenSet.has('state')) return t('legacy.usually_represents_a_status');
  if (tokenSet.has('type') || tokenSet.has('category')) return t('legacy.usually_represents_a_type_or_category');
  if (tokenSet.has('count') || tokenSet.has('total') || tokenSet.has('num') || tokenSet.has('quantity')) return t('legacy.usually_represents_a_count_or_metric');
  if (tokenSet.has('amount') || tokenSet.has('price') || tokenSet.has('cost') || tokenSet.has('fee')) return t('legacy.usually_represents_an_amount_or_price');
  if (tokenSet.has('date') || tokenSet.has('time') || tokenSet.has('created') || tokenSet.has('updated')) return t('legacy.usually_represents_a_date_or_time');
  if (tokenSet.has('url') || tokenSet.has('link') || tokenSet.has('uri')) return t('legacy.usually_represents_a_link_or_address');
  if (tokenSet.has('desc') || tokenSet.has('description') || tokenSet.has('summary')) return t('legacy.usually_represents_a_description_or_summary');
  if (tokenSet.has('content') || tokenSet.has('text')) return t('legacy.usually_represents_body_content');
  if (tokenSet.has('message') || tokenSet.has('msg')) return t('legacy.usually_represents_message_text');
  if (tokenSet.has('code')) return t('legacy.usually_represents_a_code_or_return_code');
  if (tokenSet.has('score') || tokenSet.has('rate') || tokenSet.has('ratio')) return t('legacy.usually_represents_a_score_ratio_or_rating');
  return '';
}

function childFieldSummary(value: unknown) {
  let record: Record<string, unknown> | null = null;
  if (Array.isArray(value)) {
    const sample = sampleArrayItem(value);
    if (sample && typeof sample === 'object' && !Array.isArray(sample)) {
      record = sample as Record<string, unknown>;
    }
  } else if (value && typeof value === 'object') {
    record = value as Record<string, unknown>;
  }
  if (!record) return '';
  const keys = Object.keys(record).filter(Boolean).slice(0, 6);
  if (!keys.length) return '';
  return `，包含 ${keys.join('、')}${Object.keys(record).length > keys.length ? ' 等' : ''} 子字段`;
}

function schemaDescriptionForValue(name: string, value: unknown, path = name) {
  const type = inferSchemaType(value);
  const fieldPath = path || name;
  const meaning = commonFieldMeaning(name, fieldPath);
  if (Array.isArray(value)) {
    return `数组字段 \`${fieldPath}\`${childFieldSummary(value)}，用于描述列表型响应数据`;
  }
  if (value && typeof value === 'object') {
    return `对象字段 \`${fieldPath}\`${childFieldSummary(value)}，用于承载结构化响应数据`;
  }
  return `响应字段 \`${fieldPath}\`，类型为${readableType(type)}${meaning ? `，${meaning}` : ''}`;
}

function isAutoGeneratedDescription(value: unknown) {
  const text = String(value || '').trim();
  if (!text) return true;
  return (
    text === '测试响应字段'
    || text === '测试响应中的对象字段'
    || text === '测试响应中的数组字段'
    || text === '测试响应中的数组字段，子项结构来自样例数据'
    || text.startsWith('响应字段 `')
    || text.startsWith('对象字段 `')
    || text.startsWith('数组字段 `')
    || text.startsWith('Response field `')
    || text.startsWith('Object field `')
    || text.startsWith('Array field `')
    || text === '主要结果路径中的对象字段'
    || text === 'Object field in the primary result path'
  );
}

function sampleArrayItem(values: unknown[]): unknown {
  const objectItems = values.filter((item) => item && typeof item === 'object' && !Array.isArray(item));
  if (!objectItems.length) return values.find((item) => item !== null && item !== undefined);
  return objectItems.slice(0, 10).reduce<Record<string, unknown>>((merged, item) => {
    Object.assign(merged, item as Record<string, unknown>);
    return merged;
  }, {});
}

function inferNodesFromRecord(record: Record<string, unknown>, prefix = ''): SchemaNode[] {
  return Object.entries(record)
    .filter(([name]) => String(name || '').trim())
    .map(([name, value]) => inferNodeFromValue(name, value, prefix ? `${prefix}.${name}` : name));
}

function inferNodeFromValue(name: string, value: unknown, path = name): SchemaNode {
  const type = inferSchemaType(value);
  const node = newSchemaNode({
    name,
    type,
    location: undefined,
    required: false,
    responseMode: type === 'Object' || type === 'Array' ? 'summarized' : 'original',
    description: schemaDescriptionForValue(name, value, path),
    children: [],
  });
  if (type === 'Object' && value && typeof value === 'object' && !Array.isArray(value)) {
    node.children = inferNodesFromRecord(value as Record<string, unknown>, path);
  } else if (type === 'Array' && Array.isArray(value)) {
    const sample = sampleArrayItem(value);
    if (sample && typeof sample === 'object' && !Array.isArray(sample)) {
      node.children = inferNodesFromRecord(sample as Record<string, unknown>, `${path}[]`);
    }
  }
  return node;
}

function parseResultPath(path: string): string[] {
  return String(path || '')
    .replace(/\[(\d+)\]/g, '.$1')
    .split('.')
    .map((part) => part.trim())
    .filter(Boolean);
}

function resolvePath(value: unknown, path: string): unknown {
  let current = value;
  for (const part of parseResultPath(path)) {
    if (Array.isArray(current)) {
      const index = Number(part);
      if (!Number.isInteger(index) || index < 0 || index >= current.length) return undefined;
      current = current[index];
    } else if (current && typeof current === 'object') {
      const record = current as Record<string, unknown>;
      if (!(part in record)) return undefined;
      current = record[part];
    } else {
      return undefined;
    }
  }
  return current;
}

function wrapNodesWithResultPath(nodes: SchemaNode[], value: unknown, path: string): SchemaNode[] {
  const parts = parseResultPath(path).filter((part) => !/^\d+$/.test(part));
  if (!parts.length) return nodes;
  let childNodes = nodes;
  let childValue = value;
  for (let index = parts.length - 1; index >= 0; index -= 1) {
    const isLeaf = index === parts.length - 1;
    const nodeValue = isLeaf ? childValue : {};
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
    ];
  }
  return childNodes;
}

function extractTestResponseBody(): unknown {
  if (!testResult.value) return undefined;
  if ('raw' in testResult.value) return testResult.value.raw;
  return undefined;
}

function schemaFromTestResponse(): SchemaNode[] {
  const raw = extractTestResponseBody();
  if (raw === undefined || raw === null) return [];
  const resultPath = String(form.config.resultPath || '').trim();
  const selected = resultPath ? resolvePath(raw, resultPath) : raw;
  if (selected === undefined || selected === null) return [];
  let nodes: SchemaNode[];
  if (Array.isArray(selected)) {
    const sample = sampleArrayItem(selected);
    if (sample && typeof sample === 'object' && !Array.isArray(sample)) {
      nodes = inferNodesFromRecord(sample as Record<string, unknown>, resultPath ? `${resultPath}[]` : '');
    } else {
      nodes = [inferNodeFromValue('items', selected, resultPath || 'items')];
    }
  } else if (selected && typeof selected === 'object') {
    nodes = inferNodesFromRecord(selected as Record<string, unknown>, resultPath);
  } else {
    nodes = [inferNodeFromValue('value', selected, resultPath || 'value')];
  }
  return resultPath ? wrapNodesWithResultPath(nodes, selected, resultPath) : nodes;
}

function countSchemaNodes(nodes: SchemaNode[]): number {
  return nodes.reduce(
    (total, node) => total + 1 + countSchemaNodes(node.children || []),
    0,
  );
}

function mergeSchemaNodes(target: SchemaNode[], incoming: SchemaNode[]): number {
  let added = 0;
  for (const node of incoming) {
    const existing = target.find((item) => item.name === node.name);
    if (!existing) {
      target.push(node);
      added += countSchemaNodes([node]);
      continue;
    }
    if (!existing.type || existing.type === 'String') existing.type = node.type;
    if (isAutoGeneratedDescription(existing.description)) existing.description = node.description;
    if (!existing.responseMode) existing.responseMode = node.responseMode;
    existing.children ||= [];
    added += mergeSchemaNodes(existing.children, node.children || []);
  }
  return added;
}

function inferOutputSchemaFromTest() {
  const inferred = schemaFromTestResponse();
  if (!inferred.length) {
    message.warning(t('legacy.current_test_response_cannot_generate_output_definition'));
    return;
  }
  const added = mergeSchemaNodes(outputSchema.value, inferred);
  if (added > 0) {
    message.success(t('legacy.added_output_fields', { count: added }));
  } else {
    message.info(t('legacy.output_definition_already_contains_response_fields'));
  }
}

function flattenSchema(nodes: SchemaNode[], depth = 0): FlatInputNode[] {
  return nodes.flatMap((node) => [
    { ...node, depth },
    ...flattenSchema(node.children || [], depth + 1),
  ]);
}

function findNode(nodes: SchemaNode[], id: string): SchemaNode | null {
  for (const node of nodes) {
    if (node.id === id) return node;
    const child = findNode(node.children || [], id);
    if (child) return child;
  }
  return null;
}

function removeNode(nodes: SchemaNode[], id: string): boolean {
  const index = nodes.findIndex((node) => node.id === id);
  if (index >= 0) {
    nodes.splice(index, 1);
    return true;
  }
  return nodes.some((node) => removeNode(node.children || [], id));
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
  };
}

function addInputNode(parentId?: string) {
  if (!parentId) {
    inputSchema.value.push(newSchemaNode());
    return;
  }
  const parent = findNode(inputSchema.value, parentId);
  if (parent) {
    parent.children ||= [];
    parent.children.push(newSchemaNode({ name: parent.type === 'Array' ? '[Array Item]' : '', location: parent.location || 'Body' }));
  }
}

function removeInputNode(id: string) {
  removeNode(inputSchema.value, id);
}

function addOutputNode(parentId?: string) {
  if (!parentId) {
    outputSchema.value.push(newSchemaNode({ location: undefined, required: false }));
    return;
  }
  const parent = findNode(outputSchema.value, parentId);
  if (parent) {
    parent.children ||= [];
    parent.children.push(newSchemaNode({ name: parent.type === 'Array' ? '[Array Item]' : '', location: undefined, required: false, responseMode: parent.responseMode || 'summarized' }));
  }
}

function removeOutputNode(id: string) {
  removeNode(outputSchema.value, id);
}

function addHeader() {
  headerRows.value.push({ id: uid(), name: '', value: '' });
}

function removeHeader(id: string) {
  headerRows.value = headerRows.value.filter((item) => item.id !== id);
}

function buildPayload(): ToolPayload {
  const normalizedDescription = form.description.trim();
  const normalizedUsageHint = form.usageHint.trim() || normalizedDescription;
  const config: Record<string, any> = {
    ...form.config,
    headers: headersToObject(),
  };
  if (form.type === 'http') {
    config.inputSchema = inputSchema.value;
    config.outputSchema = outputSchema.value;
  } else {
    config.enabledToolNames = enabledToolNames.value;
  }
  return {
    name: form.name,
    type: form.type,
    description: normalizedDescription,
    usageHint: normalizedUsageHint,
    tags: form.tags,
    status: form.status,
    config,
  };
}

async function saveTool() {
  if (!validateRequiredStepsForSave()) return;
  await formRef.value?.validate();
  const activationError = mcpActivationError(buildPayload());
  if (activationError) {
    message.warning(activationError);
    activeStep.value = stepNumber('mcpTools');
    return;
  }
  saving.value = true;
  try {
    const payload = buildPayload();
    if (toolId.value) {
      await updateTool(toolId.value, payload);
      message.success(t('legacy.tool_config_saved'));
    } else {
      const created = await createTool(payload);
      toolId.value = created.id;
      message.success(t('legacy.tool_config_created'));
      router.replace(`/tools/${created.id}/edit`);
    }
  } catch (error: any) {
    message.error(error?.response?.data?.detail || error?.message || t('legacy.failed_to_save'));
  } finally {
    saving.value = false;
  }
}

async function saveDraft() {
  const activationError = mcpActivationError(buildPayload());
  if (activationError) {
    message.warning(activationError);
    activeStep.value = stepNumber('mcpTools');
    return;
  }
  saving.value = true;
  try {
    const payload = buildPayload();
    if (toolId.value) {
      await updateTool(toolId.value, payload);
      message.success(t('legacy.draft_saved'));
    } else {
      const created = await createTool(payload);
      toolId.value = created.id;
      message.success(t('legacy.draft_created'));
      router.replace(`/tools/${created.id}/edit`);
    }
  } catch (error: any) {
    message.error(error?.response?.data?.detail || error?.message || t('legacy.failed_to_save_draft'));
  } finally {
    saving.value = false;
  }
}

async function generateDescriptionFromName() {
  const toolName = form.name.trim();
  if (!toolName) {
    message.warning(t('legacy.please_enter_tool_name_first'));
    return;
  }
  generatingDescription.value = true;
  try {
    const result = await generateToolDescription({
      name: toolName,
      type: form.type,
      existingDescription: form.description,
    });
    const generated = String(result?.description || '').trim();
    if (!generated) {
      message.warning(t('legacy.failed_to_generate_description_please_try_again'));
      return;
    }
    form.description = generated;
    message.success(t('legacy.tool_description_generated'));
  } catch (error: any) {
    message.error(error?.response?.data?.detail || t('legacy.failed_to_generate'));
  } finally {
    generatingDescription.value = false;
  }
}

function validateBaseStep() {
  if (!form.name.trim()) {
    message.warning(t('legacy.please_enter_tool_name_first'));
    return false;
  }
  if (!form.description.trim()) {
    message.warning(t('legacy.please_enter_tool_description_first'));
    return false;
  }
  return true;
}

function validateRequestStep() {
  if (form.type === 'http' && !String(form.config.url || '').trim()) {
    message.warning(t('legacy.please_enter_request_url_first'));
    return false;
  }
  if (form.type === 'mcp' && !String(form.config.endpoint || '').trim()) {
    message.warning(t('legacy.please_enter_mcp_endpoint_first'));
    return false;
  }
  if (form.config.authType === 'api_key' && !String(form.config.apiKeyHeader || '').trim()) {
    message.warning(t('legacy.please_enter_the_header_name_first'));
    return false;
  }
  if (form.config.authType !== 'none' && !String(form.config.authToken || '').trim()) {
    message.warning(t('legacy.please_enter_the_token_key_first'));
    return false;
  }
  return true;
}

function stepNumber(key: string) {
  const index = steps.value.findIndex((step) => step.key === key);
  return index >= 0 ? index + 1 : 1;
}

function validateStepByKey(key: string) {
  if (key === 'base') return validateBaseStep();
  if (key === 'request') return validateRequestStep();
  return true;
}

function validateRequiredStepsForSave() {
  if (!validateBaseStep()) {
    activeStep.value = stepNumber('base');
    return false;
  }
  if (!validateRequestStep()) {
    activeStep.value = stepNumber('request');
    return false;
  }
  return true;
}

function goPrevStep() {
  if (activeStep.value > 1) activeStep.value -= 1;
}

function handleStepChange(step: number) {
  if (step < 1 || step > steps.value.length) return;
  if (step > activeStep.value) {
    for (let index = activeStep.value - 1; index < step - 1; index += 1) {
      const key = steps.value[index]?.key;
      if (key && !validateStepByKey(key)) {
        activeStep.value = index + 1;
        return;
      }
    }
  }
  activeStep.value = step;
}

async function goNextStep() {
  if (activeStep.value >= steps.value.length) return;
  const currentKey = activeKey.value;
  if (currentKey === 'base' && !validateBaseStep()) return;
  if (currentKey === 'request' && !validateRequestStep()) return;
  activeStep.value += 1;
}

async function discoverTools() {
  if (!toolId.value) return;
  discovering.value = true;
  try {
    const result = await discoverMcpTools(toolId.value);
    discoveredTools.value = result.tools || [];
    const discoveredNames = new Set(discoveredTools.value.map((tool) => String(tool.name || '').trim()).filter(Boolean));
    enabledToolNames.value = enabledToolNames.value.filter((name) => discoveredNames.has(name));
    form.config.enabledToolNames = enabledToolNames.value;
    if (mcpActivationError(buildPayload())) {
      form.status = 'disabled';
    }
    message.success(result.message || t('legacy.mcp_tool_discovery_completed'));
  } catch (error: any) {
    message.error(error?.response?.data?.detail || t('legacy.mcp_tool_discovery_failed'));
  } finally {
    discovering.value = false;
  }
}

function toggleMcpTool(name: string, checked: boolean) {
  const next = nextMcpToolSelection(enabledToolNames.value, name, checked);
  if (next.error) {
    message.warning(next.error);
    return;
  }
  enabledToolNames.value = next.names;
  form.config.enabledToolNames = enabledToolNames.value;
}

function parseDebugValue(value: string, type: SchemaType) {
  if (type === 'Number' || type === 'Integer') return Number(value);
  if (type === 'Boolean') return value === 'true';
  if (type === 'Object' || type === 'Array' || type === 'ArrayObject') {
    try {
      return JSON.parse(value || (type === 'Object' ? '{}' : '[]'));
    } catch {
      return value;
    }
  }
  return value;
}

function buildHttpTestInput() {
  const query: Record<string, unknown> = {};
  const body: Record<string, unknown> = {};
  const headers: Record<string, unknown> = {};
  const path: Record<string, unknown> = {};
  for (const node of flatInputNodes.value) {
    if (!node.name) continue;
    const value = parseDebugValue(debugValues[node.id] || '', node.type);
    if (node.location === 'Body') body[node.name] = value;
    else if (node.location === 'Header') headers[node.name] = value;
    else if (node.location === 'Path') path[node.name] = value;
    else query[node.name] = value;
  }
  return { query, body, headers, path };
}

async function runDebug() {
  if (!toolId.value) {
    message.warning(t('legacy.please_save_the_tool_first_before_running_test'));
    return;
  }
  testing.value = true;
  const startedAt = performance.now();
  try {
    const input = form.type === 'mcp'
      ? {
        toolName: debugMcpToolName.value,
        arguments: JSON.parse(debugMcpArguments.value || '{}'),
      }
      : buildHttpTestInput();
    lastRequest.value = input;
    const payload = buildPayload();
    await updateTool(toolId.value, payload);
    testResult.value = await testTool(toolId.value, input, Number(payload.config.timeoutSeconds || 15));
    lastTestConfigSignature.value = JSON.stringify(payload);
  } catch (error: any) {
    const configuredTimeout = Number(form.config.timeoutSeconds || 15);
    const rawMessage = String(error?.response?.data?.detail || error?.message || '').trim();
    const isTimeout = error?.code === 'ECONNABORTED' || /timeout|timed out|超时/i.test(rawMessage);
    const errorMessage = isTimeout
      ? t('legacy.request_timed_out_no_response_after_seconds', { seconds: configuredTimeout })
      : (rawMessage || t('legacy.test_failed'));
    testResult.value = {
      success: false,
      status: 'failed',
      errorCode: isTimeout ? 'timeout' : 'request_failed',
      message: errorMessage,
      responseSummary: errorMessage,
      durationMs: Math.round(performance.now() - startedAt),
    };
    message.error(errorMessage);
  } finally {
    testing.value = false;
  }
}

function getUrlPath(value: unknown) {
  const text = String(value || '').trim();
  if (!text) return '';
  try {
    const parsed = new URL(text);
    return `${parsed.pathname.replace(/^\/+/, '')}${parsed.search || ''}`;
  } catch {
    return text.replace(/^\/+/, '');
  }
}

function buildHttpExecutionPreview(input: Record<string, unknown>) {
  const params = flatInputNodes.value
    .filter((node) => node.name)
    .map((node) => {
      const location = node.location || 'Query';
      const bucket = location === 'Body'
        ? input.body
        : location === 'Header'
          ? input.headers
          : location === 'Path'
            ? input.path
            : input.query;
      const values = bucket && typeof bucket === 'object' ? bucket as Record<string, unknown> : {};
      return {
        _id: node.id,
        children: node.children || [],
        name: node.name,
        desc: node.description || '',
        type: node.type || 'String',
        location,
        require: Boolean(node.required),
        value: values[node.name],
      };
    });
  return {
    toolId: toolId.value || null,
    toolName: form.name || '',
    path: getUrlPath(form.config.url),
    method: String(form.config.method || 'GET').toUpperCase(),
    request: {
      params,
    },
  };
}

function applyLoadedTool(tool: ExternalToolItem) {
  toolId.value = tool.id;
  form.name = tool.name;
  form.type = tool.type;
  form.description = tool.description;
  form.usageHint = tool.usageHint;
  form.tags = [...tool.tags];
  form.status = tool.status;
  form.config = { ...defaultConfig(tool.type), ...tool.config };
  objectToHeaders(form.config.headers || {});
  inputSchema.value = normalizeNodes(form.config.inputSchema || []);
  outputSchema.value = normalizeNodes(form.config.outputSchema || []);
  discoveredTools.value = tool.discoveredTools || [];
  enabledToolNames.value = Array.isArray(form.config.enabledToolNames)
    ? [...form.config.enabledToolNames]
    : [];
}

async function loadTool() {
  const id = String(route.params.id || '');
  if (!id) {
    const type = route.query.type === 'mcp' ? 'mcp' : 'http';
    resetForType(type);
    return;
  }
  loading.value = true;
  try {
    const tool = await fetchTool(id);
    applyLoadedTool(tool);
  } catch (error: any) {
    message.error(error?.response?.data?.detail || t('legacy.failed_to_load_tool_configuration'));
  } finally {
    loading.value = false;
  }
}

onMounted(loadTool);

watch(
  () => [route.params.id, route.query.type],
  () => {
    loadTool();
  },
);
</script>

<style scoped>
.tool-edit-page {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: calc(100vh - 88px);
  padding: 12px 12px;
  box-sizing: border-box;
  overflow: hidden;
}

.shell-card {
  border-radius: 14px;
  border: 1px solid #e6ebf5;
  background: #fff;
  box-shadow: 0 6px 20px rgba(16, 38, 84, 0.05);
}

.step-overview {
  width: 100%;
  margin: 0 auto;
}

.step-overview :deep(.n-card__content) {
  padding: 16px 20px;
}

.clickable-steps :deep(.n-step) {
  cursor: pointer;
}

.clickable-steps :deep(.n-step-content-header__title),
.clickable-steps :deep(.n-step-content-header__description) {
  transition: color 0.18s ease;
}

.clickable-steps :deep(.n-step:hover .n-step-content-header__title) {
  color: #2f61ff;
}

.edit-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 460px;
  gap: 16px;
  width: 100%;
  min-height: 0;
  flex: 1;
  margin: 0 auto;
  box-sizing: border-box;
  align-items: stretch;
}

.edit-main {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-width: 0;
  min-height: 0;
}

.content-card {
  flex: 1;
  min-height: 0;
  min-width: 0;
  overflow: hidden;
}

.content-card :deep(.n-card__content) {
  padding-left: 28px;
  padding-right: 28px;
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  overflow: hidden;
}

.content-card :deep(.n-card__header),
.content-card :deep(.n-card__footer) {
  padding-left: 28px;
  padding-right: 28px;
}

.content-card :deep(.n-form) {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.loading-placeholder {
  padding: 8px 4px 14px;
}

.content-card-header,
.section-head {
  align-items: center;
  display: flex;
  justify-content: space-between;
  gap: 16px;
}

.section-head > div:first-child {
  flex: 1;
  min-width: 0;
  margin-right: 16px;
}

.section-head > .n-button,
.section-head > .n-space {
  flex-shrink: 0;
}

.section-muted {
  color: #64748b;
  font-size: 13px;
  line-height: 1.5;
  margin-top: 4px;
  max-width: 520px;
}

.content-title,
.section-title {
  color: #172033;
  font-size: 16px;
  font-weight: 700;
}

.description-input-wrap {
  position: relative;
  width: 100%;
}

.description-input-wrap :deep(.n-input__textarea-el),
.description-input-wrap :deep(.n-input__placeholder) {
  padding-right: 54px !important;
}

.generate-desc-button {
  position: absolute;
  right: 10px;
  top: 10px;
  z-index: 2;
  color: #2f61ff;
  background: rgba(47, 97, 255, 0.12);
  border: 1px solid rgba(47, 97, 255, 0.28);
}

.generate-desc-button:hover {
  color: #1f4de0;
  background: rgba(47, 97, 255, 0.2);
  border-color: rgba(47, 97, 255, 0.42);
}

.generate-desc-button:deep(.n-base-loading) {
  margin: 0 !important;
}

.generate-desc-button:deep(.n-base-loading__container) {
  display: flex;
  align-items: center;
  justify-content: center;
}

.generate-desc-button:deep(.n-button__content) {
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

:deep(.tool-icon),
.tool-icon {
  display: block;
  width: 1em;
  height: 1em;
}

.generate-desc-button:deep(.n-button__state-border),
.generate-desc-button:deep(.n-button__state-icon) {
  pointer-events: none;
}

.step-panel {
  /* max-width: 1080px; */
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}

.step-panel.flex-panel {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.compact-table,
.mcp-tool-list {
  border: 1px solid #e5ebf5;
  border-radius: 8px;
  overflow: hidden;
}

:deep(.schema-editor) {
  border: 1px solid #e5ebf5;
  border-radius: 8px;
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
}

.compact-row,
:deep(.schema-grid) {
  align-items: center;
  border-bottom: 1px solid #edf1f7;
  display: grid;
  gap: 10px;
  padding: 10px 12px;
}

.compact-row:last-child,
:deep(.schema-grid:last-child) {
  border-bottom: 0;
}

.compact-head,
:deep(.schema-head) {
  background: #f7f9fd;
  color: #64748b;
  font-size: 12px;
  font-weight: 700;
}

.header-grid {
  grid-template-columns: minmax(180px, 1fr) minmax(260px, 2fr) 90px;
}

:deep(.input-grid) {
  grid-template-columns: minmax(120px, 1.1fr) minmax(150px, 1.4fr) 100px 100px 60px 110px;
}

:deep(.output-grid) {
  grid-template-columns: minmax(120px, 1.1fr) minmax(180px, 1.6fr) 100px 110px 110px;
}

:deep(.schema-actions) {
  display: flex;
  gap: 4px;
}

.step-actions {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 10px;
}

.debug-grid {
  display: grid;
  gap: 18px;
  grid-template-columns: minmax(320px, 0.9fr) minmax(420px, 1.1fr);
}

.debug-left,
.debug-right {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.debug-param-row {
  display: grid;
  gap: 8px;
}

.debug-param-row label {
  color: #334155;
  font-size: 13px;
  font-weight: 600;
}

.debug-param-row span {
  color: #d03050;
}

.result-panel {
  border: 1px solid #e5ebf5;
  border-radius: 8px;
  overflow: hidden;
}

.result-title {
  background: #f7f9fd;
  color: #334155;
  font-size: 13px;
  font-weight: 700;
  padding: 10px 12px;
}

.result-title-row {
  align-items: center;
  display: flex;
  justify-content: space-between;
  gap: 10px;
}

.mcp-tool-card {
  border-bottom: 1px solid #edf1f7;
  padding: 14px;
}

.mcp-tool-card:last-child {
  border-bottom: 0;
}

.mcp-tool-main {
  align-items: flex-start;
  display: flex;
  gap: 10px;
}

.mcp-tool-name {
  color: #172033;
  font-weight: 700;
}

.aside-card {
  height: 100%;
  min-height: 0;
  position: sticky;
  top: 12px;
}

.aside-card :deep(.n-card__content) {
  height: 100%;
  box-sizing: border-box;
}

.debug-aside {
  display: flex;
  flex-direction: column;
  gap: 8px;
  height: 100%;
  min-height: 0;
  overflow: hidden;
}

.debug-workspace {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 8px;
  min-height: 0;
  overflow: auto;
  padding-right: 2px;
}

.aside-title-row {
  align-items: flex-start;
  display: flex;
  justify-content: space-between;
  gap: 10px;
}

.aside-title {
  color: #101c3d;
  font-size: 18px;
  font-weight: 800;
}

.aside-subtitle {
  margin-top: 14px;
  color: #24385f;
  font-size: 14px;
  font-weight: 700;
}

.aside-subtitle.compact-title {
  margin-top: 2px;
}

.aside-desc {
  margin-top: 4px;
  color: #5f6f85;
  font-size: 13px;
  line-height: 1.45;
}

.debug-overview {
  border: 1px solid #e6ebf5;
  border-radius: 10px;
  display: grid;
  grid-template-columns: 56px minmax(0, 1fr);
  gap: 8px;
  align-items: center;
  padding: 8px 10px;
}

.debug-overview span {
  color: #64748b;
  font-size: 12px;
  font-weight: 700;
}

.debug-overview strong {
  color: #172033;
  font-size: 12px;
  font-weight: 600;
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.debug-param-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.debug-group-title {
  color: #64748b;
  font-size: 12px;
  font-weight: 700;
}

.debug-param-row.compact {
  align-items: center;
  display: grid;
  gap: 8px;
  grid-template-columns: 96px minmax(0, 1fr);
}

.debug-param-row.compact label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.test-summary {
  background: #f8fafc;
  border: 1px solid #e6ebf5;
  border-radius: 10px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px 10px;
}

.test-summary-row {
  align-items: center;
  display: flex;
  justify-content: space-between;
  gap: 10px;
  color: #64748b;
  font-size: 12px;
}

.test-summary-row strong {
  color: #172033;
  font-weight: 700;
}

.test-metrics-row {
  align-items: center;
  display: grid;
  gap: 12px;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
}

.test-metrics-row div {
  align-items: center;
  display: flex;
  gap: 6px;
  min-width: 0;
}

.test-metrics-row div:last-child {
  justify-content: flex-end;
}

.test-metrics-row span {
  color: #64748b;
  font-size: 12px;
  flex: none;
}

.test-metrics-row strong {
  color: #172033;
  font-size: 12px;
  font-weight: 700;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.success-text {
  color: #18a058 !important;
}

.error-text {
  color: #d03050 !important;
}

.response-summary {
  color: #334155;
  font-size: 12px;
  line-height: 1.45;
  max-height: 58px;
  overflow: auto;
  overflow-wrap: anywhere;
}

.debug-json-scroll {
  border-top: 1px solid #edf1f7;
  flex: 1;
  min-height: 120px;
  overflow: auto;
  padding-top: 2px;
}

.debug-collapse {
  min-width: 0;
}

.json-panel-header {
  align-items: center;
  display: flex;
  justify-content: space-between;
  gap: 8px;
  width: 100%;
}

.json-panel-header span {
  color: #334155;
  font-size: 13px;
  font-weight: 700;
}

.json-pre-panel {
  background:
    linear-gradient(90deg, rgba(64, 109, 246, 0.1) 0, rgba(64, 109, 246, 0.1) 3px, transparent 3px),
    #0f172a;
  border: 1px solid #1e2b45;
  border-radius: 8px;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.05);
  margin: 0;
  max-height: 210px;
  overflow: auto;
  padding: 10px 12px 10px 14px;
}

.json-code-panel {
  color: #dbeafe;
  display: block;
  font-family: "SFMono-Regular", "Menlo", "Consolas", "Liberation Mono", monospace;
  font-size: 12px;
  font-weight: 600;
  line-height: 1.55;
  tab-size: 2;
  white-space: pre;
  word-break: normal;
}

@media (max-width: 1280px) {
  .edit-layout {
    grid-template-columns: 1fr;
  }

  .debug-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .tool-edit-page {
    padding: 0 12px 16px;
    gap: 12px;
  }

  .content-card :deep(.n-card__content),
  .content-card :deep(.n-card__header),
  .content-card :deep(.n-card__footer) {
    padding-left: 14px;
    padding-right: 14px;
  }
}
</style>
