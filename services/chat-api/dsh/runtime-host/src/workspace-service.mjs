import { basename } from 'node:path'
import { SessionId } from '@deepseek-ai/dsh-session'

function requiredId(value, label) {
  const text = String(value ?? '').trim()
  if (!text || text.length > 256) throw new TypeError(`${label} is required`)
  return text
}

async function projection(workspace) {
  return {
    workspaceId: String(workspace.id),
    title: workspace.title,
    path: workspace.path,
    status: await workspace.status(),
    sessionIds: [...workspace.sessionIds].map(String),
    createdAt: workspace.createdAt,
    updatedAt: workspace.updatedAt,
  }
}

/** Thin ASKAI adapter over DSH's authoritative Workspace Registry. */
export class DshWorkspaceService {
  constructor(registry) {
    if (registry === undefined) throw new Error('DSH Workspace Registry is unavailable')
    this.registry = registry
  }

  async list() {
    return await Promise.all(this.registry.list().map(projection))
  }

  async create({ path, title }) {
    const requestedPath = String(path ?? '').trim()
    if (!requestedPath) throw new TypeError('workspace path is required')
    const workspace = await this.registry.create(requestedPath, String(title ?? '').trim() || basename(requestedPath))
    return await projection(workspace)
  }

  async get(workspaceId, { requireAvailable = false } = {}) {
    const workspace = this.registry.get(requiredId(workspaceId, 'workspaceId'))
    if (workspace === undefined) throw new Error(`workspace not found: ${workspaceId}`)
    const result = await projection(workspace)
    if (requireAvailable && result.status !== 'ok') throw new Error(`workspace directory is unavailable: ${workspaceId}`)
    return { workspace, result }
  }

  async rename(workspaceId, title) {
    const value = String(title ?? '').trim()
    if (!value || value.length > 200) throw new TypeError('workspace title is required')
    const { workspace } = await this.get(workspaceId)
    await workspace.setTitle(value)
    return (await this.get(workspaceId)).result
  }

  async delete(workspaceId) {
    return { deleted: await this.registry.delete(requiredId(workspaceId, 'workspaceId')) }
  }

  async attachSession(workspaceId, sessionId) {
    const { workspace } = await this.get(workspaceId, { requireAvailable: true })
    await workspace.attachSession(SessionId(requiredId(sessionId, 'sessionId')))
    return (await this.get(workspaceId)).result
  }

  async resolveSessionWorkspace(session) {
    const cwd = session?.header?.cwd
    if (typeof cwd !== 'string' || !cwd) return undefined
    return this.registry.list().find(workspace => workspace.path === cwd)
  }
}
