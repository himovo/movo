import { scopeOf } from '@deepseek-ai/dsh-scope'
import { clientModuleSummaries } from './plugin-client-surfaces.mjs'

function skillSummary(skill) {
  return {
    name: String(skill.name),
    description: String(skill.description ?? ''),
    source: String(skill.source ?? ''),
    provider: String(skill.provider ?? ''),
    modelInvocable: skill.invocation?.modelInvocable === true,
    userInvocable: skill.invocation?.userInvocable === true,
  }
}

function commandSummary(command) {
  return {
    name: String(command.name),
    description: String(command.description ?? ''),
    ...(command.definitionId ? { definitionId: String(command.definitionId) } : {}),
  }
}

function modelProviders(ctx) {
  const llm = ctx.get('llm')
  if (!llm) return []
  return llm.listProviders().map(provider => ({
    id: String(provider.id), name: String(provider.name ?? provider.id),
  }))
}

function webRoutes(ctx) {
  const server = ctx.get('webServer')
  if (!server) return []
  return [
    ...[...(server.exact?.keys() ?? [])].map(path => ({ kind: 'exact', path })),
    ...[...(server.prefixes?.keys() ?? [])].map(path => ({ kind: 'prefix', path })),
  ].sort((left, right) => left.path.localeCompare(right.path) || left.kind.localeCompare(right.kind))
}

function remoteEndpoints(ctx) {
  const gateway = ctx.get('typertGateway')
  const local = ctx.get('typert')?.local?.list?.() ?? []
  return [...new Set([
    ...(gateway && typeof gateway.collectSrcClaims === 'function' ? gateway.collectSrcClaims() : []),
    ...local.map(item => `${item.namespace}/${item.method}`),
  ])].sort()
}

export async function globalPluginCapabilities(ctx) {
  const skills = ctx.get('skills')
  const modules = ctx.get('clientModules')
  return {
    skills: skills ? (await skills.list()).map(skillSummary) : [],
    modelProviders: modelProviders(ctx),
    clientModules: await clientModuleSummaries(modules),
    webRoutes: webRoutes(ctx),
    remoteEndpoints: remoteEndpoints(ctx),
  }
}

export async function sessionPluginCapabilities(ctx, agent) {
  const skills = ctx.get('skills')
  const commands = ctx.get('commands')
  const modules = ctx.get('clientModules')
  return {
    skills: skills ? (await skills.list({
      scope: scopeOf(agent.ctx),
      ...(agent.session.header.cwd ? { cwd: agent.session.header.cwd } : {}),
    })).map(skillSummary) : [],
    commands: commands ? commands.list(agent).map(commandSummary) : [],
    modelProviders: modelProviders(ctx),
    clientModules: await clientModuleSummaries(modules),
    webRoutes: webRoutes(ctx),
    remoteEndpoints: remoteEndpoints(ctx),
  }
}
