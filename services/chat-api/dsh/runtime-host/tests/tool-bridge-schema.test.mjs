import assert from 'node:assert/strict'
import test from 'node:test'

import { AskaiToolBridge, validateDescriptorArguments } from '../src/askai-tool-bridge-plugin.mjs'

const descriptor = {
  input_schema: {
    type: 'object',
    properties: {
      facts: {
        type: 'array',
        items: {
          type: 'object',
          properties: {
            field: { type: 'string' },
            value: {},
          },
          required: ['field', 'value'],
          additionalProperties: false,
        },
      },
    },
    additionalProperties: false,
  },
}

test('tool bridge rejects malformed nested arguments before approval', () => {
  const violations = validateDescriptorArguments(descriptor, {
    facts: [{ fact: '预算约50万元', type: 'budget' }],
  })
  assert.ok(violations.length > 0)
  assert.match(violations.join('; '), /field|value|fact|type/)
})

test('tool bridge accepts the CRM field/value fact contract', () => {
  assert.deepEqual(validateDescriptorArguments(descriptor, {
    facts: [{ field: '预算', value: 500000 }],
  }), [])
})

test('native replacement stays available to the gateway but is not registered as a duplicate model tool', () => {
  const registered = []
  const ctx = {
    tools: { register: spec => { registered.push(spec.name); return () => {} } },
    on: () => () => {},
  }
  const bridge = new AskaiToolBridge(ctx, {
    tools: [
      { ...descriptor, name: 'external_search', description: 'provider', output_schema: {}, timeout_ms: 1000, risk_level: 'read', approval_required: false },
      { ...descriptor, name: 'knowledge_search', description: 'knowledge', output_schema: {}, timeout_ms: 1000, risk_level: 'read', approval_required: false },
    ],
    nativeReplacements: ['external_search'],
    gatewayUrl: 'http://unused.invalid', accessToken: 'test',
  })
  assert.deepEqual(registered, ['knowledge_search'])
  bridge.dispose()
})

test('enterprise tools cannot shadow official DSH Code tool names', () => {
  const tool = { ...descriptor, name: 'bash' }
  assert.throws(
    () => new AskaiToolBridge({}, {
      profileVersion: 'profile-a', tools: [tool], gatewayUrl: 'http://gateway.test', accessToken: 'test',
    }),
    /collide with DSH Code tools: bash/,
  )
})

test('tool bridge rejects an opportunity stage outside the published enum', () => {
  const opportunity = {
    input_schema: {
      type: 'object',
      properties: {
        customer_id: { type: 'string' },
        name: { type: 'string' },
        stage: { type: 'string', enum: ['lead', 'needs_confirmed', 'proposal'] },
      },
      required: ['customer_id', 'name'],
      additionalProperties: false,
    },
  }
  const violations = validateDescriptorArguments(opportunity, {
    customer_id: 'cus_1',
    name: '星河科技私有化部署项目',
    stage: '需求确认',
  })
  assert.ok(violations.length > 0)
  assert.match(violations.join('; '), /stage|enum|needs_confirmed/)
})

test('malformed arguments are denied by pre-execute before approval is requested', async () => {
  const handlers = new Map()
  const ctx = {
    tools: { register: () => () => {} },
    on: (name, handler) => {
      handlers.set(name, handler)
      return () => handlers.delete(name)
    },
  }
  const tool = {
    ...descriptor,
    name: 'crm_record_interaction',
    description: 'record',
    output_schema: {},
    timeout_ms: 1000,
    risk_level: 'write',
    approval_required: true,
  }
  const bridge = new AskaiToolBridge(ctx, {
    tools: [tool],
    gatewayUrl: 'http://unused.invalid',
    accessToken: 'test',
  })
  let delegated = false
  const decision = await handlers.get('tools/pre-execute')({
    name: tool.name,
    arguments: { facts: [{ fact: '预算约50万元', type: 'budget' }] },
  }, async () => {
    delegated = true
    return { kind: 'allow' }
  })
  assert.equal(decision.kind, 'deny')
  assert.match(decision.reason, /invalid tool arguments/)
  assert.equal(delegated, false)
  bridge.dispose()
})

test('advisory HTTP output schema is not installed as DSH strict validation', () => {
  let registered
  const ctx = {
    tools: { register: spec => { registered = spec; return () => {} } },
    on: () => () => {},
  }
  const bridge = new AskaiToolBridge(ctx, {
    tools: [{
      ...descriptor,
      name: 'http_store_snapshot',
      description: 'snapshot',
      output_schema: {
        type: 'object',
        properties: { stores: { type: 'array', items: { type: 'object' } } },
      },
      output_validation: 'none',
      timeout_ms: 1000,
      risk_level: 'read',
      approval_required: false,
    }],
    gatewayUrl: 'http://unused.invalid',
    accessToken: 'test',
  })
  assert.deepEqual(registered.output.schema, {})
  bridge.dispose()
})

test('protocol-authored output schema remains strict', () => {
  let registered
  const ctx = {
    tools: { register: spec => { registered = spec; return () => {} } },
    on: () => () => {},
  }
  const outputSchema = { type: 'object', properties: { code: { type: 'integer' } } }
  const bridge = new AskaiToolBridge(ctx, {
    tools: [{
      ...descriptor,
      name: 'mcp_contract_tool',
      description: 'mcp',
      output_schema: outputSchema,
      output_validation: 'strict',
      timeout_ms: 1000,
      risk_level: 'read',
      approval_required: false,
    }],
    gatewayUrl: 'http://unused.invalid',
    accessToken: 'test',
  })
  assert.deepEqual(registered.output.schema, outputSchema)
  bridge.dispose()
})

test('DSH tool deadline leaves the ASKAI gateway time to finalize its receipt', () => {
  let registered
  const ctx = {
    tools: { register: spec => { registered = spec; return () => {} } },
    on: () => () => {},
  }
  const bridge = new AskaiToolBridge(ctx, {
    tools: [{
      ...descriptor,
      name: 'content_production',
      description: 'content',
      output_schema: {},
      timeout_ms: 1_800_000,
      risk_level: 'read',
      approval_required: false,
    }],
    gatewayUrl: 'http://unused.invalid', accessToken: 'test',
  })
  assert.equal(registered.timeoutMs, 1_830_000)
  bridge.dispose()
})

test('argument-aware policy asks only for browser side effects', async () => {
  const handlers = new Map()
  const ctx = {
    tools: { register: () => () => {} },
    on: (name, handler) => { handlers.set(name, handler); return () => handlers.delete(name) },
  }
  const tool = {
    name: 'browser_task', description: 'browser',
    input_schema: { type: 'object', properties: { operation: { type: 'string' } } },
    output_schema: {}, output_validation: 'none', timeout_ms: 1000,
    risk_level: 'dangerous', approval_required: false,
    approval_argument: 'operation', approval_values: ['submit', 'modify', 'delete', 'file_transfer', 'publish'],
  }
  const bridge = new AskaiToolBridge(ctx, { tools: [tool], gatewayUrl: 'http://unused.invalid', accessToken: 'test' })
  const read = await handlers.get('tools/pre-execute')({
    name: tool.name, arguments: { operation: 'read' }, agent: { id: 's' }, callId: 'read-1',
  }, async () => ({ kind: 'allow' }))
  const publish = await handlers.get('tools/pre-execute')({
    name: tool.name, arguments: { operation: 'publish' }, agent: { id: 's' }, callId: 'write-1',
  }, async () => ({ kind: 'allow' }))
  assert.equal(read.kind, 'allow')
  assert.equal(publish.kind, 'ask')
  bridge.dispose()
})

test('browser approval forwards the exact action and uses a bounded ASKAI deadline', async () => {
  const handlers = new Map()
  const ctx = {
    tools: { register: () => () => {} },
    on: (name, handler) => { handlers.set(name, handler); return () => handlers.delete(name) },
  }
  const tool = {
    name: 'browser_task', description: 'browser',
    input_schema: { type: 'object', properties: { operation: { type: 'string' } } },
    output_schema: {}, output_validation: 'none', timeout_ms: 300000,
    risk_level: 'dangerous', approval_required: false,
    approval_argument: 'operation', approval_values: ['submit'],
  }
  let body
  const requestJson = async (_url, payload) => {
    body = payload
    return { ok: true, status: 200, payload: { outcome: 'allowed-once' } }
  }
  const bridge = new AskaiToolBridge(ctx, {
    profileVersion: 'profile-a', tools: [tool], gatewayUrl: 'http://gateway.test', accessToken: 'test',
  }, { requestJson })
  try {
    await handlers.get('tools/pre-execute')({
      name: tool.name, arguments: { operation: 'submit' }, agent: { id: 'session-a' }, callId: 'action-a',
    }, async () => ({ kind: 'allow' }))
    const outcome = await handlers.get('approval/request')({
      toolName: tool.name, agent: { id: 'session-a' }, callId: 'action-a', reason: 'write',
    }, async () => 'unavailable')
    assert.equal(outcome, 'allowed-once')
    assert.equal(body.actionId, 'action-a')
    assert.deepEqual(body.arguments, { operation: 'submit' })
    assert.equal(body.timeoutSeconds, 240)
  } finally {
    bridge.dispose()
  }
})
