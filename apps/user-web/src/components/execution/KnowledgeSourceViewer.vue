<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { EvidenceBundleItem, EvidenceSourceItem } from '../../features/execution-v3/domain/delivery'
import { t } from '../../composables/i18n'
import NativeSourcePreview from './NativeSourcePreview.vue'
import {
  fetchKnowledgeSourceChunk,
  fetchKnowledgeSourceDocument,
  fetchKnowledgeSourcePreview,
  type KnowledgeSourceChunk,
  type KnowledgeSourceDocument,
} from '../../api/knowledgeSources'

let pdfjsLib: any = null
const pdfWorkerUrl = `${import.meta.env.BASE_URL}vendor/pdfjs/pdf.worker.min.mjs`

async function loadPdfjs() {
  if (!pdfjsLib) {
    pdfjsLib = await import('pdfjs-dist/legacy/build/pdf.mjs')
    pdfjsLib.GlobalWorkerOptions.workerSrc = pdfWorkerUrl
  }
  return pdfjsLib
}

const props = defineProps<{
  open: boolean
  bundle: EvidenceBundleItem | null
}>()

const emit = defineEmits<{
  (e: 'close'): void
}>()

const activeIndex = ref(0)
const loading = ref(false)
const errorText = ref('')
const documentMeta = ref<KnowledgeSourceDocument | null>(null)
const chunk = ref<KnowledgeSourceChunk | null>(null)
const pdfLayerRef = ref<HTMLDivElement | null>(null)
const pdfRendering = ref(false)
const pdfDocument = ref<any>(null)
const nativeContent = ref('')
const imageObjectUrl = ref('')
const previewUnavailable = ref(false)
const locatedPageNo = ref<number | null>(null)
let renderSeq = 0
let loadSeq = 0
const PDF_MIN_SCALE = 0.4
const PDF_MAX_INITIAL_SCALE = 1
const PDF_SOURCE_HORIZONTAL_PADDING = 38
const OFFICE_EMU_WIDESCREEN_WIDTH = 12192000
const OFFICE_EMU_STANDARD_WIDTH = 9144000
const OFFICE_EMU_SLIDE_HEIGHT = 6858000

const sources = computed(() => (props.bundle?.sources || []).filter((item) => item.document_id && item.chunk_id))
const activeSource = computed(() => sources.value[activeIndex.value] || null)
const pageNo = computed(() => {
  const raw = activeSource.value?.page_no ?? chunk.value?.pageNo
  const value = Number(raw || 0)
  return Number.isFinite(value) && value > 0 ? value : null
})
const displayPageNo = computed(() => locatedPageNo.value || pageNo.value)
const titleText = computed(() => (
  documentMeta.value ? documentDisplayName(documentMeta.value) : activeSource.value?.title || t('文档依据')
))
const sourceText = computed(() => chunk.value?.text || activeSource.value?.content || activeSource.value?.snippet || '')
const previewKind = computed(() => previewKindForDocument(documentMeta.value))
const highlightTargets = computed(() => {
  const type = String(chunk.value?.contentType || activeSource.value?.content_type || '').toLowerCase()
  if (type === 'table_row' || type.includes('table')) {
    return extractMarkdownTableCellTargets(sourceText.value)
  }
  return [sourceText.value]
})
const tableHighlightTargets = computed(() => highlightTargets.value.map(buildTableTarget).filter((item): item is TableTarget => Boolean(item)))

function previewKindForDocument(doc: KnowledgeSourceDocument | null): 'pdf' | 'markdown' | 'text' | 'html' | 'image' | 'unsupported' {
  if (!doc) return 'unsupported'
  const mime = String(doc.previewMimeType || doc.mimeType || '').toLowerCase()
  const ext = String(doc.fileExt || '').toLowerCase()
  if (mime.includes('pdf') || ext === 'pdf' || ['doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx'].includes(ext)) return 'pdf'
  if (mime.includes('markdown') || ['md', 'markdown'].includes(ext)) return 'markdown'
  if (mime.includes('html') || ['html', 'htm'].includes(ext)) return 'html'
  if (mime.startsWith('text/') || ['txt', 'csv', 'json', 'tsv', 'log'].includes(ext)) return 'text'
  if (mime.startsWith('image/') || ['png', 'jpg', 'jpeg', 'webp', 'gif'].includes(ext)) return 'image'
  return 'unsupported'
}

function sourceLocatorTitle(source: EvidenceSourceItem): string {
  return source.citation_id || (source.document_id && source.chunk_id ? `${source.document_id}:${source.chunk_id}` : source.chunk_id || '')
}

function documentDisplayName(doc: KnowledgeSourceDocument): string {
  const original = String(doc.originalFilename || '').trim()
  const base = original || String(doc.name || '').trim() || doc.id
  const ext = String(doc.fileExt || '').trim().replace(/^\./, '')
  if (!ext || new RegExp(`\\.${ext}$`, 'i').test(base)) return base
  return `${base}.${ext}`
}

function sourceExcerptPreview(source: EvidenceSourceItem): string {
  return String(source.snippet || source.content || '')
    .replace(/\s+/g, ' ')
    .trim()
}

function sourceKindText(source: EvidenceSourceItem): string {
  if (!source.chunk_id) return ''
  const type = String(source.content_type || '').toLowerCase()
  if (type === 'table_row') return t('evidence.table_row')
  if (type.includes('table')) return t('evidence.table')
  return t('evidence.document_fragment')
}

function destroyPdfDocument() {
  const current = pdfDocument.value
  pdfDocument.value = null
  if (!current) return
  try {
    const result = current.destroy?.()
    if (result && typeof result.catch === 'function') result.catch(() => {})
  } catch {
    // PDF.js may throw when rendering is cancelled by source switching.
  }
}

function clearPdfLayer() {
  renderSeq += 1
  destroyPdfDocument()
  if (pdfLayerRef.value) {
    pdfLayerRef.value.innerHTML = ''
  }
}

function revokeImageObjectUrl() {
  if (!imageObjectUrl.value) return
  URL.revokeObjectURL(imageObjectUrl.value)
  imageObjectUrl.value = ''
}

function selectSource(index: number) {
  if (index < 0 || index >= sources.value.length || index === activeIndex.value) return
  errorText.value = ''
  documentMeta.value = null
  chunk.value = null
  nativeContent.value = ''
  previewUnavailable.value = false
  locatedPageNo.value = null
  revokeImageObjectUrl()
  activeIndex.value = index
}

async function loadActiveSource() {
  const source = activeSource.value
  if (!props.open || !source?.document_id || !source?.chunk_id) return
  const currentLoadSeq = ++loadSeq
  loading.value = true
  errorText.value = ''
  documentMeta.value = null
  chunk.value = null
  nativeContent.value = ''
  previewUnavailable.value = false
  locatedPageNo.value = null
  revokeImageObjectUrl()
  clearPdfLayer()
  try {
    const token = localStorage.getItem('auth_token')
    const [doc, currentChunk] = await Promise.all([
      fetchKnowledgeSourceDocument(source.document_id, token),
      fetchKnowledgeSourceChunk(source.document_id, source.chunk_id, token),
    ])
    if (currentLoadSeq !== loadSeq) return
    documentMeta.value = doc
    chunk.value = currentChunk
    loading.value = false
    await nextTick()
    const kind = previewKindForDocument(doc)
    if (kind !== 'unsupported') {
      try {
        const blob = await fetchKnowledgeSourcePreview(source.document_id, token)
        if (currentLoadSeq !== loadSeq) return
        if (kind === 'pdf') {
          await renderPdf(blob)
        } else if (kind === 'image') {
          imageObjectUrl.value = URL.createObjectURL(blob)
        } else if (kind === 'markdown' || kind === 'text' || kind === 'html') {
          nativeContent.value = await blob.text()
          await nextTick()
        }
      } catch {
        previewUnavailable.value = true
      }
    }
  } catch (error: any) {
    if (currentLoadSeq !== loadSeq) return
    errorText.value = String(error?.message || error || t('evidence.load_failed'))
    documentMeta.value = null
    chunk.value = null
    nativeContent.value = ''
    previewUnavailable.value = false
    locatedPageNo.value = null
    revokeImageObjectUrl()
  } finally {
    if (currentLoadSeq === loadSeq) {
      loading.value = false
    }
  }
}

function normalizeText(value: string): string {
  return String(value || "")
    .replace(/\s+/g, "")
    .replace(/[|，。、“”‘’：；（）()《》<>【】\[\]{}.,:;'"`~!！?？—_\-·]/g, "")
    .toLowerCase()
}

function isMarkdownTableSeparator(line: string): boolean {
  const compact = line.replace(/[|\s:]/g, '')
  return compact.length > 0 && /^-+$/.test(compact)
}

function extractMarkdownTableBodyLines(value: string): string[] {
  const lines = String(value || '')
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
  const firstTableLine = lines.findIndex((line, index) => (
    line.includes('|') && index + 1 < lines.length && isMarkdownTableSeparator(lines[index + 1])
  ))
  if (firstTableLine < 0) return []
  return lines.slice(firstTableLine + 2).filter((line) => line.includes('|') && !isMarkdownTableSeparator(line))
}

function extractMarkdownTableCellTargets(value: string): string[] {
  const bodyLines = extractMarkdownTableBodyLines(value)
  const targets: string[] = []
  const seen = new Set<string>()
  for (const line of bodyLines) {
    const cells = line
      .split('|')
      .map((cell) => cell.trim())
      .filter(Boolean)
    for (const cell of cells) {
      const normalized = normalizeText(cell)
      if (!isUsefulTableCellTarget(normalized) || seen.has(normalized)) continue
      seen.add(normalized)
      targets.push(cell)
    }
  }
  return targets.length ? targets : [value]
}

function isUsefulTableCellTarget(normalized: string): boolean {
  if (!normalized) return false
  if (/[a-z0-9]/i.test(normalized)) return normalized.length >= 2
  return normalized.length >= 10
}

interface TextItemBox {
  item: any
  normalized: string
  start: number
  end: number
}

interface TextLineBox {
  normalized: string
  left: number
  top: number
  right: number
  bottom: number
  itemCount: number
}

interface SourceBBox {
  l: number
  t: number
  r: number
  b: number
  coordOrigin?: string
  pageNo?: number | string | null
}

interface TableContext {
  tableRef?: string
  rowIndex?: number | string | null
  rowOrdinal?: number | string | null
  headerRows?: number | string | null
  numRows?: number | string | null
  numCols?: number | string | null
}

interface TableTarget {
  raw: string
  normalized: string
  weight: number
  strong: boolean
  tokens: string[]
}

interface TableLineCandidate {
  pageWrapper: HTMLElement
  line: TextLineBox
  tableLines: TextLineBox[]
  score: number
  strongHits: number
  weakHits: number
  tokenHits: number
}

interface HighlightMatch {
  pageNumber: number
  kind: 'text' | 'bbox'
  count: number
}

function longestCommonSubstring(a: string, b: string, minReturnLength = 18): { start: number; length: number } {
  if (!a || !b) return { start: -1, length: 0 }
  const previous = new Array(b.length + 1).fill(0)
  const current = new Array(b.length + 1).fill(0)
  let bestLength = 0
  let bestEnd = 0
  for (let i = 1; i <= a.length; i += 1) {
    for (let j = 1; j <= b.length; j += 1) {
      if (a.charCodeAt(i - 1) === b.charCodeAt(j - 1)) {
        current[j] = previous[j - 1] + 1
        if (current[j] > bestLength) {
          bestLength = current[j]
          bestEnd = i
        }
      } else {
        current[j] = 0
      }
    }
    for (let j = 1; j <= b.length; j += 1) {
      previous[j] = current[j]
      current[j] = 0
    }
  }
  return bestLength >= minReturnLength ? { start: bestEnd - bestLength, length: bestLength } : { start: -1, length: 0 }
}

function itemRangeFromMatch(items: TextItemBox[], matchStart: number, matchLength: number): TextItemBox[] {
  if (matchStart < 0 || matchLength <= 0) return []
  const matchEnd = matchStart + matchLength
  return items.filter((item) => item.end > matchStart && item.start < matchEnd)
}

function containsCjk(value: string): boolean {
  return /[\u3400-\u9fff]/.test(value)
}

function isMatchedTextLine(normalized: string, target: string, tableMode = false): boolean {
  if (!normalized || !target) return false
  if (tableMode) {
    const minTokenLength = containsCjk(normalized) ? 3 : 3
    if (normalized.length >= minTokenLength && target.includes(normalized)) return true
    if (target.length >= minTokenLength && normalized.includes(target)) return true
    const tableMatch = longestCommonSubstring(normalized, target, containsCjk(normalized + target) ? 6 : 4)
    if (tableMatch.length > 0) {
      const baseLength = Math.min(normalized.length, target.length)
      const minRatio = containsCjk(normalized + target) ? 0.42 : 0.5
      return baseLength > 0 && tableMatch.length / baseLength >= minRatio
    }
  }
  const minLength = containsCjk(normalized) ? 4 : 8
  if (normalized.length < minLength) return false
  if (target.includes(normalized)) return true
  const match = longestCommonSubstring(normalized, target)
  const minMatchLength = containsCjk(normalized) ? 4 : 10
  return match.length >= minMatchLength && match.length / normalized.length >= 0.58
}

function isMatchedTextLineAny(normalized: string, targets: string[], tableMode: boolean): boolean {
  return targets.some((target) => isMatchedTextLine(normalized, target, tableMode))
}

function getTextItemBox(viewport: any, item: any): TextLineBox | null {
  const normalized = normalizeText(String(item?.str || ''))
  if (!normalized) return null
  const transform = pdfjsLib.Util.transform(viewport.transform, item.transform)
  const x = transform[4]
  const fontHeight = Math.hypot(transform[2], transform[3]) || Math.abs(transform[3]) || 12
  const y = transform[5] - fontHeight
  const width = Math.max(10, Number(item.width || String(item?.str || '').length * 8) * viewport.scale)
  const height = Math.max(10, fontHeight * 1.2)
  return {
    normalized,
    left: x,
    top: y,
    right: x + width,
    bottom: y + height,
    itemCount: 1,
  }
}

function buildTextLines(rawItems: any[], viewport: any): TextLineBox[] {
  const boxes = rawItems
    .map((item) => getTextItemBox(viewport, item))
    .filter((item): item is NonNullable<ReturnType<typeof getTextItemBox>> => Boolean(item))
    .sort((a, b) => (a.top === b.top ? a.left - b.left : a.top - b.top))
  const lines: TextLineBox[] = []
  const lineThreshold = 8
  for (const box of boxes) {
    const existing = lines.find((line) => Math.abs(line.top - box.top) <= lineThreshold)
    if (!existing) {
      lines.push(box)
      continue
    }
    existing.normalized += box.normalized
    existing.left = Math.min(existing.left, box.left)
    existing.top = Math.min(existing.top, box.top)
    existing.right = Math.max(existing.right, box.right)
    existing.bottom = Math.max(existing.bottom, box.bottom)
    existing.itemCount += 1
  }
  return lines
}

function drawLineHighlight(pageWrapper: HTMLElement, highlightLayer: HTMLElement, line: TextLineBox): void {
  const node = document.createElement('div')
  node.className = 'source-highlight'
  node.style.left = `${line.left}px`
  node.style.top = `${line.top}px`
  node.style.width = `${Math.max(10, line.right - line.left)}px`
  node.style.height = `${Math.max(10, line.bottom - line.top)}px`
  highlightLayer.appendChild(node)
  pageWrapper.classList.add('has-source-highlight')
}

function drawTableRowHighlight(pageWrapper: HTMLElement, highlightLayer: HTMLElement, line: TextLineBox, tableLines: TextLineBox[]): void {
  const tableLeft = tableLines.length ? Math.min(...tableLines.map((item) => item.left)) : line.left
  const tableRight = tableLines.length ? Math.max(...tableLines.map((item) => item.right)) : line.right
  const nearbyLines = tableLines.filter((item) => {
    const verticalGap = Math.max(item.top - line.bottom, line.top - item.bottom, 0)
    return verticalGap <= 6 && item.right >= tableLeft && item.left <= tableRight
  })
  const rowLines = nearbyLines.length ? nearbyLines : [line]
  const top = Math.min(...rowLines.map((item) => item.top))
  const bottom = Math.max(...rowLines.map((item) => item.bottom))
  const node = document.createElement('div')
  node.className = 'source-highlight source-highlight-table-row'
  node.style.left = `${tableLeft}px`
  node.style.top = `${top}px`
  node.style.width = `${Math.max(10, tableRight - tableLeft)}px`
  node.style.height = `${Math.max(12, bottom - top)}px`
  highlightLayer.appendChild(node)
  pageWrapper.classList.add('has-source-highlight')
}

function sourceAnchors(): Record<string, any>[] {
  const anchors: Record<string, any>[] = []
  const sourceAnchor = activeSource.value?.source_anchor
  if (sourceAnchor && typeof sourceAnchor === 'object') anchors.push(sourceAnchor)
  const metadata = chunk.value?.metadata || {}
  for (const key of ['sourceAnchor', 'anchor', 'pageBbox', 'boundingBox', 'bbox']) {
    const value = (metadata as any)[key]
    if (value && typeof value === 'object') {
      anchors.push(key === 'bbox' || key === 'boundingBox' || key === 'pageBbox' ? { [key]: value } : value)
    }
  }
  return anchors
}

function sourceTableContext(): TableContext | null {
  const metadata = chunk.value?.metadata || {}
  if (metadata && typeof metadata === 'object' && (metadata as any).tableContext) {
    return (metadata as any).tableContext as TableContext
  }
  for (const anchor of sourceAnchors()) {
    if (anchor.tableContext && typeof anchor.tableContext === 'object') {
      return anchor.tableContext as TableContext
    }
  }
  return null
}

function anchorBboxesForPage(pageNumber: number): SourceBBox[] {
  const output: SourceBBox[] = []
  for (const anchor of sourceAnchors()) {
    const anchorPage = normalizePageNo(anchor.pageNo ?? anchor.page_no ?? pageNo.value)
    const rawBboxes = Array.isArray(anchor.bboxes)
      ? anchor.bboxes
      : [anchor.bbox, anchor.boundingBox, anchor.pageBbox].filter(Boolean)
    for (const raw of rawBboxes) {
      const bbox = normalizeSourceBBox(raw)
      if (!bbox) continue
      const bboxPage = normalizePageNo(bbox.pageNo ?? (raw as any)?.page_no ?? anchorPage)
      if (bboxPage && bboxPage !== pageNumber) continue
      if (!bboxPage && anchorPage && anchorPage !== pageNumber) continue
      output.push(bbox)
    }
  }
  return output
}

function normalizePageNo(value: unknown): number | null {
  const page = Number(value || 0)
  return Number.isFinite(page) && page > 0 ? page : null
}

function normalizeSourceBBox(raw: any): SourceBBox | null {
  if (!raw || typeof raw !== 'object') return null
  const left = Number(raw.l ?? raw.left ?? raw.x)
  const top = Number(raw.t ?? raw.top ?? raw.y)
  const right = Number(raw.r ?? raw.right ?? (Number.isFinite(left) ? left + Number(raw.w ?? raw.width) : NaN))
  const bottom = Number(raw.b ?? raw.bottom ?? (Number.isFinite(top) ? top + Number(raw.h ?? raw.height) : NaN))
  if (![left, top, right, bottom].every(Number.isFinite)) return null
  if (right <= left || bottom === top) return null
  return {
    l: left,
    t: top,
    r: right,
    b: bottom,
    coordOrigin: String(raw.coordOrigin || raw.coord_origin || 'TOPLEFT').toUpperCase(),
    pageNo: raw.pageNo ?? raw.page_no ?? null,
  }
}

function drawBBoxHighlight(pageWrapper: HTMLElement, highlightLayer: HTMLElement, viewport: any, bbox: SourceBBox): boolean {
  const scale = Number(viewport?.scale || 1)
  const pageWidth = Number(viewport?.width || 0) / scale
  const pageHeight = Number(viewport?.height || 0) / scale
  if (!pageWidth || !pageHeight) return false

  const isNormalized = Math.max(Math.abs(bbox.l), Math.abs(bbox.t), Math.abs(bbox.r), Math.abs(bbox.b)) <= 1.5
  const coordinateSize = sourceCoordinateSizeForBBox(bbox, pageWidth, pageHeight)
  const widthFactor = isNormalized ? pageWidth : coordinateSize ? pageWidth / coordinateSize.width : 1
  const heightFactor = isNormalized ? pageHeight : coordinateSize ? pageHeight / coordinateSize.height : 1
  const left = clamp(bbox.l * widthFactor, 0, pageWidth)
  const right = clamp(bbox.r * widthFactor, 0, pageWidth)
  const topValue = clamp(bbox.t * heightFactor, 0, pageHeight)
  const bottomValue = clamp(bbox.b * heightFactor, 0, pageHeight)
  const origin = String(bbox.coordOrigin || 'TOPLEFT').toUpperCase()
  const top = origin.includes('BOTTOM')
    ? (pageHeight - Math.max(topValue, bottomValue))
    : Math.min(topValue, bottomValue)
  const width = Math.max(6, (right - left) * scale)
  const height = Math.max(6, Math.abs(bottomValue - topValue) * scale)
  if (!Number.isFinite(left) || !Number.isFinite(top) || width <= 0 || height <= 0) return false

  const node = document.createElement('div')
  node.className = 'source-highlight'
  node.style.left = `${left * scale}px`
  node.style.top = `${top * scale}px`
  node.style.width = `${width}px`
  node.style.height = `${height}px`
  highlightLayer.appendChild(node)
  pageWrapper.classList.add('has-source-highlight')
  return true
}

function clamp(value: number, min: number, max: number): number {
  if (!Number.isFinite(value)) return min
  return Math.min(max, Math.max(min, value))
}

function sourceCoordinateSizeForBBox(bbox: SourceBBox, pageWidth: number, pageHeight: number): { width: number; height: number } | null {
  const maxX = Math.max(Math.abs(bbox.l), Math.abs(bbox.r))
  const maxY = Math.max(Math.abs(bbox.t), Math.abs(bbox.b))
  if (maxX <= pageWidth * 4 && maxY <= pageHeight * 4) return null

  const anchor = sourceAnchors().find((item) => item && typeof item === 'object' && (
    item.pageWidth || item.page_width || item.width || item.pageHeight || item.page_height || item.height
  ))
  const anchorWidth = Number(anchor?.pageWidth ?? anchor?.page_width ?? anchor?.width)
  const anchorHeight = Number(anchor?.pageHeight ?? anchor?.page_height ?? anchor?.height)
  if (Number.isFinite(anchorWidth) && anchorWidth > 0 && Number.isFinite(anchorHeight) && anchorHeight > 0) {
    return { width: anchorWidth, height: anchorHeight }
  }

  // Office/PPT extraction commonly reports slide bboxes in EMU units.
  // A widescreen slide is 12192000 x 6858000 EMU; a 4:3 slide is
  // 9144000 x 6858000 EMU. Scale those into the rendered PDF page.
  if (maxX > 100000 || maxY > 100000) {
    const width = maxX <= OFFICE_EMU_STANDARD_WIDTH * 1.08
      ? OFFICE_EMU_STANDARD_WIDTH
      : OFFICE_EMU_WIDESCREEN_WIDTH
    const height = Math.max(OFFICE_EMU_SLIDE_HEIGHT, maxY)
    return { width, height }
  }
  return null
}

function mergeRowBboxes(bboxes: SourceBBox[]): SourceBBox | null {
  if (!bboxes.length) return null
  const origin = String(bboxes[0].coordOrigin || 'TOPLEFT').toUpperCase()
  if (!bboxes.every((bbox) => String(bbox.coordOrigin || 'TOPLEFT').toUpperCase() === origin)) return null
  return {
    l: Math.min(...bboxes.map((bbox) => bbox.l)),
    t: Math.min(...bboxes.map((bbox) => bbox.t)),
    r: Math.max(...bboxes.map((bbox) => bbox.r)),
    b: Math.max(...bboxes.map((bbox) => bbox.b)),
    coordOrigin: origin,
    pageNo: bboxes[0].pageNo,
  }
}

function highlightSourceBboxes(pageWrapper: HTMLElement, viewport: any, pageNumber: number, tableMode: boolean): number {
  const bboxes = anchorBboxesForPage(pageNumber)
  if (!bboxes.length) return 0
  const highlightLayer = document.createElement('div')
  highlightLayer.className = 'pdf-highlight-layer'
  pageWrapper.appendChild(highlightLayer)
  let highlighted = 0
  const rowBBox = tableMode ? mergeRowBboxes(bboxes) : null
  if (rowBBox && drawBBoxHighlight(pageWrapper, highlightLayer, viewport, rowBBox)) {
    highlighted = 1
  } else {
    for (const bbox of bboxes) {
      if (drawBBoxHighlight(pageWrapper, highlightLayer, viewport, bbox)) highlighted += 1
    }
  }
  if (highlighted === 0) highlightLayer.remove()
  return highlighted
}

function numericTableValue(value: unknown): number | null {
  const numberValue = Number(value)
  return Number.isFinite(numberValue) && numberValue >= 0 ? numberValue : null
}

function buildTableTarget(raw: string): TableTarget | null {
  const normalized = normalizeText(raw)
  if (!normalized) return null
  const hasNumber = /\d/.test(normalized)
  const strong = normalized.length >= 6 || hasNumber
  const weight = normalized.length >= 14 ? 4 : normalized.length >= 8 ? 3 : normalized.length >= 4 ? 2 : 1
  return {
    raw,
    normalized,
    weight,
    strong,
    tokens: tableTargetTokens(normalized),
  }
}

function tableTargetTokens(normalized: string): string[] {
  const tokens = new Set<string>()
  for (const match of normalized.matchAll(/\d+(?:\.\d+)?(?:天|年|月|日|个|次|%|元)?/g)) {
    if (match[0].length >= 2) tokens.add(match[0])
  }
  if (normalized.length <= 4) {
    tokens.add(normalized)
  } else {
    const cjk = containsCjk(normalized)
    const size = cjk ? 3 : 4
    for (let i = 0; i <= normalized.length - size; i += Math.max(1, size - 1)) {
      const token = normalized.slice(i, i + size)
      if (token.length >= size) tokens.add(token)
    }
  }
  return Array.from(tokens).filter((token) => token.length >= 2)
}

function tableTargetMatchScore(lineText: string, target: TableTarget): { score: number; strongHit: boolean; weakHit: boolean; tokenHits: number } {
  let score = 0
  let strongHit = false
  let weakHit = false
  let tokenHits = 0

  if (lineText.includes(target.normalized)) {
    score += target.weight * 4
    if (target.strong) strongHit = true
    else weakHit = true
  } else if (target.normalized.includes(lineText) && lineText.length >= 8) {
    score += target.weight * 1.5
    if (target.strong) strongHit = true
  }

  const minLcsLength = target.normalized.length <= 4 ? 2 : containsCjk(target.normalized + lineText) ? 4 : 5
  const match = longestCommonSubstring(lineText, target.normalized, minLcsLength)
  if (match.length > 0) {
    const ratio = match.length / Math.max(target.normalized.length, 1)
    if (ratio >= 0.72 || (target.strong && match.length >= 8)) {
      score += target.weight * 2.5 * Math.min(1, ratio)
      if (target.strong) strongHit = true
      else weakHit = true
    } else if (ratio >= 0.45 && target.strong) {
      score += target.weight * ratio
    }
  }

  for (const token of target.tokens) {
    if (!lineText.includes(token)) continue
    tokenHits += 1
    score += token.length <= 3 ? 0.6 : 1
  }

  return { score, strongHit, weakHit, tokenHits }
}

function scoreTableLine(line: TextLineBox, targets: TableTarget[]): Omit<TableLineCandidate, 'pageWrapper' | 'line' | 'tableLines'> {
  let score = 0
  let strongHits = 0
  let weakHits = 0
  let tokenHits = 0
  for (const target of targets) {
    const result = tableTargetMatchScore(line.normalized, target)
    score += result.score
    if (result.strongHit) strongHits += 1
    if (result.weakHit) weakHits += 1
    tokenHits += result.tokenHits
  }
  return { score, strongHits, weakHits, tokenHits }
}

function isAcceptableTableCandidate(candidate: Pick<TableLineCandidate, 'score' | 'strongHits' | 'weakHits' | 'tokenHits'>): boolean {
  if (candidate.strongHits >= 1 && candidate.score >= 5) return true
  if (candidate.strongHits >= 1 && candidate.tokenHits >= 2 && candidate.score >= 4) return true
  if (candidate.weakHits >= 2 && candidate.tokenHits >= 3 && candidate.score >= 5) return true
  return false
}

function collectTableRowCandidates(pageWrapper: HTMLElement, viewport: any, textContent: any, targets: TableTarget[]): TableLineCandidate[] {
  const context = sourceTableContext()
  if (!targets.length) return []
  const rawItems = Array.isArray(textContent?.items) ? textContent.items : []
  const lines = buildTextLines(rawItems, viewport)
  if (!lines.length) return []

  const numCols = numericTableValue(context?.numCols)
  const minItems = Math.max(2, Math.min(4, numCols || 2))
  const tableLikeLines = lines.filter((line) => line.itemCount >= minItems || (numCols !== null && line.itemCount >= Math.min(2, numCols)))
  const rowExtentLines = tableLikeLines.length ? tableLikeLines : lines
  return lines
    .map((line) => ({
      pageWrapper,
      line,
      tableLines: rowExtentLines,
      ...scoreTableLine(line, targets),
    }))
    .filter(isAcceptableTableCandidate)
}

function bestTableCandidate(candidates: TableLineCandidate[]): TableLineCandidate | null {
  if (!candidates.length) return null
  const sorted = [...candidates].sort((a, b) => (
    b.score - a.score
    || b.strongHits - a.strongHits
    || b.tokenHits - a.tokenHits
    || b.line.normalized.length - a.line.normalized.length
  ))
  const best = sorted[0]
  const second = sorted[1]
  if (second && best.score < second.score * 1.08 && best.strongHits <= second.strongHits) {
    return null
  }
  return best
}

function drawTableCandidate(candidate: TableLineCandidate): number {
  const highlightLayer = document.createElement('div')
  highlightLayer.className = 'pdf-highlight-layer'
  candidate.pageWrapper.appendChild(highlightLayer)
  drawTableRowHighlight(candidate.pageWrapper, highlightLayer, candidate.line, candidate.tableLines)
  return 1
}

function highlightTextItems(pageWrapper: HTMLElement, viewport: any, textContent: any, targets: string[], tableMode: boolean): number {
  if (!targets.length) return 0
  const highlightLayer = document.createElement('div')
  highlightLayer.className = 'pdf-highlight-layer'
  pageWrapper.appendChild(highlightLayer)
  const rawItems = Array.isArray(textContent?.items) ? textContent.items : []
  const lines = buildTextLines(rawItems, viewport)
  const matchedLines = lines.filter((line) => isMatchedTextLineAny(line.normalized, targets, tableMode))
  if (matchedLines.length > 0) {
    for (const line of matchedLines) {
      drawLineHighlight(pageWrapper, highlightLayer, line)
    }
    return matchedLines.length
  }

  const items: TextItemBox[] = []
  let pageText = ''
  for (const item of rawItems) {
    const normalized = normalizeText(String(item?.str || ''))
    if (!normalized) continue
    const start = pageText.length
    pageText += normalized
    items.push({ item, normalized, start, end: pageText.length })
  }
  const fallbackTarget = targets.join('')
  const match = longestCommonSubstring(pageText, fallbackTarget)
  const matchedItems = itemRangeFromMatch(items, match.start, match.length)
  let highlighted = 0
  for (const boxed of matchedItems) {
    const box = getTextItemBox(viewport, boxed.item)
    if (!box) continue
    drawLineHighlight(pageWrapper, highlightLayer, box)
    highlighted += 1
  }
  return highlighted
}

function selectBestHighlightMatch(matches: HighlightMatch[], explicitPageNo: number | null): HighlightMatch | null {
  if (!matches.length) return null
  const distance = (pageNumber: number) => explicitPageNo ? Math.abs(pageNumber - explicitPageNo) : pageNumber
  return [...matches].sort((a, b) => {
    const kindDiff = (a.kind === 'text' ? 0 : 1) - (b.kind === 'text' ? 0 : 1)
    if (kindDiff !== 0) return kindDiff
    if (b.count !== a.count) return b.count - a.count
    return distance(a.pageNumber) - distance(b.pageNumber)
  })[0]
}

function removeSourceHighlightsExcept(root: ParentNode, selectedPageNumber: number): void {
  root.querySelectorAll<HTMLElement>('.pdf-source-page').forEach((pageNode) => {
    const pageNumber = Number(pageNode.dataset.pageNumber || 0)
    if (pageNumber === selectedPageNumber) return
    pageNode.classList.remove('has-source-highlight')
    pageNode.querySelectorAll('.pdf-highlight-layer').forEach((layer) => layer.remove())
  })
}

function createPageRenderOrder(totalPages: number, explicitPageNo: number | null): number[] {
  const priority = explicitPageNo
    ? [explicitPageNo, explicitPageNo - 1, explicitPageNo + 1, explicitPageNo - 2, explicitPageNo + 2]
    : [1, 2, 3]
  const seen = new Set<number>()
  const output: number[] = []
  const add = (pageNumber: number) => {
    if (!Number.isFinite(pageNumber) || pageNumber < 1 || pageNumber > totalPages || seen.has(pageNumber)) return
    seen.add(pageNumber)
    output.push(pageNumber)
  }
  priority.forEach(add)
  for (let pageNumber = 1; pageNumber <= totalPages; pageNumber += 1) add(pageNumber)
  return output
}

function nextAnimationFrame(): Promise<void> {
  return new Promise((resolve) => window.requestAnimationFrame(() => resolve()))
}

function scrollToTargetPage() {
  const host = pdfLayerRef.value
  if (!host) return
  const preferredPage = locatedPageNo.value || pageNo.value
  const targetPage = preferredPage
    ? host.querySelector<HTMLElement>(`[data-page-number="${preferredPage}"].has-source-highlight`)
      || host.querySelector<HTMLElement>(`[data-page-number="${preferredPage}"]`)
    : null
  const target = targetPage?.querySelector<HTMLElement>('.source-highlight')
    || host.querySelector<HTMLElement>('.source-highlight')
    || targetPage
    || host.querySelector<HTMLElement>('.has-source-highlight')
  if (!target) return
  const scroller = host.parentElement
  if (scroller) {
    const scrollerRect = scroller.getBoundingClientRect()
    const targetRect = target.getBoundingClientRect()
    scroller.scrollTo({
      top: Math.max(0, scroller.scrollTop + targetRect.top - scrollerRect.top - 60),
      behavior: 'smooth',
    })
    return
  }
  target.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

async function renderPdf(blob: Blob) {
  const host = pdfLayerRef.value
  if (!host) return
  const currentSeq = ++renderSeq
  pdfRendering.value = true
  host.innerHTML = ''
  destroyPdfDocument()
  const highlightType = String(chunk.value?.contentType || activeSource.value?.content_type || '').toLowerCase()
  const tableHighlightMode = highlightType === 'table_row' || highlightType.includes('table')
  const targetTexts = highlightTargets.value.map((target) => normalizeText(target)).filter(Boolean)
  try {
    const pdfjs = await loadPdfjs()
    const buffer = await blob.arrayBuffer()
    const task = pdfjs.getDocument({ data: buffer })
    const pdf = await task.promise
    if (currentSeq !== renderSeq) {
      await pdf.destroy()
      return
    }
    pdfDocument.value = pdf
    const explicitPageNo = pageNo.value
    const firstPage = await pdf.getPage(1)
    const baseViewport = firstPage.getViewport({ scale: 1 })
    const availableWidth = Math.max(160, host.clientWidth - PDF_SOURCE_HORIZONTAL_PADDING)
    const pdfScale = Math.min(
      PDF_MAX_INITIAL_SCALE,
      Math.max(PDF_MIN_SCALE, availableWidth / baseViewport.width),
    )
    const estimatedViewport = firstPage.getViewport({ scale: pdfScale })
    const wrappers = new Map<number, HTMLElement>()
    const fragment = document.createDocumentFragment()
    for (let pageNumber = 1; pageNumber <= pdf.numPages; pageNumber += 1) {
      const wrapper = document.createElement('article')
      wrapper.className = 'pdf-source-page pdf-source-page-pending'
      wrapper.dataset.pageNumber = String(pageNumber)
      wrapper.style.width = `${estimatedViewport.width}px`
      wrapper.style.height = `${estimatedViewport.height}px`
      fragment.appendChild(wrapper)
      wrappers.set(pageNumber, wrapper)
    }
    host.innerHTML = ''
    host.appendChild(fragment)
    await nextTick()

    const tableCandidates: TableLineCandidate[] = []
    const highlightMatches: HighlightMatch[] = []
    const tableTargets = tableHighlightTargets.value
    let selectedHighlightPage = 0
    const renderedPages = new Set<number>()
    const shouldCheckPageForHighlight = (pageNumber: number) => {
      if (selectedHighlightPage) return pageNumber === selectedHighlightPage
      if (tableHighlightMode) return true
      if (explicitPageNo) {
        return pageNumber >= Math.max(1, explicitPageNo - 2) && pageNumber <= Math.min(pdf.numPages, explicitPageNo + 2)
      }
      if (!highlightMatches.length) return true
      const firstMatchPage = highlightMatches[0]?.pageNumber || 0
      return pageNumber <= Math.min(pdf.numPages, firstMatchPage + 2)
    }
    const renderPage = async (pageNumber: number, allowHighlight: boolean): Promise<void> => {
      if (currentSeq !== renderSeq) return
      if (renderedPages.has(pageNumber)) return
      const wrapper = wrappers.get(pageNumber)
      if (!wrapper) return
      renderedPages.add(pageNumber)
      const page = pageNumber === 1 ? firstPage : await pdf.getPage(pageNumber)
      const viewport = page.getViewport({ scale: pdfScale })
      wrapper.classList.remove('pdf-source-page-pending')
      wrapper.innerHTML = ''
      wrapper.style.width = `${viewport.width}px`
      wrapper.style.height = `${viewport.height}px`
      const canvas = document.createElement('canvas')
      const context = canvas.getContext('2d')
      const outputScale = window.devicePixelRatio || 1
      canvas.width = Math.floor(viewport.width * outputScale)
      canvas.height = Math.floor(viewport.height * outputScale)
      canvas.style.width = `${Math.floor(viewport.width)}px`
      canvas.style.height = `${Math.floor(viewport.height)}px`
      wrapper.appendChild(canvas)
      if (context) {
        await page.render({
          canvas,
          canvasContext: context,
          viewport,
          transform: outputScale !== 1 ? [outputScale, 0, 0, outputScale, 0, 0] : undefined,
        }).promise
      }
      if (allowHighlight && shouldCheckPageForHighlight(pageNumber)) {
        if (tableHighlightMode) {
          const textContent = await page.getTextContent()
          tableCandidates.push(...collectTableRowCandidates(wrapper, viewport, textContent, tableTargets))
        } else {
          let highlighted = 0
          let highlightKind: HighlightMatch['kind'] = 'text'
          if (targetTexts.length > 0) {
            const textContent = await page.getTextContent()
            highlighted = highlightTextItems(wrapper, viewport, textContent, targetTexts, false)
          }
          if (highlighted === 0) {
            highlighted = highlightSourceBboxes(wrapper, viewport, pageNumber, false)
            highlightKind = 'bbox'
          }
          if (highlighted > 0) {
            highlightMatches.push({ pageNumber, kind: highlightKind, count: highlighted })
          }
        }
      }
    }

    const order = createPageRenderOrder(pdf.numPages, explicitPageNo)
    const priorityCount = explicitPageNo ? Math.min(5, order.length) : Math.min(3, order.length)
    const priorityPages = order.slice(0, priorityCount)
    const remainingPages = order.slice(priorityCount)
    for (const pageNumber of priorityPages) {
      await renderPage(pageNumber, true)
    }

    if (tableHighlightMode) {
      const candidate = bestTableCandidate(tableCandidates)
      if (candidate) {
        drawTableCandidate(candidate)
        selectedHighlightPage = Number(candidate.pageWrapper.dataset.pageNumber || 0) || 0
      }
    } else {
      const selectedHighlight = selectBestHighlightMatch(highlightMatches, explicitPageNo)
      if (selectedHighlight) {
        selectedHighlightPage = selectedHighlight.pageNumber
        removeSourceHighlightsExcept(host, selectedHighlight.pageNumber)
      }
    }
    locatedPageNo.value = selectedHighlightPage || null
    await nextTick()
    scrollToTargetPage()
    window.requestAnimationFrame(() => {
      window.requestAnimationFrame(scrollToTargetPage)
    })
    pdfRendering.value = false

    void (async () => {
      for (const pageNumber of remainingPages) {
        if (currentSeq !== renderSeq) return
        await nextAnimationFrame()
        await renderPage(pageNumber, !selectedHighlightPage)
        if (!selectedHighlightPage) {
          if (tableHighlightMode) {
            const candidate = bestTableCandidate(tableCandidates)
            if (candidate) {
              selectedHighlightPage = Number(candidate.pageWrapper.dataset.pageNumber || 0) || 0
              locatedPageNo.value = selectedHighlightPage || null
              removeSourceHighlightsExcept(host, selectedHighlightPage)
              scrollToTargetPage()
            }
          } else {
            const selectedHighlight = selectBestHighlightMatch(highlightMatches, explicitPageNo)
            if (selectedHighlight) {
              selectedHighlightPage = selectedHighlight.pageNumber
              locatedPageNo.value = selectedHighlight.pageNumber
              removeSourceHighlightsExcept(host, selectedHighlight.pageNumber)
              scrollToTargetPage()
            }
          }
        }
      }
    })()
  } catch (error: any) {
    errorText.value = String(error?.message || error || t('evidence.load_failed'))
  } finally {
    if (currentSeq === renderSeq) {
      pdfRendering.value = false
    }
  }
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape' && props.open) emit('close')
}

watch(
  () => props.open,
  (open) => {
    if (open) {
      activeIndex.value = 0
      void loadActiveSource()
    } else {
      locatedPageNo.value = null
      clearPdfLayer()
      revokeImageObjectUrl()
    }
  },
)

watch(activeIndex, () => {
  void loadActiveSource()
})

watch(
  () => props.bundle?.id,
  () => {
    locatedPageNo.value = null
    if (props.open) {
      activeIndex.value = 0
      void loadActiveSource()
    }
  },
)

onMounted(() => window.addEventListener('keydown', onKeydown))
onBeforeUnmount(() => {
  clearPdfLayer()
  revokeImageObjectUrl()
  window.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <Teleport to="body">
    <div v-if="open && bundle" class="fixed inset-0 z-50 bg-slate-950/30 p-4">
      <section class="mx-auto flex h-full max-w-[min(1480px,96vw)] flex-col overflow-hidden rounded-xl bg-white shadow-2xl">
        <header class="flex items-center justify-between gap-4 border-b border-slate-200 px-5 py-4">
          <div class="min-w-0">
            <div class="text-base font-semibold text-slate-950">{{ t('evidence.drawer_title') }}</div>
            <div class="mt-1 truncate text-sm text-slate-500">
              {{ titleText }}
              <span v-if="displayPageNo"> · {{ t('evidence.page_no', { page: displayPageNo }) }}</span>
            </div>
          </div>
          <button
            type="button"
            class="flex h-10 w-10 items-center justify-center rounded-full text-slate-500 hover:bg-slate-100 hover:text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500"
            :aria-label="t('ui.close')"
            @click="emit('close')"
          >
            <svg viewBox="0 0 24 24" class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
              <path d="M18 6 6 18"></path>
              <path d="m6 6 12 12"></path>
            </svg>
          </button>
        </header>

        <div class="grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)_420px] bg-slate-50">
          <main class="min-h-0 border-r border-slate-200 p-4">
            <div class="h-full overflow-hidden rounded-lg border border-slate-200 bg-white">
              <div v-if="errorText" class="flex h-full items-center justify-center p-8 text-center text-sm text-rose-600">
                {{ errorText }}
              </div>
              <div v-else class="relative h-full overflow-auto bg-slate-100">
                <div v-if="previewUnavailable" class="flex h-full items-center justify-center p-8 text-center text-sm text-slate-500">
                  {{ t('evidence.no_preview') }}
                </div>
                <div v-else-if="previewKind === 'pdf'" ref="pdfLayerRef" class="pdf-source-layer"></div>
                <div v-else-if="previewKind === 'image' && imageObjectUrl" class="h-full p-4">
                  <img
                    :src="imageObjectUrl"
                    :alt="titleText"
                    class="block h-full w-full object-contain"
                  />
                </div>
                <NativeSourcePreview
                  v-else-if="previewKind === 'markdown' || previewKind === 'text' || previewKind === 'html'"
                  :kind="previewKind"
                  :content="nativeContent"
                  :highlight-texts="highlightTargets"
                />
                <div v-else-if="documentMeta" class="flex h-full items-center justify-center p-8 text-center text-sm text-slate-500">
                  {{ t('evidence.no_preview') }}
                </div>
                <div v-if="loading || pdfRendering" class="absolute left-1/2 top-6 -translate-x-1/2 rounded-full bg-white px-3 py-1 text-xs font-medium text-slate-500 shadow">
                  {{ t('ui.loading') }}
                </div>
              </div>
              <div v-if="!loading && !errorText && !pdfRendering && !documentMeta" class="flex h-full items-center justify-center text-sm text-slate-500">
                {{ t('evidence.no_preview') }}
              </div>
            </div>
          </main>

          <aside class="min-h-0 overflow-y-auto bg-white p-4">
            <div class="mb-3 text-sm font-semibold text-slate-950">
              {{ t('evidence.fragment_list') }} · {{ sources.length }}
            </div>
            <div class="space-y-2">
              <button
                v-for="(source, idx) in sources"
                :key="`${source.document_id}:${source.chunk_id}:${idx}`"
                type="button"
                class="w-full rounded-lg border p-3 text-left transition"
                :class="idx === activeIndex ? 'border-blue-300 bg-blue-50 shadow-sm' : 'border-slate-200 bg-white hover:border-blue-200 hover:bg-slate-50'"
                @click="selectSource(idx)"
              >
                <div class="flex items-center justify-between gap-3">
                  <div class="flex min-w-0 items-center gap-2 text-sm font-semibold text-slate-900">
                    <svg class="h-4 w-4 shrink-0 text-blue-600" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                      <path d="M7 3h7l4 4v14H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z" fill="currentColor" opacity="0.12"></path>
                      <path d="M14 3v5h5" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"></path>
                      <path d="M7 3h7l5 5v11a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"></path>
                      <path d="M8.5 13h7M8.5 16h5" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"></path>
                    </svg>
                    <span class="truncate">{{ t('evidence.fragment_number', { index: idx + 1 }) }}</span>
                  </div>
                  <div class="shrink-0 text-xs font-bold text-blue-600">#{{ idx + 1 }}</div>
                </div>
                <div class="mt-2 flex flex-wrap gap-2 text-xs text-slate-500">
                  <span v-if="source.page_no" class="rounded-full bg-slate-100 px-2 py-1">{{ t('evidence.page_no', { page: source.page_no }) }}</span>
                  <span
                    v-if="sourceKindText(source)"
                    class="rounded-full bg-slate-100 px-2 py-1"
                    :title="sourceLocatorTitle(source)"
                  >{{ sourceKindText(source) }}</span>
                </div>
                <p
                  v-if="sourceExcerptPreview(source)"
                  class="mt-2 max-h-10 overflow-hidden text-xs leading-5 text-slate-500"
                >
                  {{ sourceExcerptPreview(source) }}
                </p>
              </button>
            </div>

            <section class="mt-4 rounded-lg border border-blue-200 bg-blue-50 p-3">
              <div class="text-sm font-semibold text-slate-950">{{ t('evidence.current_chunk') }}</div>
              <div v-if="chunk?.titlePath?.length" class="mt-2 text-xs leading-5 text-slate-500">
                {{ chunk.titlePath.join(' / ') }}
              </div>
              <pre class="mt-3 max-h-[45vh] overflow-auto whitespace-pre-wrap break-words rounded-md bg-white p-3 text-sm leading-6 text-slate-800">{{ sourceText }}</pre>
            </section>
          </aside>
        </div>
      </section>
    </div>
  </Teleport>
</template>

<style scoped>
.pdf-source-layer {
  min-height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 18px;
  padding: 18px;
}

.pdf-source-layer :deep(.pdf-source-page) {
  position: relative;
  flex: 0 0 auto;
  border: 1px solid #d9e2ef;
  border-radius: 8px;
  background: #fff;
  box-shadow: 0 10px 28px rgba(15, 23, 42, 0.14);
  overflow: hidden;
}

.pdf-source-layer :deep(canvas) {
  display: block;
}

.pdf-source-layer :deep(.pdf-highlight-layer) {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.pdf-source-layer :deep(.source-highlight) {
  position: absolute;
  border-radius: 3px;
  background: rgba(255, 214, 10, 0.38);
  box-shadow: 0 0 0 1px rgba(234, 179, 8, 0.35), 0 0 0 4px rgba(255, 214, 10, 0.12);
  mix-blend-mode: multiply;
}

.pdf-source-layer :deep(.has-source-highlight) {
  box-shadow: 0 0 0 2px rgba(54, 106, 255, 0.35), 0 14px 34px rgba(54, 106, 255, 0.18);
}
</style>
