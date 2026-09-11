import { readFile, realpath, stat } from 'node:fs/promises'
import { isAbsolute, relative, resolve, sep } from 'node:path'

const DEFAULT_LINE_COUNT = 200
const MAX_LINE_COUNT = 500
const MAX_TEXT_BYTES = 1024 * 1024

function containedPath(root, requested) {
  const raw = String(requested ?? '').trim()
  if (!raw || raw.includes('\0') || isAbsolute(raw)) {
    throw new Error('Skill resource path must be a non-empty relative path')
  }
  const target = resolve(root, raw)
  const rel = relative(root, target)
  if (rel === '..' || rel.startsWith(`..${sep}`) || isAbsolute(rel)) {
    throw new Error(`Skill resource path escapes the package: ${raw}`)
  }
  return { raw, target }
}

function positiveInteger(value, fallback, maximum, field) {
  const resolved = value === undefined ? fallback : Number(value)
  if (!Number.isInteger(resolved) || resolved < 1 || resolved > maximum) {
    throw new Error(`${field} must be an integer from 1 to ${maximum}`)
  }
  return resolved
}

export async function readSkillTextResource(rootPath, resourcePath, options = {}) {
  const root = await realpath(rootPath)
  const { raw, target } = containedPath(root, resourcePath)
  let canonical
  try {
    canonical = await realpath(target)
  } catch (error) {
    if (error?.code === 'ENOENT') throw new Error(`Skill resource does not exist: ${raw}`)
    throw error
  }
  containedPath(root, relative(root, canonical))
  const info = await stat(canonical)
  if (!info.isFile()) throw new Error(`Skill resource is not a file: ${raw}`)
  if (info.size > MAX_TEXT_BYTES) {
    throw new Error(`Skill resource exceeds the ${MAX_TEXT_BYTES}-byte text limit: ${raw}`)
  }

  const bytes = await readFile(canonical)
  let text
  try {
    text = new TextDecoder('utf-8', { fatal: true }).decode(bytes)
  } catch {
    throw new Error(`Skill resource is not valid UTF-8 text: ${raw}`)
  }
  const lines = text.split(/\r?\n/)
  const startLine = positiveInteger(options.startLine, 1, Math.max(lines.length, 1), 'start_line')
  const lineCount = positiveInteger(options.lineCount, DEFAULT_LINE_COUNT, MAX_LINE_COUNT, 'line_count')
  const selected = lines.slice(startLine - 1, startLine - 1 + lineCount)
  const endLine = startLine + selected.length - 1
  return {
    path: raw.replaceAll('\\', '/'),
    content: selected.join('\n'),
    startLine,
    endLine,
    totalLines: lines.length,
    truncated: endLine < lines.length,
  }
}
