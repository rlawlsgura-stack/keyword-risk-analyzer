import { useEffect, useRef, useState, type ReactNode } from 'react'
import { extractOCR } from '../lib/api.ts'
import type { OCRFileResult, OCRLine } from '../lib/types.ts'
import { Alert, Button, Spinner } from '../components/ui.tsx'

const ACCEPT = ['png', 'jpg', 'jpeg', 'webp', 'bmp']
const MAX_FILE = 20 * 1024 * 1024
type TextRange = { start: number; end: number }
type Difference = {
  kind: 'changed' | 'added' | 'removed'; aIndex?: number; bIndex?: number; aText: string; bText: string
  aRanges?: TextRange[]; bRanges?: TextRange[]; aMatches?: TextRange[]; bMatches?: TextRange[]
}
type Match = { aIndex: number; bIndex: number; aText: string; bText: string; aRanges: TextRange[]; bRanges: TextRange[] }
type ComparisonMode = 'differences' | 'matches' | 'requirements'
type Side = 'a' | 'b'
type TextHighlight = TextRange & { kind: MarkKind }
type MarkKind = Difference['kind'] | 'matched'
type TextAlignment = { aMatches: TextRange[]; bMatches: TextRange[]; aChanges: TextRange[]; bChanges: TextRange[] }
type SearchTermCheck = { term: string; occurrences: number }
type SearchTermAnalysis = { checks: SearchTermCheck[]; marks: Array<{ aIndex: number; highlights: TextHighlight[] }> }
type Comparison = {
  a: OCRFileResult | null; b: OCRFileResult | null; differences: Difference[]; matches: Match[]
  searchTerms: SearchTermCheck[]; searchMarks: SearchTermAnalysis['marks']
  hashes: [string | null, string | null]; identical: boolean; approximate: boolean
}

const normalizeLine = (value: string) => value.normalize('NFKC').toLocaleLowerCase().replace(/\s+/g, ' ').trim()

function compareLines(a: OCRLine[], b: OCRLine[]): { differences: Difference[]; approximate: boolean } {
  const left = a.map(line => normalizeLine(line.text))
  const right = b.map(line => normalizeLine(line.text))
  const n = left.length, m = right.length
  if (n * m > 1_000_000 || Math.max(n, m) > 2000) {
    const differences: Difference[] = []
    for (let index = 0; index < Math.max(n, m); index++) {
      if (left[index] === right[index]) continue
      differences.push({
        kind: index >= n ? 'added' : index >= m ? 'removed' : 'changed',
        aIndex: index < n ? index : undefined, bIndex: index < m ? index : undefined,
        aText: a[index]?.text ?? '', bText: b[index]?.text ?? '',
      })
    }
    return { differences, approximate: true }
  }

  const lcs = Array.from({ length: n + 1 }, () => new Uint16Array(m + 1))
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      lcs[i][j] = left[i] && left[i] === right[j] ? lcs[i + 1][j + 1] + 1 : Math.max(lcs[i + 1][j], lcs[i][j + 1])
    }
  }

  const anchors: Array<[number, number]> = []
  let i = 0, j = 0
  while (i < n && j < m) {
    if (left[i] && left[i] === right[j]) { anchors.push([i++, j++]); continue }
    if (lcs[i + 1][j] >= lcs[i][j + 1]) i++
    else j++
  }

  const differences: Difference[] = []
  let startA = 0, startB = 0
  const addGap = (endA: number, endB: number) => {
    const count = Math.max(endA - startA, endB - startB)
    for (let offset = 0; offset < count; offset++) {
      const aIndex = startA + offset, bIndex = startB + offset
      differences.push({
        kind: aIndex >= endA ? 'added' : bIndex >= endB ? 'removed' : 'changed',
        aIndex: aIndex < endA ? aIndex : undefined, bIndex: bIndex < endB ? bIndex : undefined,
        aText: a[aIndex]?.text ?? '', bText: b[bIndex]?.text ?? '',
      })
    }
  }
  for (const [anchorA, anchorB] of anchors) {
    addGap(anchorA, anchorB)
    startA = anchorA + 1
    startB = anchorB + 1
  }
  addGap(n, m)
  return { differences, approximate: false }
}

function normalizeMappedText(value: string) {
  const values: string[] = [], sourceIndexes: number[] = []
  Array.from(value).forEach((character, sourceIndex) => {
    for (const normalized of Array.from(character.normalize('NFKC').toLocaleLowerCase())) {
      const comparable = /\s/u.test(normalized) ? ' ' : normalized
      if (comparable === ' ' && values.at(-1) === ' ') continue
      values.push(comparable)
      sourceIndexes.push(sourceIndex)
    }
  })
  let start = 0, end = values.length
  while (values[start] === ' ') start++
  while (end > start && values[end - 1] === ' ') end--
  return { chars: values.slice(start, end), sourceIndexes: sourceIndexes.slice(start, end) }
}

function rangesFromIndexes(sourceIndexes: number[]): TextRange[] {
  const sorted = [...new Set(sourceIndexes)].sort((a, b) => a - b)
  const ranges: TextRange[] = []
  for (const index of sorted) {
    const previous = ranges.at(-1)
    if (previous && index <= previous.end) previous.end = Math.max(previous.end, index + 1)
    else ranges.push({ start: index, end: index + 1 })
  }
  return ranges
}

function allTextRanges(value: string): TextRange[] {
  const chars = Array.from(value)
  const indexes = chars.flatMap((character, index) => /\s/u.test(character) ? [] : [index])
  return rangesFromIndexes(indexes)
}

function alignText(aText: string, bText: string): TextAlignment {
  const a = normalizeMappedText(aText), b = normalizeMappedText(bText)
  const originalA = Array.from(aText), originalB = Array.from(bText)
  const aMatched = new Set<number>(), bMatched = new Set<number>()
  const n = a.chars.length, m = b.chars.length
  if (n * m <= 250_000 && n && m) {
    const lcs = Array.from({ length: n + 1 }, () => new Uint16Array(m + 1))
    for (let i = n - 1; i >= 0; i--) {
      for (let j = m - 1; j >= 0; j--) {
        lcs[i][j] = a.chars[i] === b.chars[j] ? lcs[i + 1][j + 1] + 1 : Math.max(lcs[i + 1][j], lcs[i][j + 1])
      }
    }
    let i = 0, j = 0
    while (i < n && j < m) {
      if (a.chars[i] === b.chars[j]) {
        aMatched.add(a.sourceIndexes[i++])
        bMatched.add(b.sourceIndexes[j++])
      } else if (lcs[i + 1][j] >= lcs[i][j + 1]) i++
      else j++
    }
  } else {
    let prefix = 0
    while (prefix < n && prefix < m && a.chars[prefix] === b.chars[prefix]) {
      aMatched.add(a.sourceIndexes[prefix])
      bMatched.add(b.sourceIndexes[prefix])
      prefix++
    }
    let suffix = 0
    while (n - suffix > prefix && m - suffix > prefix && a.chars[n - suffix - 1] === b.chars[m - suffix - 1]) {
      aMatched.add(a.sourceIndexes[n - suffix - 1])
      bMatched.add(b.sourceIndexes[m - suffix - 1])
      suffix++
    }
  }
  const aComparable = a.sourceIndexes.filter(index => !/\s/u.test(originalA[index]))
  const bComparable = b.sourceIndexes.filter(index => !/\s/u.test(originalB[index]))
  return {
    aMatches: rangesFromIndexes([...aMatched].filter(index => !/\s/u.test(originalA[index]))).filter(range => range.end - range.start >= 2),
    bMatches: rangesFromIndexes([...bMatched].filter(index => !/\s/u.test(originalB[index]))).filter(range => range.end - range.start >= 2),
    aChanges: rangesFromIndexes(aComparable.filter(index => !aMatched.has(index))),
    bChanges: rangesFromIndexes(bComparable.filter(index => !bMatched.has(index))),
  }
}

function withTextRanges(difference: Difference): Difference {
  if (difference.kind === 'changed') {
    const aligned = alignText(difference.aText, difference.bText)
    return { ...difference, aRanges: aligned.aChanges, bRanges: aligned.bChanges, aMatches: aligned.aMatches, bMatches: aligned.bMatches }
  }
  return difference.kind === 'added'
    ? { ...difference, aRanges: [], bRanges: allTextRanges(difference.bText), aMatches: [], bMatches: [] }
    : { ...difference, aRanges: allTextRanges(difference.aText), bRanges: [], aMatches: [], bMatches: [] }
}

function differenceTextRanges(difference: Difference): { aRanges: TextRange[]; bRanges: TextRange[] } {
  return { aRanges: difference.aRanges ?? [], bRanges: difference.bRanges ?? [] }
}

function HighlightedText({ text, ranges, kind = 'matched' }: { text: string; ranges: Array<TextRange & { kind?: MarkKind }>; kind?: MarkKind }) {
  const chars = Array.from(text)
  const parts: ReactNode[] = []
  let cursor = 0
  ranges.forEach((range, index) => {
    const start = Math.max(cursor, Math.max(0, Math.min(chars.length, range.start)))
    const end = Math.max(start, Math.min(chars.length, range.end))
    if (end <= start) return
    if (start > cursor) parts.push(chars.slice(cursor, start).join(''))
    parts.push(<mark key={index} className="ocr-ab-text-mark" data-kind={range.kind ?? kind}>{chars.slice(start, end).join('')}</mark>)
    cursor = end
  })
  if (cursor < chars.length) parts.push(chars.slice(cursor).join(''))
  return <>{parts.length ? parts : text}</>
}

function DifferenceText({ difference, side }: { difference: Difference; side: Side }) {
  const ranges = differenceTextRanges(difference)
  const text = side === 'a' ? difference.aText : difference.bText
  return <HighlightedText text={text || '해당 문구 없음'} ranges={side === 'a' ? ranges.aRanges : ranges.bRanges} kind={difference.kind} />
}

let textMeasureContext: CanvasRenderingContext2D | null | undefined

function estimateCharacterPositions(text: string, lineHeight: number): number[] {
  const chars = Array.from(text)
  const fallbackWeights = chars.map(character => {
    if (/\s/u.test(character)) return 0.32
    if (/[\u1100-\u11ff\u3130-\u318f\uac00-\ud7af\u2e80-\ua4cf]/u.test(character)) return 1
    if (/[ilI1.,:;'|!]/u.test(character)) return 0.32
    if (/[MW@%#&]/u.test(character)) return 0.88
    return 0.58
  })
  const makePositions = (weights: number[]) => {
    const total = weights.reduce((sum, weight) => sum + weight, 0)
    let position = 0
    return [0, ...weights.map(weight => {
      position += total ? weight / total : 0
      return position
    })]
  }
  if (textMeasureContext === undefined) {
    textMeasureContext = typeof document === 'undefined' ? null : document.createElement('canvas').getContext('2d')
  }
  const context = textMeasureContext
  if (!context) return makePositions(fallbackWeights)

  context.font = `${Math.max(1, lineHeight)}px "Malgun Gothic", Arial, sans-serif`
  const widths = [0]
  let prefix = ''
  for (const character of chars) {
    prefix += character
    widths.push(context.measureText(prefix).width)
  }
  const totalWidth = widths[widths.length - 1]
  return totalWidth > 0 ? widths.map(width => width / totalWidth) : makePositions(fallbackWeights)
}

function findMatchingLines(a: OCRLine[], b: OCRLine[]): Match[] {
  const aIndexes = new Map<string, number[]>()
  a.forEach((line, index) => {
    const key = normalizeLine(line.text)
    if (!key) return
    const indexes = aIndexes.get(key)
    if (indexes) indexes.push(index)
    else aIndexes.set(key, [index])
  })
  const used = new Map<string, number>()
  return b.flatMap((line, bIndex) => {
    const key = normalizeLine(line.text)
    const candidates = aIndexes.get(key)
    if (!key || !candidates) return []
    const offset = used.get(key) ?? 0
    if (offset >= candidates.length) return []
    used.set(key, offset + 1)
    const aIndex = candidates[offset]
    const aText = a[aIndex].text
    const ranges = allTextRanges(aText)
    return [{ aIndex, bIndex, aText, bText: line.text, aRanges: ranges, bRanges: allTextRanges(line.text) }]
  })
}

function parseSearchTerms(value: string): string[] {
  const unique = new Map<string, string>()
  for (const raw of value.split(/[,，;；\n]+/)) {
    const term = raw.trim()
    const key = normalizeMappedText(term).chars.join('').replace(/\s/gu, '')
    if (key && !unique.has(key)) unique.set(key, term)
  }
  return [...unique.values()]
}

function findSearchTermMatches(lines: OCRLine[], terms: string[]): SearchTermAnalysis {
  const combinedText = lines.map(line => line.text).join('\n')
  const sourcePositions: Array<{ line: number; index: number } | null> = []
  lines.forEach((line, lineIndex) => {
    Array.from(line.text).forEach((_, index) => sourcePositions.push({ line: lineIndex, index }))
    if (lineIndex < lines.length - 1) sourcePositions.push(null)
  })
  const mapped = normalizeMappedText(combinedText)
  const text: string[] = [], positions: Array<{ line: number; index: number }> = []
  mapped.chars.forEach((character, index) => {
    if (/\s/u.test(character)) return
    const source = sourcePositions[mapped.sourceIndexes[index]]
    if (!source) return
    text.push(character)
    positions.push(source)
  })
  const searchable = text.join('')
  const indexesByLine = new Map<number, number[]>()
  const checks = terms.map(term => {
    const needle = normalizeMappedText(term).chars.filter(character => !/\s/u.test(character)).join('')
    let occurrences = 0
    let matchIndex = needle ? searchable.indexOf(needle) : -1
    while (matchIndex >= 0) {
      occurrences++
      positions.slice(matchIndex, matchIndex + needle.length).forEach(source => {
        indexesByLine.set(source.line, [...(indexesByLine.get(source.line) ?? []), source.index])
      })
      matchIndex = searchable.indexOf(needle, matchIndex + needle.length)
    }
    return { term, occurrences }
  })
  const marks = [...indexesByLine]
    .sort(([left], [right]) => left - right)
    .map(([aIndex, indexes]) => ({
      aIndex,
      highlights: rangesFromIndexes(indexes).map(range => ({ ...range, kind: 'matched' as const })),
    }))
  return { checks, marks }
}

async function sha256(file: File): Promise<string | null> {
  if (!globalThis.crypto?.subtle) return null
  const digest = await crypto.subtle.digest('SHA-256', await file.arrayBuffer())
  return [...new Uint8Array(digest)].map(byte => byte.toString(16).padStart(2, '0')).join('')
}

function DifferencePreview({ fileUrl, result, side, highlighted }: {
  fileUrl: string; result: OCRFileResult | null; side: Side; highlighted: Map<number, TextHighlight[]>
}) {
  const src = result?.preview_data || fileUrl
  const width = result?.image_width || 1, height = result?.image_height || 1
  const boxes = (result?.lines ?? []).flatMap((line, index) => {
    const ranges = highlighted.get(index)
    if (!ranges?.length || !line.bbox || line.bbox.length !== 4) return []
    const [boxX1, y1, boxX2, y2] = line.bbox
    if (boxX2 <= boxX1 || y2 <= y1) return []
    const chars = Array.from(line.text)
    const positions = estimateCharacterPositions(line.text, y2 - y1)
    return ranges.flatMap(range => {
      const start = Math.max(0, Math.min(chars.length, range.start))
      const end = Math.max(start, Math.min(chars.length, range.end))
      if (end <= start) return []
      const x1 = boxX1 + (boxX2 - boxX1) * positions[start]
      const x2 = boxX1 + (boxX2 - boxX1) * positions[end]
      return [{ index: [index, start, end, range.kind].join('-'), text: chars.slice(start, end).join(''), kind: range.kind, x1, y1, x2, y2 }]
    })
  })
  return <div className="ocr-ab-image-scroll"><div className="ocr-ab-image-stage">
    <img src={src} alt={`${side === 'a' ? 'A안' : 'B안'} 미리보기`} />
    {boxes.map(box => <span key={box.index} className={`ocr-ab-mark ${box.kind}`} title={box.text}
      style={{ left: `${box.x1 / width * 100}%`, top: `${box.y1 / height * 100}%`, width: `${(box.x2 - box.x1) / width * 100}%`, height: `${(box.y2 - box.y1) / height * 100}%` }} />)}
  </div></div>
}

export function OcrABCompare() {
  const [fileA, setFileA] = useState<File | null>(null)
  const [fileB, setFileB] = useState<File | null>(null)
  const [urlA, setUrlA] = useState('')
  const [urlB, setUrlB] = useState('')
  const [comparison, setComparison] = useState<Comparison | null>(null)
  const [mode, setMode] = useState<ComparisonMode>('differences')
  const [searchInput, setSearchInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const inputA = useRef<HTMLInputElement>(null)
  const inputB = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!fileA) { setUrlA(''); return }
    const url = URL.createObjectURL(fileA)
    setUrlA(url)
    return () => URL.revokeObjectURL(url)
  }, [fileA])
  useEffect(() => {
    if (!fileB) { setUrlB(''); return }
    const url = URL.createObjectURL(fileB)
    setUrlB(url)
    return () => URL.revokeObjectURL(url)
  }, [fileB])

  const selectFile = (side: Side, file?: File) => {
    if (!file) return
    const extension = file.name.split('.').pop()?.toLowerCase() ?? ''
    if (!ACCEPT.includes(extension)) { setError('PNG, JPG, JPEG, WEBP, BMP 이미지만 선택할 수 있습니다.'); return }
    if (file.size > MAX_FILE) { setError('이미지 파일은 20MB 이하로 선택해 주세요.'); return }
    setError('')
    setNotice('')
    setComparison(null)
    if (side === 'a') setFileA(file)
    else setFileB(file)
  }

  const runComparison = async () => {
    const terms = parseSearchTerms(searchInput)
    if (!fileA || busy || (mode === 'requirements' ? !terms.length : !fileB)) return
    setBusy(true)
    setError('')
    setNotice('')
    setComparison(null)
    try {
      let hashes: [string | null, string | null] = [null, null]
      if (mode !== 'requirements') hashes = await Promise.all([sha256(fileA), sha256(fileB!)])
      const [hashA, hashB] = hashes
      const identical = Boolean(hashA && hashB && hashA === hashB)
      if (identical && mode === 'differences') {
        setComparison({ a: null, b: null, differences: [], matches: [], searchTerms: [], searchMarks: [], hashes, identical: true, approximate: false })
        return
      }
      const result = await extractOCR(mode === 'requirements' ? [fileA] : [fileA, fileB!])
      const a = result.files.find(file => file.index === 0)
      const b = mode === 'requirements' ? null : result.files.find(file => file.index === 1) ?? null
      if (!a || a.error || (mode !== 'requirements' && (!b || b.error))) {
        throw new Error([a?.error, b?.error].filter(Boolean).join(' / ') || (mode === 'requirements' ? 'A안 이미지의 OCR 결과를 받지 못했습니다.' : '두 이미지의 OCR 결과를 받지 못했습니다.'))
      }
      const lineComparison = mode === 'requirements'
        ? { differences: [] as Difference[], approximate: false }
        : compareLines(a.lines, b!.lines)
      const compared = lineComparison
      const lineDifferences = lineComparison.differences.map(withTextRanges)
      const differences = mode === 'differences' ? lineDifferences : []
      const matches = mode === 'matches' ? [
        ...findMatchingLines(a.lines, b!.lines),
        ...lineDifferences.flatMap(difference => {
          if (difference.kind !== 'changed' || difference.aIndex === undefined || difference.bIndex === undefined) return []
          if (!difference.aMatches?.length && !difference.bMatches?.length) return []
          return [{
            aIndex: difference.aIndex, bIndex: difference.bIndex,
            aText: difference.aText, bText: difference.bText,
            aRanges: difference.aMatches ?? [], bRanges: difference.bMatches ?? [],
          }]
        }),
      ] : []
      const searchAnalysis = mode === 'requirements' ? findSearchTermMatches(a.lines, terms) : { checks: [], marks: [] }
      setComparison({ a, b, differences, matches, searchTerms: searchAnalysis.checks, searchMarks: searchAnalysis.marks,
        hashes, identical, approximate: compared.approximate })
      const notices = []
      if (!a.lines.some(line => line.bbox) || (b && !b.lines.some(line => line.bbox))) notices.push('OCR 위치 정보를 얻지 못한 문구는 아래 결과 목록에서만 확인할 수 있습니다.')
      if (compared.approximate) notices.push('인식 문구가 많아 순서 기준으로 간략 대조했습니다. 하이라이트를 확인해 주세요.')
      if (a.truncated || b?.truncated) notices.push(mode === 'requirements'
        ? 'A안 OCR 결과가 2,000줄에서 잘려 일부 검색 결과가 누락될 수 있습니다.'
        : mode === 'matches' ? 'OCR 결과가 2,000줄에서 잘려 일부 일치 문구가 누락될 수 있습니다.'
          : 'OCR 결과가 2,000줄에서 잘려 일부 차이는 누락될 수 있습니다.')
      setNotice(notices.join(' '))
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'A/B 비교 중 오류가 발생했습니다.')
    } finally {
      setBusy(false)
    }
  }

  const differences = comparison?.differences ?? []
  const matches = comparison?.matches ?? []
  const searchTerms = comparison?.searchTerms ?? []
  const marksA = new Map<number, TextHighlight[]>()
  const marksB = new Map<number, TextHighlight[]>()
  const addRanges = (marks: Map<number, TextHighlight[]>, index: number, ranges: TextRange[], kind: MarkKind) =>
    marks.set(index, [...(marks.get(index) ?? []), ...ranges.map(range => ({ ...range, kind }))])
  if (mode === 'matches') {
    for (const match of matches) addRanges(marksB, match.bIndex, match.bRanges, 'matched')
  } else if (mode === 'requirements') {
    for (const mark of comparison?.searchMarks ?? []) marksA.set(mark.aIndex, mark.highlights)
  } else {
    for (const difference of differences) {
      const ranges = differenceTextRanges(difference)
      if (difference.bIndex !== undefined) addRanges(marksB, difference.bIndex, ranges.bRanges, difference.kind)
    }
  }
  const searchTermsInput = parseSearchTerms(searchInput)
  const canCompare = Boolean(fileA && !busy && (mode === 'requirements' ? searchTermsInput.length : fileB))
  const searchCounts = {
    found: searchTerms.filter(item => item.occurrences > 0).length,
    missing: searchTerms.filter(item => item.occurrences === 0).length,
  }

  return <section className="ocr-ab-section">
    <div className="ocr-ab-heading">
      <div><h3>A/B 이미지 비교 검토</h3><p>검색 모드에서는 A안 이미지에서 입력한 단어를 찾고, 비교 모드에서는 A안과 B안을 대조합니다.</p></div>
      <span className="ocr-ab-badge">OCR + SHA-256</span>
    </div>
    <div className="ocr-ab-inputs ocr-ab-no-print">
      {(['a', 'b'] as const).map(side => {
        const file = side === 'a' ? fileA : fileB
        const ref = side === 'a' ? inputA : inputB
        const title = side === 'a' ? 'A안 · 원안' : 'B안 · 대조안'
        if (side === 'b' && mode === 'requirements') return <div className="ocr-ab-upload ocr-ab-search-upload" key={side}>
          <div className="ocr-ab-upload-title"><strong>A안 검색어</strong><span>쉼표로 여러 개 입력</span></div>
          <label htmlFor="ocr-ab-search-terms">찾을 단어 또는 문구</label>
          <textarea id="ocr-ab-search-terms" rows={3} value={searchInput} placeholder="제품명, 중량, 전성분, 제조번호 및 사용기한"
            onChange={event => { setSearchInput(event.target.value); setComparison(null); setError(''); setNotice('') }} />
          <p>쉼표 또는 줄바꿈으로 검색어를 구분합니다. 입력한 문구가 A안 이미지에 있으면 표시합니다.</p>
        </div>
        return <div className="ocr-ab-upload" key={side} onDragOver={event => event.preventDefault()}
          onDrop={event => { event.preventDefault(); selectFile(side, event.dataTransfer.files[0]) }}>
          <div className="ocr-ab-upload-title"><strong>{title}</strong><span>{side === 'a' ? '비교 기준' : '변경 확인 대상'}</span></div>
          <p>{file ? <><b>{file.name}</b> · {(file.size / (1024 * 1024)).toFixed(1)} MB</> : '이미지를 끌어다 놓거나 파일을 선택하세요'}</p>
          <input ref={ref} type="file" hidden accept={ACCEPT.map(ext => `.${ext}`).join(',')} onChange={event => { selectFile(side, event.target.files?.[0]); event.currentTarget.value = '' }} />
          <Button small onClick={() => ref.current?.click()}>{file ? '다른 파일 선택' : '파일 선택'}</Button>
        </div>
      })}
    </div>
    <div className="ocr-ab-controls ocr-ab-no-print">
      <label className="ocr-ab-mode">
        <span>비교 모드</span>
        <select value={mode} disabled={busy} onChange={event => {
          setMode(event.target.value as ComparisonMode)
          setComparison(null)
          setError('')
          setNotice('')
        }}>
          <option value="differences">A안 대비 B안의 차이 찾기</option>
          <option value="matches">A안과 일치하는 B안 내용 찾기</option>
          <option value="requirements">A안 이미지에서 단어 찾기</option>
        </select>
      </label>
      <span>지원 형식 PNG, JPG, JPEG, WEBP, BMP · 파일별 최대 20MB</span>
      <Button primary disabled={!canCompare} onClick={() => void runComparison()}>
        {busy ? '비교 중…' : mode === 'requirements' ? 'A안에서 단어 찾기' : mode === 'matches' ? '일치 내용 찾기' : '차이 분석'}
      </Button>
    </div>
    {error && <Alert kind="error">{error}</Alert>}
    {busy && <Spinner text={mode === 'requirements'
      ? 'A안 이미지를 OCR 분석하고 검색어를 찾고 있습니다…'
      : mode === 'matches' ? '두 이미지를 OCR 분석하고 일치 문구를 찾고 있습니다…' : '두 이미지를 OCR 분석하고 변경 문구를 대조하고 있습니다…'} />}
    {notice && <div className="ocr-ab-notice">{notice}</div>}

    {comparison && <div className="ocr-ab-report">
      <div className="ocr-ab-report-title"><div><h4>비교 검토 결과</h4><span>{mode === 'requirements'
        ? `검색어 ${searchTerms.length}개 · 발견 ${searchCounts.found} · 미발견 ${searchCounts.missing}`
        : mode === 'matches' ? `A안과 일치하는 B안 문구 ${matches.length}건`
          : comparison.identical ? '두 파일의 SHA-256이 일치합니다.' : `텍스트 차이 ${differences.length}건${comparison.hashes[0] && comparison.hashes[1] ? ' · 파일 해시는 서로 다름' : ''}`}</span></div>
        <Button className="ocr-ab-no-print" onClick={() => window.print()}>PDF로 저장</Button>
      </div>
      {comparison.identical && mode === 'differences' && <Alert kind="success">A안과 B안은 파일 내용이 완전히 같습니다. OCR 분석은 생략했습니다.</Alert>}
      {comparison.identical && mode === 'matches' && <Alert kind="info">A안과 B안은 동일한 파일입니다. OCR 문구를 대조해 일치 위치를 표시했습니다.</Alert>}
      {mode === 'differences' && !comparison.identical && differences.length === 0 && <Alert kind="info">이미지 해시는 다르지만 OCR 문구 차이는 찾지 못했습니다. 이미지 색상·배치 차이는 이 대조 범위에 포함되지 않습니다.</Alert>}
      {mode === 'matches' && matches.length === 0 && <Alert kind="info">OCR 문구가 A안과 완전히 일치하는 B안 내용을 찾지 못했습니다.</Alert>}
      <div className={`ocr-ab-panes${mode === 'requirements' ? ' single' : ''}`}>
        <article className="ocr-ab-pane"><header><strong>A안 · 원안</strong><span>{fileA?.name}</span></header>
          {urlA && <DifferencePreview fileUrl={urlA} result={comparison.a} side="a" highlighted={marksA} />}</article>
        {mode !== 'requirements' && <article className="ocr-ab-pane"><header><strong>B안 · 대조안</strong><span>{fileB?.name}</span></header>
          {urlB && <DifferencePreview fileUrl={urlB} result={comparison.b} side="b" highlighted={marksB} />}</article>}
      </div>
      {mode === 'differences' && !comparison.identical && differences.length > 0 && <>
          <div className="ocr-ab-legend"><span><i className="ocr-ab-dot changed" />변경 문구</span><span><i className="ocr-ab-dot added" />추가 문구</span><span><i className="ocr-ab-dot removed" />삭제 문구</span></div>
          <div className="ocr-ab-diffs"><h5>차이 및 확인 안내</h5>
            {differences.map((difference, index) => <article className="ocr-ab-diff" key={`${difference.kind}-${difference.aIndex}-${difference.bIndex}-${index}`}>
              <strong className={`ocr-ab-diff-kind ${difference.kind}`}>{difference.kind === 'changed' ? '변경' : difference.kind === 'added' ? '추가' : '삭제'}</strong>
              <div><small>A안</small><p><DifferenceText difference={difference} side="a" /></p></div>
              <div><small>B안</small><p><DifferenceText difference={difference} side="b" /></p></div>
              <div className="ocr-ab-advice">{difference.kind === 'changed' ? '변경된 표현의 근거와 의도된 수정인지 확인해 주세요.' : difference.kind === 'added' ? '새 문구의 근거와 사용 가능 여부를 확인해 주세요.' : '삭제가 의도된 것인지 확인하고, 필요하면 원안 문구를 복원해 주세요.'}</div>
            </article>)}
          </div>
      </>}
      {mode === 'matches' && matches.length > 0 && <>
        <div className="ocr-ab-legend"><span><i className="ocr-ab-dot matched" />A안과 일치하는 문구</span></div>
        <div className="ocr-ab-matches"><h5>A안과 일치하는 B안 문구</h5>
          {matches.map((match, index) => <article className="ocr-ab-match" key={`${match.aIndex}-${match.bIndex}-${index}`}>
            <strong>{index + 1}</strong>
            <div><small>A안 · 원안</small><p><HighlightedText text={match.aText} ranges={match.aRanges} kind="matched" /></p></div>
            <div><small>B안 · 대조안</small><p><HighlightedText text={match.bText} ranges={match.bRanges} kind="matched" /></p></div>
          </article>)}
        </div>
      </>}
      {mode === 'requirements' && searchTerms.length > 0 && <>
        <div className="ocr-ab-legend">
          <span><i className="ocr-ab-dot matched" />A안에서 찾은 검색어</span>
        </div>
        <div className="ocr-ab-requirements">
          <h5>검색어별 A안 포함 여부</h5>
          <p className="caption">입력한 단어와 문구가 A안 OCR 텍스트에 포함된 위치를 이미지에 표시합니다. 쉼표나 줄바꿈으로 여러 검색어를 입력할 수 있습니다.</p>
          {searchTerms.map((item, index) => <article className={'ocr-ab-requirement ' + (item.occurrences ? 'found' : 'missing')} key={item.term}>
            <header className="ocr-ab-requirement-head">
              <strong>{index + 1}</strong>
              <span className={'ocr-ab-requirement-status ' + (item.occurrences ? 'found' : 'missing')}>
                {item.occurrences ? `발견 ${item.occurrences}회` : '미발견'}
              </span>
            </header>
            <div className="ocr-ab-requirement-body">
              <div><small>검색어</small><p>{item.term}</p></div>
              <div><small>A안 결과</small><p>{item.occurrences ? `A안 이미지에서 ${item.occurrences}회 찾았습니다.` : 'A안 OCR 텍스트에서 찾지 못했습니다.'}</p></div>
            </div>
          </article>)}
        </div>
      </>}
      {mode === 'requirements' && <p className="ocr-ab-disclaimer">검색은 입력한 글자와 OCR 인식 문구의 포함 여부를 확인합니다. 결과는 이미지의 OCR 인식 품질에 따라 달라질 수 있습니다.</p>}
      {mode !== 'requirements' && !comparison.identical && <p className="ocr-ab-disclaimer">{mode === 'matches'
        ? '일치 결과는 공백과 영문 대소문자를 정규화한 뒤 OCR 문구 전체가 같은 줄을 찾은 검토 보조 자료입니다. 이미지 색상이나 배치의 일치는 판단하지 않습니다.'
        : '이 결과는 문구 차이를 찾는 검토 보조 자료입니다. 하이라이트만으로 위반 여부나 법적 수정 지시를 판정하지 않으며, 최종 판단은 담당자가 근거를 확인해야 합니다.'}</p>}
    </div>}
  </section>
}
