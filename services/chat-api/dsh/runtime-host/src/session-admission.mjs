import { resolveSessionSeed } from './session-seed.mjs'
import { codePermissionPolicy } from './code-permission-policy.mjs'
import { validConversationSpaceKey } from './personal-space.mjs'

// The parent Host resolves predecessor identities before sending a trusted
// seed to a plugin-isolated child. Raw seeds remain forbidden at the public API.
export async function admitSessionBody(input, seedSource, { trusted = false } = {}) {
  let body = input
  if (Object.hasOwn(body, 'cwd')) throw new Error('raw cwd is forbidden over the Runtime Host API; use workspaceId')
  if (body.personalConversationKey !== undefined && !validConversationSpaceKey(body.personalConversationKey)) {
    throw new Error('invalid personal conversation key')
  }
  if (trusted) {
    if (process.env.MOVO_DSH_PLUGIN_CHILD !== '1' ||
        Object.hasOwn(body, 'seedRuntimeId') || Object.hasOwn(body, 'seedSessionId') ||
        (body.seed !== undefined && (!Array.isArray(body.seed) || !body.parentSessionId))) {
      throw new Error('trusted Session seed is not permitted')
    }
  } else {
    body = await resolveSessionSeed(seedSource, body)
  }
  if (body.presetId === 'code') {
    if (body.workspaceId === undefined) throw new Error('Code Session requires a DSH workspaceId')
    Object.assign(body, codePermissionPolicy(body))
  }
  return body
}
