export const DSH_CODE_PRESET_ID = 'code'

function usesSessionPermissionProjection(version) {
  return /^0\.1\.2(?:-|$)/.test(version)
}

/** Keep ASKAI's stable `code` contract while DSH evolves preset names. */
export async function resolveNativePreset(presets, requestedPreset) {
  if (requestedPreset !== DSH_CODE_PRESET_ID) return await presets.resolve(requestedPreset)
  try {
    return await presets.resolve(DSH_CODE_PRESET_ID)
  } catch (error) {
    if (error?.code !== 'agent-preset/not-found') throw error
    return await presets.resolve('standard')
  }
}

/** Normalize the permission projection boundary across the approved trains. */
export function currentPermissionPreset(permissionPresets, session, dshVersion) {
  return usesSessionPermissionProjection(dshVersion)
    ? permissionPresets.current(session)
    : permissionPresets.current(session.events)
}
