export const desktopCompatibilityMessages = {
  'server-older': {
    zh: '企业 MOVO 服务版本早于此桌面端，兼容性未经验证。建议联系管理员升级服务端；你仍可继续使用。',
    en: 'The enterprise MOVO service is older than this desktop app. Compatibility is unverified. Ask an administrator to update the service; you can continue using the app.',
  },
  'client-older': {
    zh: '企业 MOVO 服务版本较新，兼容性未经验证。建议更新桌面端；你仍可继续使用。',
    en: 'The enterprise MOVO service is newer than this desktop app. Compatibility is unverified. Update the desktop app; you can continue using it.',
  },
  unverified: {
    zh: '当前桌面端与企业服务的版本组合尚未验证。请联系管理员确认服务端是否需要升级；你仍可继续使用。',
    en: 'This desktop and enterprise service combination has not been verified. Ask an administrator whether the service needs an update; you can continue using the app.',
  },
  legacy: {
    zh: '企业 MOVO 服务未提供版本信息，无法确认兼容性。建议管理员升级服务端；你仍可继续使用。',
    en: 'The enterprise MOVO service does not provide release information, so compatibility cannot be verified. Ask an administrator to update the service; you can continue.',
  },
  unavailable: {
    zh: '暂时无法检查企业服务版本。你仍可继续使用。',
    en: 'The enterprise service version cannot be checked right now. You can continue using the app.',
  },
  candidate: {
    zh: '候选桌面版本与当前企业服务的兼容状态：',
    en: 'Candidate desktop version and current enterprise service: ',
  },
} as const
