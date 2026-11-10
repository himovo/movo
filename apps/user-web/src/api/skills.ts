import { createApiClient } from './client'

const api = createApiClient({
  baseURL: '/askai-api/api',
  timeout: 120000,
})

export type SkillType = 'writing_style' | 'workflow' | 'ordinary' | 'expert_package'

export interface ExpertPackageChild {
  slug: string
  name: string
  description: string
  version: string
}

export interface SkillPackageInfo {
  slug: string
  version: string
  digest: string
  files: Array<{ path: string; size: number; sha256: string }>
  warnings: Array<{ code: string; message: string; tool?: string; packageVersion?: string; skillVersion?: string }>
  kind: 'ordinary' | 'expert_package'
  children: ExpertPackageChild[]
}

export interface SkillInstallResult {
  id: string
  name: string
  slug: string
  description: string
  version: string
  type: 'ordinary' | 'expert_package'
  enabled: boolean
  duplicate: boolean
  updated: boolean
  fileCount: number
  digest: string
  dependencyPreparation?: 'disabled' | 'not_required' | 'preparing' | 'ready' | 'failed' | 'unavailable'
  warnings: Array<{ code: string; message: string; tool?: string; packageVersion?: string; skillVersion?: string; childSlug?: string; declaredName?: string; skillName?: string }>
  childCount: number
  children: ExpertPackageChild[]
  compatibility: {
    status: 'compatible' | 'warning'
    declaredTools: string[]
    referencedTools: string[]
    warnings: Array<{ code: string; message: string; tool?: string; packageVersion?: string; skillVersion?: string }>
  }
  upgrade?: SkillUpgradeInfo
}

export async function fetchSkillDependencyStatus(id: string): Promise<{ status: string }> {
  const res = await api.get(`/skills/${encodeURIComponent(id)}/dependency-status`)
  return dataOf<{ status: string }>(res)
}

export async function retrySkillDependency(id: string): Promise<{ status: string }> {
  const res = await api.post(`/skills/${encodeURIComponent(id)}/dependency-retry`)
  return dataOf<{ status: string }>(res)
}

export interface SkillUpgradeInfo {
  action: 'install' | 'duplicate' | 'upgrade' | 'replace' | 'downgrade'
  currentVersion?: string
  incomingVersion?: string
  currentName?: string
}

export interface SkillLifecycle {
  authoringMode: 'platform' | 'package'
  publicationStatus: 'draft' | 'published' | 'package'
  publishedVersion: string
  publishedReleaseId: string
  draftRevision: number
  hasUnpublishedChanges: boolean
}

export interface SkillFeedbackChannel {
  id: string
  role: 'owner' | 'member'
  commentCount: number
  unreadCount: number
  latestCommentAt: string
}

export interface SkillFeedbackSummary {
  commentCount: number
  unreadCount: number
  channels: SkillFeedbackChannel[]
}

export interface SkillItem {
  id: string
  mainId: string
  name: string
  description: string
  scenario: string
  type: SkillType
  config: Record<string, any>
  enabled: boolean
  environmentStatus?: 'preparing' | 'ready' | 'failed' | 'unavailable' | 'disabled' | null
  createdAt: string
  updatedAt: string
  packageSource?: {
    kind?: string
    mode?: string
    fileName?: string
    coordinate?: string
    sender?: { userId?: string; displayName?: string; username?: string }
    distributionId?: string
    releaseId?: string
  }
  distributionId?: string
  feedback?: SkillFeedbackSummary
  locallyModified?: boolean
  lifecycle?: SkillLifecycle
  package?: SkillPackageInfo | null
}

export interface SkillPayload {
  name: string
  description: string
  scenario: string
  type: SkillType
  config: Record<string, any>
  enabled: boolean
}

export interface SelectableSkillItem {
  id: string
  mainId: string
  name: string
  description: string
  scenario: string
  type: SkillType
  sourceScope: 'user' | 'organization'
  pluginName?: string
  entryKind?: 'command'
  enabled: boolean
  available?: boolean
  unavailableReason?: string
  updatedAt?: string
}

export interface SelectableSkillPage {
  items: SelectableSkillItem[]
  nextCursor: string
  hasMore: boolean
}

export interface WorkflowStepDraft {
  id?: string
  text: string
}

export type WorkflowNodeType =
  | 'read_material'
  | 'extract_resources'
  | 'understand_image'
  | 'extract_info'
  | 'compute_metric'
  | 'data_collect'
  | 'browser_automation'
  | 'internal_search'
  | 'external_search'
  | 'call_tool'
  | 'script_plugin'
  | 'generate_content'
  | 'translate_rewrite'
  | 'fill_table'
  | 'review_check'
  | 'export_delivery'

export interface WorkflowNodeDraft {
  id?: string
  type: WorkflowNodeType
  title: string
  description: string
  businessConfig?: Record<string, any>
  boundWritingSkillId?: string
  outputAlias?: string
}

export interface WorkflowCheckResult {
  pass: boolean
  logic: {
    label: string
    level: 'success' | 'warning'
    summary: string
  }
  coverage: Array<{ key: string; label: string; covered: boolean }>
  readiness: Array<{ key: string; label: string; ready: boolean }>
  suggestions: string[]
  conclusion: string
  source?: string
  message?: string
}

export interface ScriptPluginCheckIssue {
  level: 'error' | 'warning'
  code: string
  message: string
  line?: number | null
}

export interface ScriptPluginCheckResult {
  pass: boolean
  rulePass: boolean
  errors: ScriptPluginCheckIssue[]
  warnings: ScriptPluginCheckIssue[]
  llm?: {
    pass: boolean
    level: 'success' | 'warning'
    summary: string
    risks: string[]
    suggestions: string[]
  } | null
  source?: string
  message?: string
}

export interface WritingStyleDraft {
  publishChannel: string[]
  contentForm: string[]
  targetAudience: string[]
  preferredStyle: string[]
  targetLength?: {
    min?: number
    max?: number
    unit?: string
  }
  sectionStructure?: Array<Record<string, any>>
  requiredSections: string[]
  requiredElements: string[]
  forbiddenElements: string[]
  inputProfile?: Record<string, any>
  contractJson?: Record<string, any>
  skillMarkdown?: string
}

export interface SkillSourceUpload {
  object_path: string
  filename?: string
  [key: string]: unknown
}

export interface SkillDraftEnrichment {
  contract_json?: Record<string, any>
  skill_markdown?: string
}

export interface TemplateAnalysis {
  skill_markdown?: string
  resources?: Record<string, any>
}

function params(userId: string | null | undefined, mainId: string | null | undefined) {
  return {
    userId: userId || '',
    mainId: mainId || 'default',
  }
}

function dataOf<T>(res: { data?: any }): T {
  return res.data?.data ?? res.data
}

export async function fetchSkills(userId: string, mainId = 'default'): Promise<SkillItem[]> {
  const res = await api.get('/skills', { params: params(userId, mainId), timeout: 15000 })
  return dataOf<SkillItem[]>(res) || []
}

export async function listSkills(userId: string, mainId = 'default'): Promise<SkillItem[]> {
  return fetchSkills(userId, mainId)
}

export async function fetchSelectableSkills(payload: {
  userId: string
  mainId?: string
  scope?: 'all' | 'user' | 'organization'
  keyword?: string
  cursor?: string
  limit?: number
}): Promise<SelectableSkillPage> {
  const res = await api.get('/skills/selectable', {
    params: {
      ...params(payload.userId, payload.mainId),
      scope: payload.scope || 'all',
      keyword: payload.keyword || '',
      cursor: payload.cursor || '',
      limit: payload.limit || 20,
    },
    timeout: 15000,
  })
  const data = dataOf<SelectableSkillPage>(res) || { items: [], nextCursor: '', hasMore: false }
  return {
    items: Array.isArray(data.items) ? data.items : [],
    nextCursor: String(data.nextCursor || ''),
    hasMore: Boolean(data.hasMore),
  }
}

export async function fetchSelectablePluginSkills(payload: {
  scope?: 'all' | 'user' | 'organization'
  keyword?: string
  cursor?: string
  limit?: number
}): Promise<SelectableSkillPage> {
  const res = await api.get('/dsh-plugins/personal/selectable-skills', {
    params: {
      scope: payload.scope || 'all',
      keyword: payload.keyword || '',
      cursor: payload.cursor || '0',
      limit: payload.limit || 20,
    },
    timeout: 15000,
  })
  const data = dataOf<SelectableSkillPage>(res) || { items: [], nextCursor: '', hasMore: false }
  return {
    items: Array.isArray(data.items) ? data.items : [],
    nextCursor: String(data.nextCursor || ''),
    hasMore: Boolean(data.hasMore),
  }
}

export async function fetchSelectablePluginCommands(payload: {
  scope?: 'all' | 'user' | 'organization'
  keyword?: string
  cursor?: string
  limit?: number
}): Promise<SelectableSkillPage> {
  const res = await api.get('/dsh-plugins/personal/selectable-commands', {
    params: {
      scope: payload.scope || 'all',
      keyword: payload.keyword || '',
      cursor: payload.cursor || '0',
      limit: payload.limit || 20,
    },
    timeout: 15000,
  })
  const data = dataOf<SelectableSkillPage>(res) || { items: [], nextCursor: '', hasMore: false }
  return {
    items: Array.isArray(data.items) ? data.items : [],
    nextCursor: String(data.nextCursor || ''),
    hasMore: Boolean(data.hasMore),
  }
}

export async function fetchSkill(id: string, userId: string, mainId = 'default'): Promise<SkillItem> {
  const res = await api.get(`/skills/${id}`, { params: params(userId, mainId) })
  return dataOf<SkillItem>(res)
}

export async function createSkill(userId: string, mainId: string, payload: SkillPayload): Promise<SkillItem> {
  const res = await api.post('/skills', payload, { params: params(userId, mainId), timeout: 90000 })
  return dataOf<SkillItem>(res)
}

export async function updateSkill(id: string, userIdOrPayload: string | any, mainId = 'default', payload?: SkillPayload): Promise<SkillItem> {
  let userId = String(userIdOrPayload || '')
  let body = payload
  let resolvedMainId = mainId
  if (typeof userIdOrPayload === 'object') {
    const legacy = userIdOrPayload || {}
    userId = String(legacy.user_id || legacy.userId || '')
    resolvedMainId = String(legacy.main_id || legacy.mainId || 'default')
    const skillType = String(legacy.skill_type || legacy.type || 'style')
    const type: SkillType = skillType === 'composite_task' || skillType === 'workflow' ? 'workflow' : 'writing_style'
    body = {
      name: String(legacy.name || ''),
      description: String(legacy.description || legacy.summary || ''),
      scenario: String(legacy.scenario || legacy.notes || ''),
      type,
      config: {
        ...(legacy.config || {}),
        inputProfile: legacy.input_profile || legacy.config?.inputProfile || {},
        contractJson: legacy.contract_json || legacy.config?.contractJson || {},
        skillMarkdown: legacy.skill_markdown || legacy.config?.skillMarkdown || '',
      },
      enabled: legacy.is_active !== false && legacy.enabled !== false,
    }
  }
  const res = await api.put(`/skills/${id}`, body, { params: params(userId, resolvedMainId), timeout: 90000 })
  return dataOf<SkillItem>(res)
}

export async function deleteSkill(id: string, userId: string, mainId = 'default'): Promise<{ id: string }> {
  const res = await api.delete(`/skills/${id}`, { params: params(userId, mainId) })
  return dataOf<{ id: string }>(res)
}

export async function setSkillEnabled(id: string, userId: string, mainId: string, enabled: boolean): Promise<SkillItem> {
  const res = await api.patch(`/skills/${id}/enabled`, { enabled }, { params: params(userId, mainId) })
  return dataOf<SkillItem>(res)
}

export async function installPersonalSkillZip(file: File, confirmReplace = false): Promise<SkillInstallResult> {
  const form = new FormData()
  form.append('file', file)
  form.append('confirmReplace', String(confirmReplace))
  const res = await api.post('/skills/install-zip', form, {
    headers: { 'Content-Type': 'multipart/form-data' }, timeout: 300000,
  })
  return dataOf<SkillInstallResult>(res)
}

export async function publishSkill(id: string, version = '', releaseNotes = ''): Promise<{ skill: SkillItem; release: { id: string; version: string; digest: string; releaseNotes: string; createdAt: string } }> {
  const res = await api.post(`/skills/${id}/publish`, { version, releaseNotes })
  return dataOf(res)
}

export async function fetchSkillReleases(id: string): Promise<Array<{ id: string; version: string; digest: string; releaseNotes: string; createdAt: string }>> {
  const res = await api.get(`/skills/${id}/releases`)
  return dataOf<{ items: any[] }>(res)?.items || []
}

export async function generateWorkflowSteps(payload: {
  name: string
  description?: string
  scenario?: string
  existingSteps?: string[]
  maxSteps?: number
  mode?: 'generate' | 'optimize' | 'supplement' | 'supplement_step'
  supplement?: string
  nodeCatalog?: Array<{ type: WorkflowNodeType; name: string; usageDescription: string; usageExample: string }>
}): Promise<{ steps: WorkflowStepDraft[]; source?: string; message?: string }> {
  const res = await api.post('/skills/generate-workflow-steps', payload, { timeout: 60000 })
  return dataOf<{ steps: WorkflowStepDraft[]; source?: string; message?: string }>(res)
}

export async function generateWorkflowNodes(payload: {
  name: string
  description?: string
  scenario?: string
  existingNodes?: WorkflowNodeDraft[]
  maxNodes?: number
  mode?: 'generate' | 'optimize' | 'supplement' | 'supplement_step'
  supplement?: string
  nodeCatalog?: Array<{ type: WorkflowNodeType; name: string; usageDescription: string; usageExample: string }>
}): Promise<{ nodes: WorkflowNodeDraft[]; source?: string; message?: string }> {
  const res = await api.post('/skills/generate-workflow-nodes', payload, { timeout: 60000 })
  return dataOf<{ nodes: WorkflowNodeDraft[]; source?: string; message?: string }>(res)
}

export async function checkWorkflowNodes(payload: {
  name: string
  description?: string
  scenario?: string
  nodes: WorkflowNodeDraft[]
  steps?: string[]
}): Promise<WorkflowCheckResult> {
  const res = await api.post('/skills/check-workflow-nodes', payload, { timeout: 60000 })
  return dataOf<WorkflowCheckResult>(res)
}

export async function checkWorkflowLogic(payload: {
  name: string
  description?: string
  scenario?: string
  steps: string[]
  nodes?: WorkflowNodeDraft[]
}): Promise<WorkflowCheckResult> {
  const res = await api.post('/skills/check-workflow-logic', payload, { timeout: 60000 })
  return dataOf<WorkflowCheckResult>(res)
}

export async function checkScriptPlugin(payload: {
  code: string
  nodeTitle?: string
  nodeDescription?: string
}): Promise<ScriptPluginCheckResult> {
  const res = await api.post('/skills/check-script-plugin', payload, { timeout: 60000 })
  return dataOf<ScriptPluginCheckResult>(res)
}

export async function fixScriptPlugin(payload: {
  code: string
  nodeTitle?: string
  nodeDescription?: string
  issues?: Array<Record<string, any>>
}): Promise<{ code: string; notes: string[]; check?: ScriptPluginCheckResult }> {
  const res = await api.post('/skills/fix-script-plugin', payload, { timeout: 90000 })
  return dataOf<{ code: string; notes: string[]; check?: ScriptPluginCheckResult }>(res)
}

export async function generateScriptPlugin(payload: {
  processingInstruction: string
  nodeTitle?: string
  nodeDescription?: string
  skillName?: string
  skillDescription?: string
  scenario?: string
  selectedInputSource?: string
  selectedInputTypes?: string[]
  workflowNodes?: WorkflowNodeDraft[]
}): Promise<{ code: string; notes: string[]; check?: ScriptPluginCheckResult }> {
  const res = await api.post('/skills/generate-script-plugin', payload, { timeout: 90000 })
  return dataOf<{ code: string; notes: string[]; check?: ScriptPluginCheckResult }>(res)
}

export async function enrichWritingStyleDraft(payload: {
  userId: string
  mainId: string
  name: string
  description?: string
  scenario?: string
  draft: WritingStyleDraft
}): Promise<{
  inputProfile: Record<string, any>
  contractJson: Record<string, any>
  skillMarkdown: string
}> {
  const res = await api.post(
    '/skills/enrich-writing-style',
    {
      name: payload.name,
      description: payload.description || '',
      scenario: payload.scenario || '',
      draft: payload.draft,
    },
    { params: params(payload.userId, payload.mainId), timeout: 60000 },
  )
  return dataOf(res)
}

// Compatibility for older components that are no longer used by /skills.
export async function uploadSkillSource(userId: string, file: File): Promise<SkillSourceUpload> {
  const form = new FormData()
  form.append('user_id', userId)
  form.append('file', file)
  const res = await api.post('/skills/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return dataOf<SkillSourceUpload>(res)
}

export async function analyzeTemplate(file: File): Promise<TemplateAnalysis> {
  const form = new FormData()
  form.append('file', file)
  const res = await api.post('/skills/analyze_template', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return dataOf<TemplateAnalysis>(res)
}

export async function generateSkill(payload: any) {
  const userId = String(payload?.user_id || payload?.userId || '')
  const mainId = String(payload?.main_id || payload?.mainId || 'default')
  const skillType = String(payload?.skill_type || payload?.type || 'style')
  const type: SkillType = skillType === 'composite_task' || skillType === 'workflow' ? 'workflow' : 'writing_style'
  return createSkill(userId, mainId, {
    name: String(payload?.name || ''),
    description: String(payload?.description || payload?.summary || ''),
    scenario: String(payload?.scenario || payload?.notes || ''),
    type,
    config: {
      inputProfile: payload?.input_profile || {},
      contractJson: payload?.contract_json || {},
      skillMarkdown: payload?.skill_markdown || '',
    },
    enabled: payload?.is_active === true,
  })
}

export async function enrichSkillDraft(payload: any): Promise<SkillDraftEnrichment> {
  const res = await api.post('/skills/enrich_draft', payload)
  return dataOf<SkillDraftEnrichment>(res)
}
