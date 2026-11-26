import { dirname, isAbsolute, join } from 'node:path'
import { pathToFileURL } from 'node:url'
import { NATIVE_COMPACTION_CONFIG } from './compaction-config.mjs'

function loaderSpecifier(name) {
  // DSH's declarative preset tree imports row names directly. A Windows
  // absolute path is parsed as a drive-letter URL scheme by Node's ESM loader.
  return process.platform === 'win32' && typeof name === 'string' && isAbsolute(name)
    ? pathToFileURL(name).href : name
}

// The app-boot bare-module anchor applies to the Host Include only. DSH 0.2's
// declarative presets mount a second Loader tree, so resolve their package rows
// against the same installed DSH release before passing declarations to boot.
function resolveRows(rows, installation, presetId) {
  return rows.map(row => {
    const name = row.name
    const resolved = typeof name === 'string' && name.startsWith('@deepseek-ai/')
      ? installation.resolveDependency(name)
      : name
    let config = row.group === true && Array.isArray(row.config)
      ? resolveRows(row.config, installation, presetId)
      : row.config
    if (row.name === '@deepseek-ai/dsh-compaction-basic') {
      config = { ...NATIVE_COMPACTION_CONFIG, ...config }
    }
    // The shipped Cordis preset resolves its bundled skills through baseUrl.
    // In an embedded Host that URL is MOVO's profile, not DSH's installation.
    if (presetId === 'cordis' && row.id === 'skill-filesystem' && Array.isArray(config?.customSkillDirs)) {
      config = {
        ...config,
        customSkillDirs: [join(dirname(installation.resolveDependency('@deepseek-ai/dsh-agent-preset/package.json')), 'skills')],
      }
    }
    // MOVO does not mount DSH's schedule tools. The shipped Web preset denies
    // those names for children, but 0.2 validates deny lists against mounted
    // global tools and rejects an unknown name before the child can start.
    if (['tool-subagent', 'tool-subagent-fork'].includes(row.id) && Array.isArray(config?.toolFilter?.deny)) {
      const deny = config.toolFilter.deny.filter(name => !/^schedule_(create|delete|list|update)$/.test(name))
      config = { ...config, toolFilter: { ...config.toolFilter, deny } }
    }
    return { ...row, name: loaderSpecifier(resolved), ...(config === undefined ? {} : { config }) }
  })
}

export function resolvePresetModules(patches, installation) {
  return patches.map(patch => {
    if (!Array.isArray(patch.insert)) return patch
    return {
      ...patch,
      insert: patch.insert.map(row => {
        if (row.name !== '@deepseek-ai/dsh-agent-preset' || !Array.isArray(row.config?.plugins)) return row
        return { ...row, config: { ...row.config, plugins: resolveRows(row.config.plugins, installation, row.config.id) } }
      }),
    }
  })
}
