import assert from 'node:assert/strict'
import { createServer } from 'node:http'
import { mkdtemp, mkdir, readFile, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import test from 'node:test'

import { KernelRuntime } from '../src/kernel-runtime.mjs'
import { ASKAI_DSH_KERNEL_VERSION } from '../src/host-protocol.mjs'

async function waitFor(predicate) {
  const deadline = Date.now() + 10_000
  while (!predicate()) {
    assert.ok(Date.now() < deadline, 'approval routing did not settle')
    await new Promise(resolve => setTimeout(resolve, 20))
  }
}

// A shipped bundle enables the real plugin Web composition without fetching
// a third-party package. This also mounts the official remote approval answerer.
const plugins = [{ name: '@deepseek-ai/dsh-base', version: ASKAI_DSH_KERNEL_VERSION }]

for (const scenario of [
  { pluginWeb: false, outcome: 'allowed-once' },
  { pluginWeb: true, outcome: 'allowed-once' },
  { pluginWeb: true, outcome: 'rejected' },
  { pluginWeb: true, outcome: 'cancelled' },
  { pluginWeb: true, enterprise: true, outcome: 'rejected' },
]) {
  test(`approval routing with plugin Web ${scenario.pluginWeb}: ${scenario.enterprise ? 'enterprise' : 'native'} ${scenario.outcome}`, async () => {
    const root = await mkdtemp(join(tmpdir(), 'movo-approval-routing-'))
    const workspace = join(root, 'workspace')
    await mkdir(workspace)
    const output = join(root, 'outside.txt')
    let modelCalls = 0
    let enterpriseApprovals = 0
    const server = createServer(async (request, response) => {
      const chunks = []
      for await (const chunk of request) chunks.push(chunk)
      const body = JSON.parse(Buffer.concat(chunks).toString('utf8'))
      if (request.url === '/tools/approval/request') {
        enterpriseApprovals += 1
        assert.equal(body.toolName, 'crm_write')
        response.writeHead(200, { 'content-type': 'application/json' })
        return response.end(JSON.stringify({ outcome: 'rejected' }))
      }
      assert.equal(request.url, '/model')
      const first = ++modelCalls === 1
      response.writeHead(200, { 'content-type': 'application/x-ndjson' })
      const event = first ? {
        type: 'tool-call', id: 'write-a', name: scenario.enterprise ? 'crm_write' : 'write',
        arguments: JSON.stringify(scenario.enterprise ? { value: 'test' } : {
          file_path: output, content: 'approved output',
          sandbox_permissions: 'danger-full-access', justification: 'Approval regression check',
        }),
      } : { type: 'text-delta', text: 'Completed.' }
      response.end([event, { type: 'finish', reason: { kind: first ? 'tool-calls' : 'stop' } }]
        .map(value => JSON.stringify(value)).join('\n') + '\n')
    })
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
    const baseUrl = `http://127.0.0.1:${server.address().port}`
    const runtime = new KernelRuntime({
      runtimeId: 'approval-routing', isolationKey: 'approval-routing', profileVersion: 'test', storageRoot: join(root, 'storage'),
      modelProfile: {
        profileVersion: 'test', modelInstanceId: 'test', modelName: 'test',
        gatewayUrl: `${baseUrl}/model`, accessToken: 'test',
        ...(scenario.pluginWeb ? { plugins } : {}),
        toolProfile: {
          gatewayUrl: `${baseUrl}/tools`, accessToken: 'test', nativeReplacements: [],
          tools: [{ name: 'crm_write', description: 'Write enterprise data',
            input_schema: { type: 'object', properties: { value: { type: 'string' } }, required: ['value'] },
            approval_required: true, risk_level: 'write', timeout_ms: 15000 }],
        },
      },
    })
    const sessionId = 'approval-routing'
    try {
      await runtime.start()
      await runtime.createSession({ sessionId, presetId: 'code', cwd: workspace })
      await runtime.send({ sessionId, mode: 'prompt', content: [{ type: 'text', data: { text: 'Write the test output.' } }],
        temporalContext: { captured_at_utc: '2026-11-19T00:00:00Z', user_local_time: '2026-11-19T08:00:00+08:00', user_timezone: 'Asia/Shanghai' } })
      if (!scenario.enterprise) {
        await waitFor(() => runtime.pendingApprovals(sessionId).length === 1)
        const [pending] = runtime.pendingApprovals(sessionId)
        const asked = runtime.events(sessionId, -1).find(event => event.nativeType === 'approval/asked')
        assert.equal(pending.approvalId, asked.data.id)
        assert.equal(pending.callId, 'write-a')
        await assert.rejects(readFile(output), { code: 'ENOENT' })
        if (scenario.outcome === 'cancelled') await runtime.cancel(sessionId, 'test')
        else runtime.decideApproval(sessionId, pending.approvalId, scenario.outcome)
      }
      await waitFor(() => runtime.events(sessionId, -1).some(event => event.nativeType === 'turn/end'))
      const decided = runtime.events(sessionId, -1).find(event => event.nativeType === 'approval/decided')
      assert.equal(decided?.data.outcome, scenario.outcome)
      assert.deepEqual(runtime.pendingApprovals(sessionId), [])
      assert.equal(enterpriseApprovals, scenario.enterprise ? 1 : 0)
      if (scenario.outcome === 'allowed-once') assert.equal(await readFile(output, 'utf8'), 'approved output')
      else await assert.rejects(readFile(output), { code: 'ENOENT' })
    } finally {
      await runtime.dispose()
      server.closeAllConnections()
      await new Promise(resolve => server.close(resolve))
      await rm(root, { recursive: true, force: true })
    }
  })
}
