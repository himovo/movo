import MarkdownIt from 'markdown-it'
import type { ArtifactItem } from './delivery'

const parser = new MarkdownIt({ html: false })

function identity(url: string): string {
  try {
    const value = new URL(url)
    return `${value.origin}${decodeURIComponent(value.pathname)}`
  } catch { return url }
}

export function inlineImageUrls(content: string): Set<string> {
  const urls = new Set<string>()
  for (const block of parser.parse(content, {})) {
    for (const token of block.children || []) {
      if (token.type === 'image') urls.add(identity(token.attrGet('src') || ''))
    }
  }
  return urls
}

export function imageIsInline(artifact: ArtifactItem, urls: Set<string>): boolean {
  return [artifact.url, artifact.signed_url].some(url => Boolean(url && urls.has(identity(url))))
}
