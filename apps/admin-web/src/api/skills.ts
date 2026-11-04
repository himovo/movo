import { apiClient } from './client';

export type SkillType = 'writing_style' | 'workflow' | 'ordinary' | 'expert_package';

export interface ExpertPackageChild {
  slug: string; name: string; description: string; version: string;
}

export interface SkillPackageInfo {
  slug: string;
  version: string;
  digest: string;
  files: Array<{ path: string; size: number; sha256: string }>;
  warnings: Array<{ code: string; message: string; tool?: string; packageVersion?: string; skillVersion?: string }>;
  kind: 'ordinary' | 'expert_package';
  children: ExpertPackageChild[];
}

export interface SkillInstallResult {
  id: string; name: string; slug: string; description: string; version: string;
  type: 'ordinary' | 'expert_package'; enabled: boolean; duplicate: boolean; updated: boolean;
  fileCount: number; digest: string;
  dependencyPreparation?: 'disabled' | 'not_required' | 'preparing' | 'ready' | 'failed' | 'unavailable';
  warnings: Array<{ code: string; message: string; tool?: string; packageVersion?: string; skillVersion?: string; childSlug?: string; declaredName?: string; skillName?: string }>;
  childCount: number; children: ExpertPackageChild[];
  compatibility: {
    status: 'compatible' | 'warning'; declaredTools: string[]; referencedTools: string[];
    warnings: Array<{ code: string; message: string; tool?: string; packageVersion?: string; skillVersion?: string }>;
  };
  upgrade?: { action: 'install' | 'duplicate' | 'upgrade' | 'replace' | 'downgrade'; currentVersion?: string; incomingVersion?: string; currentName?: string };
}

export async function fetchSkillDependencyStatus(id: string): Promise<{ status: string }> {
  const { data } = await apiClient.get(`/api/skills/${encodeURIComponent(id)}/dependency-status`);
  return dataOf<{ status: string }>(data);
}

export async function retrySkillDependency(id: string): Promise<{ status: string }> {
  const { data } = await apiClient.post(`/api/skills/${encodeURIComponent(id)}/dependency-retry`);
  return dataOf<{ status: string }>(data);
}

export interface SkillPreparationRecord {
  id: string;
  digest: string;
  baseImageId: string;
  status: 'preparing' | 'ready' | 'failed' | 'interrupted';
  startedAt: string;
  finishedAt: string;
  attempts: Array<{ source: string; exitCode: number }>;
  truncated: boolean;
  log?: string;
}

export async function fetchSkillPreparationRecords(id: string): Promise<SkillPreparationRecord[]> {
  const { data } = await apiClient.get(`/api/skills/${encodeURIComponent(id)}/dependency-records`);
  return data.items || [];
}

export async function fetchSkillPreparationRecord(id: string, recordId: string): Promise<SkillPreparationRecord> {
  const { data } = await apiClient.get(`/api/skills/${encodeURIComponent(id)}/dependency-records/${encodeURIComponent(recordId)}`);
  return data;
}

export interface SkillItem {
  id: string;
  mainId: string;
  name: string;
  description: string;
  scenario: string;
  type: SkillType;
  config: Record<string, any>;
  enabled: boolean;
  environmentStatus?: 'preparing' | 'ready' | 'failed' | 'unavailable' | 'disabled' | null;
  createdAt: string;
  updatedAt: string;
  lifecycle?: { authoringMode: 'platform' | 'package'; publicationStatus: 'draft' | 'published' | 'package'; publishedVersion: string; publishedReleaseId: string; draftRevision: number; hasUnpublishedChanges: boolean };
  package?: SkillPackageInfo | null;
}

export interface SkillPayload {
  name: string;
  description: string;
  scenario: string;
  type: SkillType;
  config: Record<string, any>;
  enabled: boolean;
}

export interface WorkflowStepDraft {
  id?: string;
  text: string;
}

export type WorkflowNodeType =
  | 'read_material'
  | 'extract_resources'
  | 'understand_image'
  | 'extract_info'
  | 'compute_metric'
  | 'data_collect'
  | 'internal_search'
  | 'external_search'
  | 'call_tool'
  | 'script_plugin'
  | 'generate_content'
  | 'translate_rewrite'
  | 'fill_table'
  | 'review_check'
  | 'export_delivery';

export interface WorkflowNodeDraft {
  id?: string;
  type: WorkflowNodeType;
  title: string;
  description: string;
  businessConfig?: Record<string, any>;
  boundWritingSkillId?: string;
  outputAlias?: string;
}

export interface WorkflowCheckResult {
  pass: boolean;
  logic: {
    label: string;
    level: 'success' | 'warning';
    summary: string;
  };
  coverage: Array<{
    key: string;
    label: string;
    covered: boolean;
  }>;
  readiness: Array<{
    key: string;
    label: string;
    ready: boolean;
  }>;
  suggestions: string[];
  conclusion: string;
  source?: string;
  message?: string;
}

export interface ScriptPluginCheckIssue {
  level: 'error' | 'warning';
  code: string;
  message: string;
  line?: number | null;
}

export interface ScriptPluginCheckResult {
  pass: boolean;
  rulePass: boolean;
  errors: ScriptPluginCheckIssue[];
  warnings: ScriptPluginCheckIssue[];
  llm?: {
    pass: boolean;
    level: 'success' | 'warning';
    summary: string;
    risks: string[];
    suggestions: string[];
  } | null;
  source?: string;
  message?: string;
}

export interface WritingStyleDraft {
  publishChannel: string[];
  contentForm: string[];
  targetAudience: string[];
  preferredStyle: string[];
  targetLength?: {
    min?: number;
    max?: number;
    unit?: string;
  };
  sectionStructure?: Array<Record<string, any>>;
  requiredSections: string[];
  requiredElements: string[];
  forbiddenElements: string[];
  inputProfile?: Record<string, any>;
  contractJson?: Record<string, any>;
  skillMarkdown?: string;
}

function dataOf<T>(payload: any): T {
  return payload?.data ?? payload;
}

export async function fetchSkills(): Promise<SkillItem[]> {
  const { data } = await apiClient.get<SkillItem[]>('/api/skills');
  return data;
}

export async function fetchSkill(id: string): Promise<SkillItem> {
  const { data } = await apiClient.get<SkillItem>(`/api/skills/${id}`);
  return data;
}

export async function createSkill(payload: SkillPayload): Promise<SkillItem> {
  const { data } = await apiClient.post<SkillItem>('/api/skills', payload, { timeout: 90000 });
  return data;
}

export async function updateSkill(id: string, payload: SkillPayload): Promise<SkillItem> {
  const { data } = await apiClient.put<SkillItem>(`/api/skills/${id}`, payload, { timeout: 90000 });
  return data;
}

export async function deleteSkill(id: string): Promise<{ id: string }> {
  const { data } = await apiClient.delete<{ id: string }>(`/api/skills/${id}`);
  return data;
}

export async function setSkillEnabled(id: string, enabled: boolean): Promise<SkillItem> {
  const { data } = await apiClient.patch<SkillItem>(`/api/skills/${id}/enabled`, { enabled });
  return data;
}

export async function publishSkill(id: string, version = '', releaseNotes = ''): Promise<{ skill: SkillItem; release: { id: string; version: string } }> {
  const { data } = await apiClient.post(`/api/skills/${id}/publish`, { version, releaseNotes });
  return data;
}

export interface SkillFeedbackSummary {
  items: Array<{ id: string; content: string; parentId: string; author: { userId?: string; displayName?: string }; likes: number; createdAt: string }>;
  likes: number;
}

export async function fetchSkillFeedback(id: string): Promise<SkillFeedbackSummary> {
  const { data } = await apiClient.get<SkillFeedbackSummary>(`/api/skills/${id}/feedback`);
  return data;
}

export async function installSkillZip(file: File, confirmReplace = false): Promise<SkillInstallResult> {
  const form = new FormData();
  form.append('file', file);
  form.append('confirmReplace', String(confirmReplace));
  const { data } = await apiClient.post<SkillInstallResult>('/api/skills/install-zip', form, {
    headers: { 'Content-Type': 'multipart/form-data' }, timeout: 300000,
  });
  return dataOf<SkillInstallResult>(data);
}

export async function generateWorkflowSteps(payload: {
  name: string;
  description?: string;
  scenario?: string;
  existingSteps?: string[];
  maxSteps?: number;
  mode?: 'generate' | 'optimize' | 'supplement' | 'supplement_step';
  supplement?: string;
  nodeCatalog?: Array<{ type: WorkflowNodeType; name: string; usageDescription: string; usageExample: string }>;
}): Promise<{ steps: WorkflowStepDraft[]; source?: string; message?: string }> {
  const { data } = await apiClient.post<{ steps: WorkflowStepDraft[]; source?: string; message?: string }>(
    '/api/skills/generate-workflow-steps',
    payload,
    { timeout: 60000 },
  );
  return data;
}

export async function generateWorkflowNodes(payload: {
  name: string;
  description?: string;
  scenario?: string;
  existingNodes?: WorkflowNodeDraft[];
  maxNodes?: number;
  mode?: 'generate' | 'optimize' | 'supplement' | 'supplement_step';
  supplement?: string;
  nodeCatalog?: Array<{ type: WorkflowNodeType; name: string; usageDescription: string; usageExample: string }>;
}): Promise<{ nodes: WorkflowNodeDraft[]; source?: string; message?: string }> {
  const { data } = await apiClient.post<{ nodes: WorkflowNodeDraft[]; source?: string; message?: string }>(
    '/api/skills/generate-workflow-nodes',
    payload,
    { timeout: 60000 },
  );
  return data;
}

export async function polishWorkflowNode(payload: {
  name: string;
  description?: string;
  scenario?: string;
  node: WorkflowNodeDraft;
  existingNodes?: WorkflowNodeDraft[];
  nodeCatalog?: Array<{ type: WorkflowNodeType; name: string; usageDescription: string; usageExample: string }>;
}): Promise<{ text: string; source?: string; message?: string }> {
  const { data } = await apiClient.post<{ text: string; source?: string; message?: string }>(
    '/api/skills/polish-workflow-node',
    payload,
    { timeout: 60000 },
  );
  return data;
}

export async function checkWorkflowLogic(payload: {
  name: string;
  description?: string;
  scenario?: string;
  steps: string[];
  nodes?: WorkflowNodeDraft[];
}): Promise<WorkflowCheckResult> {
  const { data } = await apiClient.post<WorkflowCheckResult>(
    '/api/skills/check-workflow-logic',
    payload,
    { timeout: 60000 },
  );
  return data;
}

export async function checkWorkflowNodes(payload: {
  name: string;
  description?: string;
  scenario?: string;
  nodes: WorkflowNodeDraft[];
  steps?: string[];
}): Promise<WorkflowCheckResult> {
  const { data } = await apiClient.post<WorkflowCheckResult>(
    '/api/skills/check-workflow-nodes',
    payload,
    { timeout: 60000 },
  );
  return data;
}

export async function checkScriptPlugin(payload: {
  code: string;
  nodeTitle?: string;
  nodeDescription?: string;
}): Promise<ScriptPluginCheckResult> {
  const { data } = await apiClient.post<ScriptPluginCheckResult>(
    '/api/skills/check-script-plugin',
    payload,
    { timeout: 60000 },
  );
  return dataOf<ScriptPluginCheckResult>(data);
}

export async function fixScriptPlugin(payload: {
  code: string;
  nodeTitle?: string;
  nodeDescription?: string;
  issues?: Array<Record<string, any>>;
}): Promise<{
  code: string;
  notes: string[];
  check?: ScriptPluginCheckResult;
}> {
  const { data } = await apiClient.post<{
    code: string;
    notes: string[];
    check?: ScriptPluginCheckResult;
  }>(
    '/api/skills/fix-script-plugin',
    payload,
    { timeout: 90000 },
  );
  const result = dataOf<{
    code: string;
    notes: string[];
    check?: ScriptPluginCheckResult;
  }>(data);
  if (result?.check) {
    result.check = dataOf<ScriptPluginCheckResult>(result.check);
  }
  return result;
}

export async function generateScriptPlugin(payload: {
  processingInstruction: string;
  nodeTitle?: string;
  nodeDescription?: string;
  skillName?: string;
  skillDescription?: string;
  scenario?: string;
  selectedInputSource?: string;
  selectedInputTypes?: string[];
  workflowNodes?: WorkflowNodeDraft[];
}): Promise<{
  code: string;
  notes: string[];
  check?: ScriptPluginCheckResult;
}> {
  const { data } = await apiClient.post<{
    code: string;
    notes: string[];
    check?: ScriptPluginCheckResult;
  }>(
    '/api/skills/generate-script-plugin',
    payload,
    { timeout: 90000 },
  );
  const result = dataOf<{
    code: string;
    notes: string[];
    check?: ScriptPluginCheckResult;
  }>(data);
  if (result?.check) {
    result.check = dataOf<ScriptPluginCheckResult>(result.check);
  }
  return result;
}

export async function enrichWritingStyleDraft(payload: {
  name: string;
  description?: string;
  scenario?: string;
  draft: WritingStyleDraft;
}): Promise<{
  inputProfile: Record<string, any>;
  contractJson: Record<string, any>;
  skillMarkdown: string;
}> {
  const { data } = await apiClient.post<{
    inputProfile: Record<string, any>;
    contractJson: Record<string, any>;
    skillMarkdown: string;
  }>(
    '/api/skills/enrich-writing-style',
    payload,
    { timeout: 60000 },
  );
  return data;
}
