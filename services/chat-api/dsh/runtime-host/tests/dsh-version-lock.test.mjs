import test from 'node:test'
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'

import { assertLockedDshVersion } from '../src/official-host/installation.mjs'
import { runtimeHealth } from '../src/host-protocol.mjs'

test('runtime rejects a DSH installation that differs from the exact host lock', () => {
  const manifest = { dependencies: { '@deepseek-ai/dsh': '0.2.1-alpha.1' } }
  assert.doesNotThrow(() => assertLockedDshVersion('0.2.1-alpha.1', manifest))
  assert.throws(() => assertLockedDshVersion('0.2.0', manifest), /does not match/)
  assert.throws(() => assertLockedDshVersion('0.2.1-alpha.1', { dependencies: {} }), /missing/)
})

test('health reports the installed DSH release and lock agreement', () => {
  const require = createRequire(import.meta.url)
  const installed = require('@deepseek-ai/dsh/package.json').version
  const declared = require('../package.json').dependencies['@deepseek-ai/dsh']
  const health = runtimeHealth([])
  assert.equal(health.version, installed)
  assert.equal(health.lockedVersion, declared)
  assert.equal(health.ok, installed === declared)
})
