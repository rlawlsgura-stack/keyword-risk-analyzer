import { useCallback, useEffect, useMemo, useState } from 'react'
import { analyzeText, loadMatchingRules } from '../lib/api.ts'
import { DATETIME_COLUMNS, displayHeader, formatDatetime, koSorted, sortForDisplay, uniqueValues } from '../lib/catalog.ts'
import { downloadCsv } from '../lib/csv.ts'
import { buildSegments, type Segment } from '../lib/highlight.ts'
import {
  HIGHLIGHT_HELP, MODE_DETAILS, MODE_LABELS, NORMALIZATION_OPTIONS, PARTIAL_LEN_HELP, numberedHelp, rulesSummary,
  type NormalizationKey,
} from '../lib/help.ts'
import type { AnalysisInput, AnalysisMode, ApprovedPartialRules, KeywordRow, Match } from '../lib/types.ts'
import { useStore } from '../store.tsx'
import { HighlightPreview } from '../components/HighlightPreview.tsx'
import { KeywordList } from '../components/KeywordList.tsx'
import {
  Alert, Button, Checkbox, DataTable, Expander, Help, MultiSelect, NumberInput, Radio, Spinner, TextArea, errorText,
} from '../components/ui.tsx'

const MODES: AnalysisMode[] = ['exact', 'similar', 'partial']
const CSV_COLUMNS = ['kwd_no', '키워드명', '상품카테고리', '리스크 등급', '리스크 등급별 세부 심의기준', 'start', 'end']

type Outcome = {
  show: boolean
  count: number
  rows: KeywordRow[]
  matches: Match[]
  segments: Segment[] | null
}

export function AnalysisTab() {
  const { catalog, reloadCatalog, analysisText, setAnalysisText, autoRun, setAutoRun, addPending, tab } = useStore()
  const [categories, setCategories] = useState<string[]>([])
  const [risks, setRisks] = useState<string[]>([])
  const [mode, setMode] = useState<AnalysisMode>('exact')
  const [partialMinLen, setPartialMinLen] = useState(2)
  const [opts, setOpts] = useState<Record<NormalizationKey, boolean>>({
    strip_bracket_notes: true, normalize_whitespace: true, ignore_case: true, normalize_symbols: true,
  })
  const [symbols, setSymbols] = useState<string[]>(['/', '&', ',', '*'])
  const [busy, setBusy] = useState(false)
  const [messages, setMessages] = useState<{ kind: 'info' | 'warning' | 'error'; text: string; detail?: string }[]>([])
  const [collectionNote, setCollectionNote] = useState('')
  const [outcome, setOutcome] = useState<Outcome>({ show: false, count: 0, rows: [], matches: [], segments: null })

  useEffect(() => { loadMatchingRules().then(r => setSymbols(r.ignored_symbols)).catch(() => undefined) }, [])

  const catOptions = useMemo(() => koSorted(uniqueValues(catalog?.rows ?? [], '상품카테고리')), [catalog])
  const riskOptions = useMemo(() => koSorted(uniqueValues(catalog?.rows ?? [], '리스크 등급')), [catalog])

  // Changing the mode or minimum length hides the result table (invalidate_analysis_result);
  // the highlight preview stays, as in Streamlit.
  const invalidate = () => setOutcome(o => ({ ...o, show: false }))

  const run = useCallback(async (text: string) => {
    setBusy(true); setMessages([]); setCollectionNote('')
    try {
      let approved: ApprovedPartialRules = {}
      try {
        const rules = await loadMatchingRules()
        setSymbols(rules.ignored_symbols)
        approved = rules.approved_partials
      } catch { /* the analysis itself still reloads the rules server-side */ }
      if (!text.trim()) {
        setOutcome({ show: false, count: 0, rows: [], matches: [], segments: null })
        setMessages([{ kind: 'info', text: '매칭된 키워드가 없습니다.' }])
        return
      }
      const input: AnalysisInput = {
        analysis_id: crypto.randomUUID(), text, mode, partial_min_len: mode === 'partial' ? partialMinLen : 2,
        ...opts, categories, risks,
      }
      const result = await analyzeText(input)
      if (result.unmatched_collection_pending) {
        addPending(input)
        setMessages(m => [...m, { kind: 'warning', text: '미매칭 후보를 DB에 저장하지 못했습니다. 수집 저장 재시도로 다시 저장하세요.' }])
      } else {
        setCollectionNote('미매칭 후보 수집을 완료했습니다.')
      }
      const fresh = (await reloadCatalog()) ?? catalog
      if (!fresh?.rows.length) {
        setOutcome({ show: false, count: 0, rows: [], matches: [], segments: null })
        setMessages(m => [...m, { kind: 'info', text: '키워드가 없습니다. 먼저 추가하세요.' }])
        return
      }
      if (!result.matches.length) {
        setOutcome({ show: false, count: 0, rows: [], matches: [], segments: null })
        setMessages(m => [...m, { kind: 'info', text: '매칭된 키워드가 없습니다.' }])
        return
      }
      const uniqueCodes = [...new Set(result.matches.map(m => String(m.kwd_no ?? '').trim()).filter(Boolean))]
      const byCode = new Map(fresh.rows.map(r => [String(r.kwd_no).trim(), r]))
      const apiRows = new Map(result.unique_keyword_rows.map(r => [String(r.kwd_no).trim(), r]))
      const rows = sortForDisplay(uniqueCodes.map(code => {
        const base = byCode.get(code) ?? apiRows.get(code) ?? ({ kwd_no: code } as KeywordRow)
        return Object.fromEntries(fresh.columns.map(c => [c, base[c] ?? ''])) as KeywordRow
      }))
      const segments = buildSegments(text, result.matches, {
        catalogRows: fresh.rows, columns: fresh.columns, mode, partialMinLen: input.partial_min_len, approvedPartials: approved,
      })
      setOutcome({ show: true, count: uniqueCodes.length, rows, matches: result.matches, segments })
    } catch (error) {
      setMessages(m => [...m, { kind: 'error', text: '오류 발생 (상세):', detail: errorText(error) }])
    } finally {
      setBusy(false)
    }
  }, [mode, partialMinLen, opts, categories, risks, addPending, reloadCatalog, catalog])

  // OCR → "OCR 후보 텍스트 분석 및 하이라이트 미리보기" switches here and runs once.
  useEffect(() => {
    if (autoRun && tab === 'analysis' && !busy) { setAutoRun(false); void run(analysisText) }
  }, [autoRun, tab, busy, run, analysisText, setAutoRun])

  const columns = catalog?.columns ?? []
  const resultColumns = columns.map(c => ({
    key: c, label: displayHeader(c),
    render: (r: KeywordRow) => (DATETIME_COLUMNS.has(c) ? formatDatetime(r[c]) : r[c] ?? ''),
  }))

  return (
    <div>
      <div className="analysis-text-input">
      <TextArea label="스크립트 입력" value={analysisText} onChange={setAnalysisText} maxLength={20000} height={180} />
      </div>
      <hr />
      <h3>분석 실행</h3>
      <Expander title="사전 필터 (선택)" defaultOpen>
        <div className="row" style={{ alignItems: 'flex-start' }}>
          <div className="col"><MultiSelect label="상품카테고리" value={categories} options={catOptions} onChange={setCategories} /></div>
          <div className="col"><MultiSelect label="리스크 등급" value={risks} options={riskOptions} onChange={setRisks} /></div>
          <div className="col">
            <Radio label="키워드 매칭 방식" value={mode} options={MODES} format={m => MODE_LABELS[m]}
              optionHelp={m => numberedHelp(MODE_DETAILS[m])} onChange={m => { setMode(m); invalidate() }} />
            {mode === 'partial' && (
              <NumberInput label="최소 일치 글자수" value={partialMinLen} min={2} max={20} help={numberedHelp(PARTIAL_LEN_HELP)}
                onChange={v => { setPartialMinLen(v); invalidate() }} />
            )}
            <Expander title="키워드 매칭 옵션">
              {NORMALIZATION_OPTIONS.map(([key, label, description]) => (
                <Checkbox key={key} label={label} help={numberedHelp(description)} checked={opts[key]}
                  onChange={v => setOpts(o => ({ ...o, [key]: v }))} />
              ))}
              <div className="caption">옵션은 텍스트 분석하기를 눌러 적용하세요.</div>
              {mode === 'exact' && !opts.strip_bracket_notes && (
                <Alert kind="info">{'현재는 괄호까지 포함한 등록명을 찾습니다.\n\n안티에이징(anti-aging)을 안티에이징으로에서도 찾으려면 괄호 설명 제외를 켜세요.'}</Alert>
              )}
            </Expander>
            <div className="caption">현재 선택한 매칭방식&매칭옵션<Help text={rulesSummary(mode, partialMinLen, opts, symbols)} /></div>
          </div>
        </div>
      </Expander>
      <div className="caption">미매칭 표현은 분석할 때마다 자동 수집됩니다. 원문·이미지·계정 정보는 후보 통계에 저장하지 않습니다.</div>
      <div className="mt"><Button primary onClick={() => run(analysisText)} disabled={busy}>텍스트 분석하기</Button></div>
      {busy && <Spinner text="분석 중입니다." />}
      {collectionNote && <div className="caption">{collectionNote}</div>}
      {messages.map((m, i) => (
        <div key={i}>
          <Alert kind={m.kind}>{m.text}</Alert>
          {m.detail && <pre style={{ background: 'var(--input-bg)', padding: '.75rem', borderRadius: 8, whiteSpace: 'pre-wrap' }}>{m.detail}</pre>}
        </div>
      ))}

      {outcome.show && outcome.rows.length > 0 && (
        <>
          <Alert kind="success">{`총 ${outcome.count}건의 키워드가 발견되었습니다.`}</Alert>
          <DataTable rows={outcome.rows} columns={resultColumns} rowKey={r => String(r.kwd_no)} />
          <div className="mt">
            <Button onClick={() => downloadCsv('analysis_results.csv', CSV_COLUMNS, outcome.matches.map(m => ({
              kwd_no: m.kwd_no ?? '', '키워드명': m.term, '상품카테고리': m.category, '리스크 등급': m.risk,
              '리스크 등급별 세부 심의기준': m.detail, start: m.start, end: m.end,
            })))}>분석 결과 CSV 다운로드</Button>
          </div>
        </>
      )}

      <hr className="analysis-section-separator" />
      <h3>하이라이트 미리보기<Help text={numberedHelp(HIGHLIGHT_HELP)} /></h3>
      {outcome.segments && <HighlightPreview segments={outcome.segments} />}

      <hr className="analysis-section-separator" />
      <h4>🧰 리스트 필터</h4>
      <KeywordList rows={catalog?.rows ?? []} columns={columns} />
    </div>
  )
}
