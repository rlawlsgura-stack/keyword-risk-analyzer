import { useEffect, useRef, useState } from 'react'
import { extractOCR } from '../lib/api.ts'
import type { OCRFileResult, OCRLine } from '../lib/types.ts'
import { Alert, Button, Spinner } from '../components/ui.tsx'

const ACCEPT = ['png', 'jpg', 'jpeg', 'webp', 'bmp']
const MAX_FILE = 20 * 1024 * 1024
type Difference = { kind: 'changed' | 'added' | 'removed'; aIndex?: number; bIndex?: number; aText: string; bText: string }
type Match = { aIndex: number; bIndex: number; aText: string; bText: string }
type ComparisonMode = 'differences' | 'matches'
type Comparison = { a: OCRFileResult | null; b: OCRFileResult | null; differences: Difference[]; matches: Match[]; hashes: [string | null, string | null]; identical: boolean; approximate: boolean }
type Side = 'a' | 'b'
type MarkKind = Difference['kind'] | 'matched'

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
    return [{ aIndex, bIndex, aText: a[aIndex].text, bText: line.text }]
  })
}

async function sha256(file: File): Promise<string | null> {
  if (!globalThis.crypto?.subtle) return null
  const digest = await crypto.subtle.digest('SHA-256', await file.arrayBuffer())
  return [...new Uint8Array(digest)].map(byte => byte.toString(16).padStart(2, '0')).join('')
}

function DifferencePreview({ fileUrl, result, side, highlighted }: {
  fileUrl: string; result: OCRFileResult | null; side: Side; highlighted: Map<number, MarkKind[]>
}) {
  const src = result?.preview_data || fileUrl
  const width = result?.image_width || 1, height = result?.image_height || 1
  const boxes = (result?.lines ?? []).flatMap((line, index) => {
    const kinds = highlighted.get(index)
    if (!kinds?.length || !line.bbox || line.bbox.length !== 4) return []
    const [x1, y1, x2, y2] = line.bbox
    if (x2 <= x1 || y2 <= y1) return []
    const kind = kinds.includes('matched') ? 'matched' : kinds.includes('added') ? 'added' : kinds.includes('removed') ? 'removed' : 'changed'
    return [{ index, text: line.text, kind, x1, y1, x2, y2 }]
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
    if (!fileA || !fileB || busy) return
    setBusy(true)
    setError('')
    setNotice('')
    setComparison(null)
    try {
      const [hashA, hashB] = await Promise.all([sha256(fileA), sha256(fileB)])
      const identical = Boolean(hashA && hashA === hashB)
      if (identical && mode === 'differences') {
        setComparison({ a: null, b: null, differences: [], matches: [], hashes: [hashA, hashB], identical: true, approximate: false })
        return
      }
      const result = await extractOCR([fileA, fileB])
      const a = result.files.find(file => file.index === 0)
      const b = result.files.find(file => file.index === 1)
      if (!a || !b || a.error || b.error) {
        throw new Error([a?.error, b?.error].filter(Boolean).join(' / ') || '두 이미지의 OCR 결과를 받지 못했습니다.')
      }
      const compared = mode === 'differences' ? compareLines(a.lines, b.lines) : { differences: [], approximate: false }
      const matches = mode === 'matches' ? findMatchingLines(a.lines, b.lines) : []
      setComparison({ a, b, differences: compared.differences, matches, hashes: [hashA, hashB], identical, approximate: compared.approximate })
      const notices = []
      if (!a.lines.some(line => line.bbox) || !b.lines.some(line => line.bbox)) notices.push('OCR 위치 정보를 얻지 못한 문구는 아래 결과 목록에서만 확인할 수 있습니다.')
      if (compared.approximate) notices.push('인식 문구가 많아 순서 기준으로 간략 대조했습니다. 하이라이트를 확인해 주세요.')
      if (a.truncated || b.truncated) notices.push(mode === 'matches'
        ? 'OCR 결과가 2,000줄에서 잘려 일부 일치 문구가 누락될 수 있습니다.'
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
  const marksA = new Map<number, MarkKind[]>()
  const marksB = new Map<number, MarkKind[]>()
  const addMark = (marks: Map<number, MarkKind[]>, index: number, kind: MarkKind) =>
    marks.set(index, [...(marks.get(index) ?? []), kind])
  if (mode === 'matches') {
    for (const match of matches) {
      addMark(marksA, match.aIndex, 'matched')
      addMark(marksB, match.bIndex, 'matched')
    }
  } else {
    for (const difference of differences) {
      if (difference.aIndex !== undefined) addMark(marksA, difference.aIndex, difference.kind)
      if (difference.bIndex !== undefined) addMark(marksB, difference.bIndex, difference.kind)
    }
  }
  const canCompare = Boolean(fileA && fileB && !busy)

  return <section className="ocr-ab-section">
    <div className="ocr-ab-heading">
      <div><h3>A/B 이미지 비교 검토</h3><p>비교 모드에서 차이 또는 A안과 일치하는 B안 문구를 찾아 표시합니다.</p></div>
      <span className="ocr-ab-badge">OCR + SHA-256</span>
    </div>
    <div className="ocr-ab-inputs ocr-ab-no-print">
      {(['a', 'b'] as const).map(side => {
        const file = side === 'a' ? fileA : fileB
        const ref = side === 'a' ? inputA : inputB
        const title = side === 'a' ? 'A안 · 원안' : 'B안 · 대조안'
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
        </select>
      </label>
      <span>지원 형식 PNG, JPG, JPEG, WEBP, BMP · 파일별 최대 20MB</span>
      <Button primary disabled={!canCompare} onClick={() => void runComparison()}>
        {busy ? '비교 중…' : mode === 'matches' ? '일치 내용 찾기' : '차이 분석'}
      </Button>
    </div>
    {error && <Alert kind="error">{error}</Alert>}
    {busy && <Spinner text={mode === 'matches' ? '두 이미지를 OCR 분석하고 일치 문구를 찾고 있습니다…' : '두 이미지를 OCR 분석하고 변경 문구를 대조하고 있습니다…'} />}
    {notice && <div className="ocr-ab-notice">{notice}</div>}

    {comparison && <div className="ocr-ab-report">
      <div className="ocr-ab-report-title"><div><h4>비교 검토 결과</h4><span>{mode === 'matches'
        ? `A안과 일치하는 B안 문구 ${matches.length}건`
        : comparison.identical ? '두 파일의 SHA-256이 일치합니다.' : `텍스트 차이 ${differences.length}건${comparison.hashes[0] && comparison.hashes[1] ? ' · 파일 해시는 서로 다름' : ''}`}</span></div>
        <Button className="ocr-ab-no-print" onClick={() => window.print()}>PDF로 저장</Button>
      </div>
      {comparison.identical && mode === 'differences' && <Alert kind="success">A안과 B안은 파일 내용이 완전히 같습니다. OCR 분석은 생략했습니다.</Alert>}
      {comparison.identical && mode === 'matches' && <Alert kind="info">A안과 B안은 동일한 파일입니다. OCR 문구를 대조해 일치 위치를 표시했습니다.</Alert>}
      {mode === 'differences' && !comparison.identical && differences.length === 0 && <Alert kind="info">이미지 해시는 다르지만 OCR 문구 차이는 찾지 못했습니다. 이미지 색상·배치 차이는 이 대조 범위에 포함되지 않습니다.</Alert>}
      {mode === 'matches' && matches.length === 0 && <Alert kind="info">OCR 문구가 A안과 완전히 일치하는 B안 내용을 찾지 못했습니다.</Alert>}
      <div className="ocr-ab-panes">
        <article className="ocr-ab-pane"><header><strong>A안 · 원안</strong><span>{fileA?.name}</span></header>
          {urlA && <DifferencePreview fileUrl={urlA} result={comparison.a} side="a" highlighted={marksA} />}</article>
        <article className="ocr-ab-pane"><header><strong>B안 · 대조안</strong><span>{fileB?.name}</span></header>
          {urlB && <DifferencePreview fileUrl={urlB} result={comparison.b} side="b" highlighted={marksB} />}</article>
      </div>
      {mode === 'differences' && !comparison.identical && differences.length > 0 && <>
          <div className="ocr-ab-legend"><span><i className="ocr-ab-dot changed" />변경 문구</span><span><i className="ocr-ab-dot added" />추가 문구</span><span><i className="ocr-ab-dot removed" />삭제 문구</span></div>
          <div className="ocr-ab-diffs"><h5>차이 및 확인 안내</h5>
            {differences.map((difference, index) => <article className="ocr-ab-diff" key={`${difference.kind}-${difference.aIndex}-${difference.bIndex}-${index}`}>
              <strong className={`ocr-ab-diff-kind ${difference.kind}`}>{difference.kind === 'changed' ? '변경' : difference.kind === 'added' ? '추가' : '삭제'}</strong>
              <div><small>A안</small><p>{difference.aText || '해당 문구 없음'}</p></div>
              <div><small>B안</small><p>{difference.bText || '해당 문구 없음'}</p></div>
              <div className="ocr-ab-advice">{difference.kind === 'changed' ? '변경된 표현의 근거와 의도된 수정인지 확인해 주세요.' : difference.kind === 'added' ? '새 문구의 근거와 사용 가능 여부를 확인해 주세요.' : '삭제가 의도된 것인지 확인하고, 필요하면 원안 문구를 복원해 주세요.'}</div>
            </article>)}
          </div>
      </>}
      {mode === 'matches' && matches.length > 0 && <>
        <div className="ocr-ab-legend"><span><i className="ocr-ab-dot matched" />A안과 일치하는 문구</span></div>
        <div className="ocr-ab-matches"><h5>A안과 일치하는 B안 문구</h5>
          {matches.map((match, index) => <article className="ocr-ab-match" key={`${match.aIndex}-${match.bIndex}-${index}`}>
            <strong>{index + 1}</strong>
            <div><small>A안 · 원안</small><p>{match.aText}</p></div>
            <div><small>B안 · 대조안</small><p>{match.bText}</p></div>
          </article>)}
        </div>
      </>}
      {!comparison.identical && <p className="ocr-ab-disclaimer">{mode === 'matches'
        ? '일치 결과는 공백과 영문 대소문자를 정규화한 뒤 OCR 문구 전체가 같은 줄을 찾은 검토 보조 자료입니다. 이미지 색상이나 배치의 일치는 판단하지 않습니다.'
        : '이 결과는 문구 차이를 찾는 검토 보조 자료입니다. 하이라이트만으로 위반 여부나 법적 수정 지시를 판정하지 않으며, 최종 판단은 담당자가 근거를 확인해야 합니다.'}</p>}
    </div>}
  </section>
}
