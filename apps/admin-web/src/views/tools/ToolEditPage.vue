<template src="./ToolEditPageTemplate.html"></template>

<script setup lang="ts">
import { createToolSchemaInference, type SchemaNode, type FlatInputNode, type SchemaType, type ParamLocation, type ResponseMode } from './toolSchemaInference';
import { computed, defineComponent, h, onMounted, reactive, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { t, useLocale } from '@/composables/i18n';
import { isLegacyGeneratedDescription, timeoutMessagePattern } from '@/locales/legacyRecognitionValues';
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
import ToolOutputSample from './ToolOutputSample.vue';
import { decodeResponseJsonField } from './toolOutputResponse';

interface HeaderRow {
  id: string;
  name: string;
  value: string;
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
        return h(NEmpty, { class: 'schema-empty', description: props.mode === 'input' ? t('legacy.no_input_parameters_defined_yet') : t('legacy.no_output_parameters_defined_yet') });
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

function extractTestResponseBody(): unknown {
  if (!testResult.value) return undefined;
  if ('raw' in testResult.value) return testResult.value.raw;
  return undefined;
}

function schemaFromResponse(response: unknown): SchemaNode[] {
  const raw = decodeResponseJsonField(response, String(form.config.responseJsonPath || ''));
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

function mergeSchemaNodes(target: SchemaNode[], incoming: SchemaNode[], jsonField: string, prefix = ''): number {
  let added = 0;
  for (const node of incoming) {
    const existing = target.find((item) => item.name === node.name);
    if (!existing) {
      target.push(node);
      added += countSchemaNodes([node]);
      continue;
    }
    const path = prefix ? `${prefix}.${node.name}` : node.name;
    if (existing.type !== node.type) {
      if (path !== jsonField || existing.type !== 'String' || !['Object', 'Array'].includes(node.type)) continue;
      existing.type = node.type;
    }
    if (isAutoGeneratedDescription(existing.description)) existing.description = node.description;
    if (!existing.responseMode) existing.responseMode = node.responseMode;
    existing.children ||= [];
    added += mergeSchemaNodes(existing.children, node.children || [], jsonField, path);
  }
  return added;
}

function inferOutputSchemaFromTest() {
  applyOutputSchema(extractTestResponseBody());
}

function applyOutputSchema(response: unknown) {
  const inferred = schemaFromResponse(response);
  if (!inferred.length) {
    message.warning(t('legacy.current_test_response_cannot_generate_output_definition'));
    return;
  }
  const added = mergeSchemaNodes(outputSchema.value, inferred, String(form.config.responseJsonPath || '').trim());
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

const { readableType, normalizeType, normalizeLocation, normalizeResponseMode, inferSchemaType, splitFieldTokens, commonFieldMeaning, childFieldSummary, schemaDescriptionForValue, isAutoGeneratedDescription, sampleArrayItem, inferNodesFromRecord, inferNodeFromValue, parseResultPath, resolvePath, wrapNodesWithResultPath } = createToolSchemaInference(newSchemaNode);

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
    const isTimeout = error?.code === 'ECONNABORTED' || timeoutMessagePattern.test(rawMessage);
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

<style scoped src="./ToolEditPageStyles1.css"></style>
<style scoped src="./ToolEditPageStyles2.css"></style>
