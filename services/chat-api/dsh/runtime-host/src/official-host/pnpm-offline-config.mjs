import { existsSync, statSync } from 'node:fs'
import { join, resolve } from 'node:path'

export function packageManagerEnvironment(parent = process.env) {
  const environment = { ...parent }
  const root = resolve(parent.MOVO_OFFLINE_PACKAGE_ROOT || '/offline-packages')
  if (!existsSync(root) || !statSync(root).isDirectory()) return environment
  environment.pnpm_config_store_dir = join(root, 'pnpm')
  environment.pnpm_config_cache_dir = join(root, 'pnpm-cache')
  environment.pnpm_config_prefer_offline = 'true'
  environment.pnpm_config_offline = existsSync(join(root, 'offline-only')) ? 'true' : 'false'
  return environment
}
