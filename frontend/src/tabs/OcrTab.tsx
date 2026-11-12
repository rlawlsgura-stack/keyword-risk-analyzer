import { useEffect, useMemo, useRef, useState } from 'react'
import { extractOCR, saveOCRKeywords, suggestKeyword } from '../lib/api.ts'
import { pySorted } from '../lib/catalog.ts'
import type { KeywordSuggestion, OCRCandidate, OCRFileResult } from '../lib/types.ts'
import { useStore } from '../store.tsx'
import { Alert, Button, Expander, Spinner, errorText } from '../components/ui.tsx'

const ACCEPT = ['png', 'jpg', 'jpeg', 'webp', 'bmp']
const MB = 1024 * 1024
const MAX_FILES = 5, MAX_FILE = 20 * MB, MAX_TOTAL = 50 * MB
const PER_PAGE = 2

const norm = (s: string) => s.normalize('NFKC').trim().split(/\s+/).join(' ').toLowerCase()

/** _ocr_options_for_column (L2948): "" + sorted unique(catalog ∪ configured), no none/nan/(직접 입력). */
function optionsFor(catalogValues: string[], configured: string[]): string[] {
  const set = new Set<string>()
  for (const raw of [...catalogValues, ...configured]) {
    const v = String(raw ?? '').trim()
    if (!v || ['none', 'nan'].includes(v.toLowerCase()) || v.includes('(직접 입력)')) continue
    set.add(v)
  }
  const sorted = pySorted(set)
  return ['', ...(sorted.length ? sorted : ['-'])]
}

export function OcrTab() {
  const { catalog, dropdowns, ocr, setOcr, analysisText, setAnalysisText, setAutoRun, setTab, reloadCatalog, isAdmin } = useStore()
  const [busy, setBusy] = useState(false)
  const [engineError, setEngineError] = useState('')
  const [notice, setNotice] = useState<{ kind: 'success' | 'warning' | 'error'; text: string } | null>(null)
  const [previews, setPreviews] = useState<string[]>([])
  const inputRef = useRef<HTMLInputElement>(null)

  const files = ocr.files
  const totalBytes = files.reduce((s, f) => s + f.size, 0)
  const tooMany = files.length > MAX_FILES
  const tooBig = totalBytes > MAX_TOTAL

  useEffect(() => {
    const urls = files.map(f => URL.createObjectURL(f))
    setPreviews(urls)
    return () => urls.forEach(u => URL.revokeObjectURL(u))
  }, [files])

  const rows = catalog?.rows ?? []
  const col = (c: string) => rows.map(r => String(r[c] ?? ''))
  const opts = useMemo(() => ({
    category: optionsFor(col('상품카테고리'), dropdowns?.opt_categories ?? []),
    risk: optionsFor(col('리스크 등급'), dropdowns?.opt_risks ?? []),
    detail: optionsFor(col('리스크 등급별 세부 심의기준'), dropdowns?.opt_details ?? []),
    evidence: optionsFor(col('증빙자료유형'), dropdowns?.opt_evidences ?? []),
    alternative: optionsFor(col('대체키워드'), dropdowns?.opt_alt_terms ?? []),
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }), [catalog, dropdowns])

  const existingPairs = useMemo(() => new Set(rows.map(r => `${norm(String(r['키워드명'] ?? ''))}\u0000${norm(String(r['상품카테고리'] ?? ''))}`)), [rows])
  const pairOf = (c: OCRCandidate) => `${norm(c.term)}\u0000${norm(c.category)}`
  const duplicates = useMemo(() => {
    const counts = new Map<string, number>()
    for (const c of ocr.candidates) counts.set(pairOf(c), (counts.get(pairOf(c)) ?? 0) + 1)
    return [...new Set(ocr.candidates.filter(c => existingPairs.has(pairOf(c)) || (counts.get(pairOf(c)) ?? 0) > 1).map(c => c.term.trim()))]
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ocr.candidates, existingPairs])

  const choose = (list: FileList | null) => {
    const chosen = [...(list ?? [])].filter(f => ACCEPT.includes(f.name.split('.').pop()?.toLowerCase() ?? ''))
    const oversized = chosen.filter(f => f.size > MAX_FILE)
    setNotice(oversized.length ? { kind: 'error', text: `${oversized.map(f => f.name).join(', ')}: 파일별 한도 20MB를 넘었습니다.` } : null)
    setOcr(s => ({ ...s, files: chosen.filter(f => f.size <= MAX_FILE), results: [], candidates: [], page: 0, version: s.version + 1 }))
  }

  const runOcr = async () => {
    setBusy(true); setEngineError(''); setNotice(null)
    try {
      const result = await extractOCR(files)
      setOcr(s => ({ ...s, results: result.files, candidates: result.candidates, version: s.version + 1 }))
    } catch (error) {
      setEngineError(`OCR 준비 중 오류가 발생했습니다: ${errorText(error)}`)
    } finally { setBusy(false) }
  }

  const reset = () => {
    setOcr(s => ({ files: [], results: [], candidates: [], page: 0, version: s.version + 1 }))
    if (inputRef.current) inputRef.current.value = ''
    setNotice(null)
  }

  const update = (i: number, patch: Partial<OCRCandidate>) =>
    setOcr(s => ({ ...s, candidates: s.candidates.map((c, j) => (j === i ? {
      ...c, ...(Object.keys(patch).some(key => key !== 'approved' && key !== 'ai_suggestion') ? { ai_suggestion: undefined } : {}), ...patch,
    } : c)) }))

  const applySuggestedFields = (i: number, suggestion: KeywordSuggestion) => {
    const current = ocr.candidates[i]
    if (!current) return
    const blank = (value: string) => !value.trim() || value.trim() === '-'
    update(i, {
      ...(blank(current.category) && suggestion.category ? { category: suggestion.category } : {}),
      ...(blank(current.risk) && suggestion.risk ? { risk: suggestion.risk } : {}),
      ...(blank(current.detail) && suggestion.criteria ? { detail: suggestion.criteria } : {}),
      ...(blank(current.evidence) && suggestion.evidence_type ? { evidence: suggestion.evidence_type } : {}),
      ...(blank(current.alternative) && suggestion.alternative ? { alternative: suggestion.alternative } : {}),
      ai_suggestion: suggestion,
    })
  }

  const applyCategoryOption = async (i: number, suggestion: KeywordSuggestion,
                                     option: KeywordSuggestion['category_options'][number]) => {
    const dbSuggestion: KeywordSuggestion = {
      ...suggestion, status: 'suggested', category: option.category, risk: option.risk,
      criteria: option.criteria, evidence_type: option.evidence_type, alternative: option.alternative,
      reason: `기존 DB 사례 '${option.keyword}'의 분류값을 적용했습니다. 상품과 광고 전체 맥락을 확인하세요.`,
      source_ids: [option.source_id],
    }
    setBusy(true); setNotice(null)
    try {
      const detailed = await suggestKeyword(ocr.candidates[i].term.trim(), option.category)
      applySuggestedFields(i, detailed.status === 'suggested' ? detailed : dbSuggestion)
      setNotice({ kind: detailed.status === 'suggested' ? 'success' : 'warning', text: detailed.status === 'suggested'
        ? '상품군에 맞는 추천값으로 빈 셀을 채웠습니다. 근거를 확인한 뒤 승인하세요.'
        : 'AI가 세부 기준을 검증하지 못해 선택한 DB 사례값만 적용했습니다. 검토 후 승인하세요.' })
    } catch (error) {
      applySuggestedFields(i, dbSuggestion)
      setNotice({ kind: 'warning', text: `AI 상세 분석에 실패해 선택한 DB 사례값만 적용했습니다: ${errorText(error)}` })
    } finally { setBusy(false) }
  }

  const recommend = async (i: number) => {
    const candidate = ocr.candidates[i]
    if (!candidate?.term.trim()) return
    setBusy(true); setNotice(null)
    try {
      const suggestion = await suggestKeyword(candidate.term.trim(), candidate.category)
      if (suggestion.status === 'suggested') applySuggestedFields(i, suggestion)
      else update(i, { ai_suggestion: suggestion })
      setNotice(suggestion.status === 'suggested'
        ? { kind: 'success', text: '추천값으로 빈 셀을 채웠습니다. 근거를 확인한 뒤 승인하세요.' } : null)
    } catch (error) { setNotice({ kind: 'error', text: `AI 추천에 실패했습니다: ${errorText(error)}` }) }
    finally { setBusy(false) }
  }

  const allApproved = ocr.candidates.length > 0 && ocr.candidates.every(c => c.approved)

  const sendToAnalysis = () => {
    const text = ocr.candidates.filter(c => c.approved && c.term.trim())
      .flatMap(c => Array(Math.max(1, c.occurrences)).fill(c.term.trim())).join('\n')
    if (!text) { setNotice({ kind: 'error', text: '승인 체크된 OCR 후보가 없어 분석할 수 없습니다.' }); return }
    const base = analysisText.replace(/[\r\n]+$/, '')
    const combined = base.trim() ? `${base}\n\n${text}` : text
    if (combined.length > 20000) {
      setNotice({ kind: 'error', text: '기존 스크립트와 OCR 후보를 합친 분석 입력은 20,000자까지 가능합니다. 내용을 줄인 뒤 다시 시도하세요.' })
      return
    }
    setAnalysisText(combined)
    setAutoRun(true)
    setTab('analysis')
  }

  const save = async () => {
    setNotice(null)
    const approved = ocr.candidates.filter(c => c.approved)
    if (!approved.length) { setNotice({ kind: 'warning', text: '등록할 OCR 후보를 먼저 선택하세요.' }); return }
    if (approved.some(c => [c.term, c.category, c.risk, c.detail, c.evidence].some(v => !String(v ?? '').trim()))) {
      setNotice({ kind: 'error', text: '승인한 모든 행에 키워드명·카테고리·리스크 등급·심의기준·증빙자료 유형을 입력하세요.' }); return
    }
    const pairs = approved.map(pairOf)
    if (new Set(pairs).size !== pairs.length || pairs.some(p => existingPairs.has(p))) {
      setNotice({ kind: 'error', text: '승인 후보에 기존 DB 또는 후보끼리 중복된 키워드가 있습니다. 중복을 수정하거나 승인 해제하세요.' }); return
    }
    setBusy(true)
    try {
      const fresh = await reloadCatalog()
      const result = await saveOCRKeywords(fresh?.revision ?? 0, approved.map(c => ({
        term: c.term.trim(), category: c.category.trim(), risk: c.risk.trim(), detail: c.detail.trim(),
        evidence: c.evidence.trim(), alternative: c.alternative.trim() || '-',
      })))
      await reloadCatalog()
      setOcr(s => ({ ...s, files: [], candidates: [], page: 0, version: s.version + 1 }))
      if (inputRef.current) inputRef.current.value = ''
      setNotice({ kind: 'success', text: `관리자 승인 키워드 ${result.added.length}건을 등록했습니다.` })
    } catch (error) {
      await reloadCatalog()
      const msg = errorText(error)
      setNotice({ kind: 'error', text: /changed|revision/i.test(msg) ? '데이터가 변경되었습니다. 새로 불러온 후 다시 시도하세요.'
        : /duplicate/i.test(msg) ? '승인 후보에 기존 DB 또는 후보끼리 중복된 키워드가 있습니다. 중복을 수정하거나 승인 해제하세요.' : msg })
    } finally { setBusy(false) }
  }

  const pageCount = Math.ceil(files.length / PER_PAGE)
  const page = Math.min(ocr.page, Math.max(0, pageCount - 1))
  const resultsByName = new Map(ocr.results.map(r => [r.index, r]))
  const hasOverlay = ocr.results.some(r => r.preview_data && r.lines.some(l => l.bbox))

  return (
    <div>
      {engineError && <Alert kind="error">{engineError}</Alert>}
      <h3>이미지 OCR분석</h3>
      <div className="caption">이미지에서 키워드 후보만 추출합니다. 필수 분류 항목을 검토·승인한 뒤 DB에 저장할 수 있습니다.</div>
      <div style={{ maxWidth: 720, margin: '.75rem 0' }}>
        <label className="field">키워드 이미지 업로드</label>
        <div style={{ background: '#f0f2f6', borderRadius: 8, minHeight: 62, padding: '.75rem 1rem', display: 'flex', alignItems: 'center', gap: '1rem' }}
          onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); choose(e.dataTransfer.files) }}>
          <span className="caption" style={{ flex: 1 }}>Drag and drop files here · Limit 20MB per file · PNG, JPG, JPEG, WEBP, BMP</span>
          <Button onClick={() => inputRef.current?.click()}>Browse files</Button>
          <input ref={inputRef} type="file" multiple hidden accept={ACCEPT.map(a => `.${a}`).join(',')} onChange={e => choose(e.target.files)} />
        </div>
      </div>
      {files.length > 0 && (
        <>
          <div className="caption">첨부한 이미지: {files.length}장 / 총 {(totalBytes / MB).toFixed(1)}MB (최대 5장, 총 50MB)</div>
          <div className="caption">파일별 한도는 20MB입니다. 선택한 파일은 한 장씩 차례대로 OCR처리합니다.</div>
          {tooMany && <Alert kind="error">이미지는 한 번에 최대 5장까지 업로드할 수 있습니다.</Alert>}
          {tooBig && <Alert kind="error">업로드 전체 용량은 50MB까지 가능합니다. 파일 수를 줄이거나 이미지를 압축해서 올려주세요.</Alert>}
          {hasOverlay && <div className="caption">이미지 위 인식 글자를 드래그해 선택한 뒤 Ctrl+C로 복사할 수 있습니다.</div>}
          <div className="mt"><Button primary disabled={busy || tooMany || tooBig} onClick={runOcr}>OCR 분석 실행</Button></div>
          {busy && <Spinner text={`${files.length}장의 이미지를 순차로 OCR 처리하고 있습니다...`} />}
          <div style={{ width: '60%', minWidth: 320 }} className="mt">
            {pageCount > 1 && (
              <div className="row center" style={{ justifyContent: 'space-between' }}>
                <Button small disabled={page <= 0} onClick={() => setOcr(s => ({ ...s, page: page - 1 }))}>‹ 이전</Button>
                <span>{page + 1} / {pageCount}</span>
                <Button small disabled={page >= pageCount - 1} onClick={() => setOcr(s => ({ ...s, page: page + 1 }))}>다음 ›</Button>
              </div>
            )}
            <div className="row" style={{ alignItems: 'flex-start' }}>
              {files.slice(page * PER_PAGE, page * PER_PAGE + PER_PAGE).map((file, k) => {
                const i = page * PER_PAGE + k
                return (
                  <div className="col" key={`${file.name}-${i}`}>
                    <div className="caption">{file.name} ({i + 1}/{files.length})</div>
                    <OcrPreview src={previews[i]} result={resultsByName.get(i)} />
                  </div>
                )
              })}
            </div>
          </div>
          {files.length > 1 && (
            <Expander title={`첨부 이미지 파일명 ${files.length}개 확인`}>
              {files.map((f, i) => <div key={i}>• {f.name} ({(f.size / MB).toFixed(1)}MB)</div>)}
            </Expander>
          )}
        </>
      )}
      {ocr.results.map(r => (
        r.error ? <Alert key={r.index} kind="error">{`${r.name}: OCR 처리 실패 - ${r.error}`}</Alert>
          : r.count ? <div key={r.index} className="caption">{r.name}: OCR 인식 완료 ({r.count}개 텍스트)</div>
            : <Alert key={r.index} kind="warning">{`${r.name}: 인식한 텍스트가 없습니다.`}</Alert>
      ))}
      {notice && <Alert kind={notice.kind}>{notice.text}</Alert>}
      {!ocr.candidates.length ? (
        <div style={{ background: '#e8f1ff', color: '#0061b0', minHeight: 62, maxWidth: 720, borderRadius: 8, padding: '1rem', marginTop: '1rem' }}>
          이미지를 업로드하고 OCR을 실행하면 검토할 후보가 여기에 표시됩니다.
        </div>
      ) : (
        <div className="mt">
          <Button onClick={reset}>OCR 분석 초기화</Button>
          <div className="table-wrap mt">
            <table className="grid">
              <thead>
                <tr>
                  <th className="sel"><input type="checkbox" aria-label="OCR 후보 전체 선택/해제" checked={allApproved}
                    onChange={e => setOcr(s => ({ ...s, candidates: s.candidates.map(c => ({ ...c, approved: e.target.checked })) }))} /></th>
                  <th>키워드명</th><th className="num">OCR 신뢰도(%)</th><th>상품 카테고리</th><th>리스크 등급</th>
                   <th>심의기준</th><th>증빙자료 유형</th><th>대체키워드</th><th>AI 추천</th>
                </tr>
              </thead>
              <tbody>
                {ocr.candidates.map((c, i) => (
                  <tr key={i} className={c.approved ? 'selected' : undefined}>
                    <td className="sel"><input type="checkbox" checked={c.approved} aria-label={`${c.term} 승인`} onChange={e => update(i, { approved: e.target.checked })} /></td>
                    <td><input type="text" value={c.term} onChange={e => update(i, { term: e.target.value })} /></td>
                    <td className="num">{Math.round(c.confidence * 100)}%</td>
                    {(['category', 'risk', 'detail', 'evidence', 'alternative'] as const).map(field => (
                      <td key={field}>
                        <select value={['none', 'nan'].includes(String(c[field]).toLowerCase()) ? '' : c[field]} onChange={e => update(i, { [field]: e.target.value })}>
                          {(opts[field].includes(c[field]) ? opts[field] : [...opts[field], c[field]]).map(o => <option key={o} value={o}>{o}</option>)}
                        </select>
                      </td>
                    ))}
                    <td><Button small onClick={() => void recommend(i)} disabled={busy || !c.term.trim()}>근거 찾기</Button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {ocr.candidates.map((candidate, index) => candidate.ai_suggestion && (
            <details key={index} className="mt"><summary>{candidate.term} · AI 추천 근거</summary>
              <p>{candidate.ai_suggestion.reason}</p>
              {candidate.ai_suggestion.status === 'needs_category' &&
                candidate.ai_suggestion.category_options.map(option => (
                  <div className="row tight mt" key={option.category}>
                    <Button small disabled={busy} onClick={() => applyCategoryOption(index, candidate.ai_suggestion!, option)}>
                      {option.category} · {option.risk} 적용
                    </Button>
                    <span className="caption">DB 사례: {option.keyword} / {option.criteria}</span>
                  </div>
                ))}
              {candidate.ai_suggestion.warnings.map((warning, i) => <div className="caption" key={i}>{warning}</div>)}
              {candidate.ai_suggestion.source_ids.map(id => {
                const source = candidate.ai_suggestion?.sources.find(item => item.id === id)
                return source && <details key={id}><summary>[{id}] {source.label}</summary><pre style={{ whiteSpace: 'pre-wrap' }}>{source.text}</pre></details>
              })}
            </details>
          ))}
          {duplicates.length > 0 && <Alert kind="warning">{`기존 DB 또는 후보끼리 중복된 항목: ${duplicates.join(', ')}`}</Alert>}
          <div className="caption">신뢰도가 60% 미만인 후보는 기본 선택 해제 상태입니다. 모든 후보를 직접 검토하세요.</div>
          <div className="row tight mt">
            <Button onClick={sendToAnalysis} title="승인 체크된 OCR 후보만 분석 입력란에 보내고 기존 키워드 DB로 분석합니다.">OCR 후보 텍스트 분석 및 하이라이트 미리보기</Button>
            {isAdmin && <Button primary onClick={save} disabled={busy}>선택 후보 승인 및 DB 저장</Button>}
          </div>
        </div>
      )}
    </div>
  )
}

/** Image with a transparent, selectable text layer at each recognised line (ocr_keyword_import.py). */
function OcrPreview({ src, result }: { src?: string; result?: OCRFileResult }) {
  const [previewFailed, setPreviewFailed] = useState(false)
  useEffect(() => setPreviewFailed(false), [result?.preview_data])

  if (!result || !result.preview_data) {
    return (
      <>
        {src && <img src={src} alt="" style={{ maxWidth: '100%' }} />}
        {result?.preview_error && <div className="caption">선택 레이어 미리보기를 만들지 못했습니다. OCR 후보는 유지됩니다.</div>}
      </>
    )
  }
  const w = result.image_width || 1, h = result.image_height || 1
  const boxed = result.lines.filter(l => l.text && l.bbox && l.bbox.length === 4 && l.bbox[2] > l.bbox[0] && l.bbox[3] > l.bbox[1])
  if (previewFailed) {
    return (
      <>
        {src && <img src={src} alt="업로드한 스캔 이미지" style={{ maxWidth: '100%' }} />}
        <div className="caption">OCR 미리보기 이미지를 불러오지 못해 업로드한 원본을 표시합니다.</div>
      </>
    )
  }
  return (
    <>
      <div className="ocr-wrap" style={{ containerType: 'inline-size', width: '100%' }}>
        <img src={result.preview_data} alt="OCR 분석 이미지" onError={() => setPreviewFailed(true)} />
        {boxed.map((l, i) => {
          const [x1, y1, x2, y2] = l.bbox as number[]
          return (
            <span key={i} className="ocr-box"
              style={{
                left: `${(x1 / w) * 100}%`, top: `${(y1 / h) * 100}%`, width: `${((x2 - x1) / w) * 100}%`, height: `${((y2 - y1) / h) * 100}%`,
                fontSize: `${(100 * (y2 - y1) * 0.78) / w}cqw`, lineHeight: 1,
              }}>{l.text}</span>
          )
        })}
      </div>
      {boxed.length === 0 && result.lines.length > 0 && <div className="caption">인식 결과의 위치 정보가 없어 이미지 위에서 선택할 수 없습니다.</div>}
      {boxed.length > 0 && boxed.length < result.lines.length && <div className="caption">일부 인식 문장은 위치 정보를 얻지 못해 이미지에서 선택할 수 없습니다.</div>}
    </>
  )
}
