import { useEffect, useMemo, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { ApiError, askRegulation, askRegulationLegacy, deleteRegulationThread, downloadRegulationDocumentOriginal, listRegulationThreads, loadRegulationDocumentFullText, loadRegulationThread, loadRegulationUsage, type RegulationConversationMessage, type RegulationScope, type RegulationThread } from '../lib/api.ts'
import { koSorted, pySorted, uniqueValues } from '../lib/catalog.ts'
import type { RegulationResult, RegulationUsageSummary } from '../lib/types.ts'
import { useStore } from '../store.tsx'
import { Alert, Checkbox, DataTable, Dialog, Expander, Help, MultiSelect, Select } from '../components/ui.tsx'
import { RegulationDocuments } from './RegulationDocuments.tsx'

type Direction = 'keyword_to_law' | 'law_to_keywords'
type Turn = { question: string; result: RegulationResult; failed?: boolean }
const DIRECTIONS: Direction[] = ['keyword_to_law', 'law_to_keywords']
const DIRECTION_LABELS: Record<Direction, string> = {
  keyword_to_law: '광고 문구·키워드에서 법령 찾기',
  law_to_keywords: '법령·조항에서 등록 키워드 찾기',
}
const MATCH_COLUMNS = ['kwd_no', '키워드명', '상품카테고리', '리스크 등급', '대체키워드', '리스크 등급별 검토 의견']
type SearchScope = Exclude<RegulationScope, 'all'>
const SCOPES: SearchScope[] = ['law', 'internal', 'keyword']
const SCOPE_LABELS: Record<RegulationScope, string> = { all: '통합 검색', law: '국가법령정보센터', internal: '사내 규정 문서', keyword: '키워드 DB' }
const ALL_SCOPES: SearchScope[] = ['law', 'internal', 'keyword']
const scopeLabel = (mode: string) => {
  const selected = mode.split(',').filter((scope): scope is SearchScope => SCOPES.includes(scope as SearchScope))
  if (mode === 'all' || (selected.length === SCOPES.length && new Set(selected).size === SCOPES.length)) return SCOPE_LABELS.all
  return selected.length ? selected.map(scope => SCOPE_LABELS[scope]).join(' + ') : SCOPE_LABELS[mode as RegulationScope] ?? mode
}
const METHOD_LABELS: Record<string, string> = { hybrid: 'Kiwi·전문·유사 문자열·의미', lexical_fuzzy: 'Kiwi·전문·유사 문자열', lexical_fuzzy_embedding_unavailable: 'Kiwi·전문·유사 문자열 (의미 검색 장애)', lexical: '전문', fuzzy: '유사 문자열', semantic: '의미', official_web: '\uACF5\uC2DD \uC6F9 \uCD94\uAC00 \uAC80\uC0C9' }

function SearchModeHelp() {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    if (!open) return
    const closeOutside = (event: PointerEvent) => {
      if (!ref.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('pointerdown', closeOutside)
    return () => document.removeEventListener('pointerdown', closeOutside)
  }, [open])
  return <button ref={ref} type="button" className="search-mode-help-trigger" aria-label="검색 모드별 사용 기법과 예시"
    aria-expanded={open} onClick={event => { event.preventDefault(); event.stopPropagation(); setOpen(value => !value) }}>
    <span aria-hidden>?</span>
    <span className={`search-mode-tooltip${open ? ' open' : ''}`} role="tooltip">
      <strong>검색 모드별 범위와 기법</strong>
      <span className="search-mode-tooltip-note">검색 모드는 여러 범위를 함께 선택할 수 있습니다. 세 개별 범위를 모두 선택하면 기존 통합 검색과 같습니다.</span>
      <span className="search-mode-tooltip-item"><b>통합 검색</b><br /><b>사용:</b> 국가법령정보센터 검색 + 사내 문서 하이브리드 검색 + 키워드 DB 검색. 키워드 의미 후보는 별도 옵션을 켰을 때 추가됩니다.<br /><b>사용하지 않음:</b> 모든 문서 전체를 읽거나 검색 점수로 위험도를 판정하지 않습니다.<br /><b>예:</b> ‘미백 광고 문구’를 법령·사내 지침·등록 키워드 범위에서 함께 찾습니다.</span>
      <span className="search-mode-tooltip-item"><b>국가법령정보센터</b><br /><b>사용:</b> 질문의 단어로 법령·행정규칙·판례를 검색합니다. 질문 방향을 ‘법령에서 키워드 찾기’로 바꾸면 법령 조문을 키워드 DB와 대조합니다.<br /><b>사용하지 않음:</b> 사내 문서 하이브리드 검색은 하지 않습니다.<br /><b>예:</b> ‘미백 표시 광고’를 검색해 관련 공식 법령과 판례를 찾습니다.</span>
      <span className="search-mode-tooltip-item"><b>사내 규정 문서</b><br /><b>사용:</b> 기준일·카테고리에 맞는 승인 문서에서 Kiwi 토큰·전문·문자열 유사도를 결합해 관련 문단을 찾습니다. 임베딩 의미 검색은 서버 설정과 문서 색인에 따라 추가됩니다.<br /><b>사용하지 않음:</b> 국가법령정보센터 및 키워드 DB 검색은 하지 않습니다.<br /><b>예:</b> ‘미백 표현 검토’를 검색해 적용 중인 사내 광고 지침의 관련 문단을 찾습니다.</span>
      <span className="search-mode-tooltip-item"><b>키워드 DB</b><br /><b>사용:</b> 질문 문구와 등록 키워드의 문자열 일치를 찾습니다. 의미가 비슷한 키워드 후보는 별도 임베딩 옵션을 켰을 때 추가됩니다.<br /><b>사용하지 않음:</b> 법령 및 사내 규정 문서를 검색하지 않습니다.<br /><b>예:</b> ‘피부를 환하게’를 검색해 등록어 ‘미백’과 일치하거나 유사한 후보를 찾습니다.</span>
      <span className="search-mode-tooltip-note">AI 근거 검토는 별도 옵션입니다. 켜져 있고 서버에 모델이 설정된 경우에만 검색 결과를 LLM이 검토합니다. 사내 문서 검색 결과는 관련도순 최대 5개 문단입니다.</span>
    </span>
  </button>
}

type HighlightTerms = { exact: string[]; partial: string[]; relaxed: boolean }
const escapeRegExp = (term: string) => term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const hasExactTerm = (text: string, term: string) =>
  new RegExp(`(?<![\\p{L}\\p{N}])${escapeRegExp(term)}(?![\\p{L}\\p{N}])`, 'iu').test(text)

function matchedQuestionTerms(question: string, matches: Record<string, unknown>[], catalogTerms: string[]): HighlightTerms {
  const relaxed = /(?:부분\s*일치|일치율.{0,12}(?:완화|낮춰|줄여)|(?:완화|낮춰|줄여).{0,12}(?:일치율|매칭|검색)|포함\s*(?:검색|일치|매칭)|퍼지\s*검색|fuzzy|(?:유사|비슷한|비슷하게)\s*(?:표현|단어|키워드|검색|것))/iu.test(question)
  const questionForTerms = question
    .replace(/부분\s*일치(?:\s*조건(?:값)?)?/giu, ' ')
    .replace(/일치율.{0,12}(?:완화|낮춰|줄여)(?:\S*)?/giu, ' ')
    .replace(/(?:완화|낮춰|줄여).{0,12}(?:일치율|매칭|검색)(?:\S*)?/giu, ' ')
    .replace(/(?:포함\s*(?:검색|일치|매칭)|퍼지\s*검색|fuzzy|(?:유사|비슷한|비슷하게)\s*(?:표현|단어|키워드|검색|것))/giu, ' ')
  const foldedQuestion = questionForTerms.toLocaleLowerCase()
  const commonWords = new Set([
    '광고', '문구', '키워드', '관련', '내용', '법령', '규정', '문서', '검색', '찾아',
    '찾아줘', '찾아주세요', '알려줘', '알려주세요', '해주세요', '해줘', '검토',
    '확인', '비교', '설명', '어떤', '무엇', '무슨', '어떻게', '이것', '해당',
    '대해', '대해서', '현재', '그럼', '질문', '답변', '부분', '포함', '되어',
    '되나요', '되는지', '있나요', '있는지', '인가요', '입니다', '인가',
    '부분일치', '일치율', '완화', '매칭', '방식', '조건', '조건값', '포함',
    '유사', '유사도', '비슷한', '비슷하게', '보여줘', '보여주세요',
  ])
  const queryWords = questionForTerms.match(/[가-힣A-Za-z0-9]{2,}/g) ?? []
  const queryTerms = queryWords.flatMap(term => {
    const stem = term.replace(/(으로부터|에게서|에서|으로|에게|한테|까지|부터|보다|처럼|만큼|이랑|하고|은|는|이|가|을|를|에|로|와|과|도|만|의|께)$/u, '')
    return [term, stem]
  }).filter(term => term.length > 1 && !commonWords.has(term.toLocaleLowerCase()))
  const candidates = [
    ...matches.map(row => String(row[MATCH_COLUMNS[1]] ?? row.keyword ?? row.term ?? '').trim()),
    ...catalogTerms,
  ]
  const exactCatalogTerms = candidates.filter(term => term.length > 1 && hasExactTerm(foldedQuestion, term))
  const exact = [...new Set([...exactCatalogTerms, ...queryTerms])].sort((a, b) => b.length - a.length)
  const partial = relaxed
    ? [...new Set(catalogTerms.filter(term => {
        const folded = term.trim().toLocaleLowerCase()
        return folded.length > 1 && !exact.some(exactTerm => exactTerm.toLocaleLowerCase() === folded)
          && (foldedQuestion.includes(folded)
            || queryTerms.some(queryTerm => queryTerm.toLocaleLowerCase().includes(folded)
              || folded.includes(queryTerm.toLocaleLowerCase())))
      }))].sort((a, b) => b.length - a.length)
    : []
  return { exact, partial, relaxed }
}

function HighlightedText({ text, terms }: { text: string; terms: HighlightTerms }) {
  const exact = terms.exact.filter(Boolean)
  const partial = terms.partial.filter(Boolean)
  if (!exact.length && !partial.length) return <>{text}</>
  const particles = '(?:으로부터|에게서|에서|으로|에게|한테|까지|부터|보다|처럼|만큼|이랑|하고|은|는|이|가|을|를|에|로|와|과|도|만|의|께)?'
  const exactPattern = exact.length
    ? `(?<![\\p{L}\\p{N}])(${exact.map(escapeRegExp).join('|')})(?=${particles}(?![\\p{L}\\p{N}]))`
    : ''
  const partialPattern = partial.length ? `(${partial.map(escapeRegExp).join('|')})` : ''
  const matcher = new RegExp([exactPattern, partialPattern].filter(Boolean).join('|'), 'giu')
  const exactSet = new Set(exact.map(term => term.toLocaleLowerCase()))
  const output: React.ReactNode[] = []
  let cursor = 0
  for (const match of text.matchAll(matcher)) {
    const value = match[1] ?? match[2]
    if (!value) continue
    const start = match.index ?? 0
    if (start > cursor) output.push(text.slice(cursor, start))
    const isExact = exactSet.has(value.toLocaleLowerCase())
    output.push(<mark className={isExact ? 'chat-keyword-highlight' : 'chat-keyword-highlight partial'} key={`${start}-${value}`}>{value}</mark>)
    cursor = start + value.length
  }
  if (cursor < text.length) output.push(text.slice(cursor))
  return <>{output}</>
}

function MarkdownText({ text, highlightTerms }: { text: string; highlightTerms: HighlightTerms }) {
  const highlight = (value: string) => <HighlightedText text={value} terms={highlightTerms} />
  return <div>{text.split(/\n{2,}/).map((para, i) => <p key={i} style={{ margin: '0 0 .6rem' }}>{para.split(/(\*\*[^*]+\*\*)/g).map((part, j) => part.startsWith('**') && part.endsWith('**') ? <strong key={j}>{highlight(part.slice(2, -2))}</strong> : <span key={j}>{highlight(part)}</span>)}</p>)}</div>
}

export function ChatTab() {
  const { catalog, ocr, analysisText, isAdmin } = useStore()
  const [history, setHistory] = useState<Turn[]>([])
  const [direction, setDirection] = useState<Direction>('keyword_to_law')
  const [scope, setScope] = useState<SearchScope[]>(['internal'])
  const [useLlm, setUseLlm] = useState(false)
  const [includeKeywordCandidates, setIncludeKeywordCandidates] = useState(false)
  const [asOf, setAsOf] = useState(new Date().toISOString().slice(0, 10))
  const [threadId, setThreadId] = useState<string | null>(null)
  const [threads, setThreads] = useState<RegulationThread[]>([])
  const [corpusReady, setCorpusReady] = useState<boolean | null>(null)
  const [question, setQuestion] = useState('')
  const [ocrTerms, setOcrTerms] = useState<string[]>([])
  const [includeOcr, setIncludeOcr] = useState(false)
  const [includeText, setIncludeText] = useState(false)
  const [category, setCategory] = useState('')
  const [warning, setWarning] = useState('')
  const [busy, setBusy] = useState(false)
  const [usageSummary, setUsageSummary] = useState<RegulationUsageSummary | null>(null)
  const [fullEvidence, setFullEvidence] = useState<{ id: string; label: string; version: string; text: string; terms: HighlightTerms } | null>(null)
  const [originalDocument, setOriginalDocument] = useState<{ title: string; version: string; originalName: string; text: string; terms: HighlightTerms } | null>(null)
  const [loadingOriginalId, setLoadingOriginalId] = useState('')
  const [downloadingOriginalId, setDownloadingOriginalId] = useState('')
  const [originalDocumentError, setOriginalDocumentError] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)
  const directionEnabled = scope.includes('law')
  const contextOptionsEnabled = scope.some(item => item !== 'law') || direction === 'law_to_keywords' || useLlm
  const categoryEnabled = scope.some(item => item !== 'law') || direction === 'law_to_keywords' || useLlm
  const keywordSemanticsEnabled = scope.includes('keyword') || scope.includes('internal') || (scope.includes('law') && direction === 'law_to_keywords')
  const asOfEnabled = scope.includes('internal') || useLlm
  const ocrOptions = useMemo(() => pySorted(new Set(ocr.candidates.map(c => c.term.trim()).filter(Boolean))), [ocr.candidates])
  const categories = useMemo(() => ['', ...koSorted(uniqueValues(catalog?.rows ?? [], '\uC0C1\uD488\uCE74\uD14C\uACE0\uB9AC'))], [catalog])
  const contextText = contextOptionsEnabled
    ? [...(includeOcr ? ocrTerms.filter(t => ocrOptions.includes(t)) : []), ...(includeText && analysisText.trim() ? [analysisText] : [])].join('\n')
    : ''
  useEffect(() => {
    void listRegulationThreads().then(data => { setThreads(data.items); setCorpusReady(true) }).catch(() => setCorpusReady(false))
    void loadRegulationUsage().then(setUsageSummary).catch(() => setUsageSummary({ available: false }))
  }, [])

  const openThread = async (id: string) => {
    if (!id) { setThreadId(null); setHistory([]); return }
    try {
      const data = await loadRegulationThread(id)
      const restored: Turn[] = []
      for (let i = 0; i + 1 < data.messages.length; i += 2) {
        const user = data.messages[i]
        const assistant = data.messages[i + 1]
        if (user.role === 'user' && assistant.role === 'assistant') restored.push({ question: user.content,
          result: { answer: assistant.content, sources: assistant.evidence as RegulationResult['sources'], keyword_matches: [] } })
      }
      setThreadId(id); setHistory(restored); setWarning('')
    } catch (cause) { setWarning(cause instanceof Error ? cause.message : '대화를 불러오지 못했습니다.') }
  }

  const removeThread = async () => {
    if (!threadId || busy || !window.confirm('선택한 대화와 모든 메시지를 삭제할까요? 삭제 후 복구할 수 없습니다.')) return
    setBusy(true)
    try {
      await deleteRegulationThread(threadId)
      setThreads(current => current.filter(thread => thread.id !== threadId))
      setThreadId(null)
      setHistory([])
      setWarning('')
      void listRegulationThreads().then(data => setThreads(data.items)).catch(() => {})
    } catch (cause) { setWarning(cause instanceof Error ? cause.message : '대화를 삭제하지 못했습니다.') }
    finally { setBusy(false) }
  }

  const submit = async (e?: FormEvent) => {
    e?.preventDefault()
    if (busy) return
    setWarning('')
    const q = question.trim()
    if (q.length < 2 || q.length > 500) { setWarning('질문은 2~500자로 입력해 주세요.'); return }
    if (!scope.length) { setWarning('검색 모드를 하나 이상 선택해 주세요.'); return }
    if (contextText.length > 20000) { setWarning(`연결 자료가 ${contextText.length.toLocaleString()}자입니다. 최대 20,000자까지 연결할 수 있습니다.`); return }
    setBusy(true)
    const conversation: RegulationConversationMessage[] = []
    for (const turn of history.filter(item => !item.failed).slice(-6)) {
      const pair = [
        { role: 'user' as const, content: turn.question },
        { role: 'assistant' as const, content: turn.result.answer || '' },
      ].filter(item => item.content.length > 0)
      if (conversation.reduce((total, item) => total + item.content.length, 0) + pair.reduce((total, item) => total + item.content.length, 0) > 20000) break
      conversation.push(...pair)
    }
    let result: RegulationResult
    let failed = false
    try {
      const requestedScope = scope.length === SCOPES.length ? 'all'
        : scope.length === 1 ? scope[0] : scope
      result = corpusReady
        ? await askRegulation({ direction, scope: requestedScope, use_llm: useLlm,
                                include_keyword_candidates: includeKeywordCandidates,
                                thread_id: threadId, as_of: asOf,
                                query: q, context_text: contextText, category, conversation_history: conversation })
        : await askRegulationLegacy({ direction, query: q, context_text: contextText,
                                     category, conversation_history: conversation })
      if (result.usage_summary) setUsageSummary(result.usage_summary)
      if (result.thread_id) { setThreadId(result.thread_id); void listRegulationThreads().then(data => setThreads(data.items)).catch(() => {}) }
    } catch (error) {
      failed = true
      const answer = error instanceof ApiError && error.status === 0
        ? 'API 서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.'
        : error instanceof Error ? error.message.slice(0, 500) || '답변을 가져오지 못했습니다.' : '답변을 가져오지 못했습니다.'
      result = { answer, sources: [], keyword_matches: [] }
    }
    setHistory(current => [...current, { question: q, result, failed }])
    setQuestion('')
    setBusy(false)
    requestAnimationFrame(() => bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }))
  }

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void submit() }
  }

  return (
    <section className="chat-workspace">
      <header className="chat-header"><div><h2>심의 Chat-bot</h2><span>공식 자료를 바탕으로 키워드·법령 문의를 이어서 상담합니다.</span></div></header>
      <div className="chat-controls">
        {corpusReady && <div className="chat-saved-threads"><label><span className="chat-control-title">저장된 대화</span><select value={threadId ?? ''} onChange={e => void openThread(e.target.value)} disabled={busy}><option value="">새 대화</option>{threads.map(thread => <option key={thread.id} value={thread.id}>{new Date(thread.updated_at).toLocaleString('ko-KR')} · {scopeLabel(thread.mode)}</option>)}</select></label><button type="button" className="chat-thread-delete" onClick={() => void removeThread()} disabled={!threadId || busy}>선택 대화 삭제</button></div>}
        {corpusReady && <div className="chat-scope-bar"><div className="chat-scope-picker">
          <div className="chat-scope-label">
            <span className="chat-scope-heading"><span className="chat-control-title">검색 모드</span><SearchModeHelp /></span>
            <button type="button" className="btn small chat-scope-all" onClick={() => setScope(scope.length === SCOPES.length ? [] : ALL_SCOPES)} disabled={busy}>
              {scope.length === SCOPES.length ? '선택 해제' : '전체 선택'}
            </button>
          </div>
          <MultiSelect value={scope} options={SCOPES} optionLabels={SCOPE_LABELS}
            onChange={next => { setScope(next as SearchScope[]); if (!next.includes('law')) setDirection('keyword_to_law') }}
            placeholder="검색 모드 선택" />
        </div></div>}
        {corpusReady === false && <div className="chat-warning" role="alert">검색 모드를 불러오지 못했습니다. API 연결을 확인한 뒤 새로고침해 주세요.</div>}
        <details className="chat-options"><summary className="chat-control-title">검색 옵션</summary>
          <div className="chat-options-body">
            <div className="chat-options-grid">
              <Select label={<>질문 방향<Help text={"광고 문구·키워드에서 법령 찾기\n사용: 입력한 광고 문구나 키워드로 법령·행정규칙·판례를 검색합니다.\n예: ‘미백 광고 문구’ → 관련 법령과 판례 검색\n\n법령에서 등록 키워드 찾기\n사용: 법령명과 조항을 검색해 조문 본문을 현재 키워드 DB와 대조합니다.\n예: ‘화장품법 제13조’ → 조문에 포함된 등록 키워드 검색"} /></>} value={direction} options={DIRECTIONS} format={d => DIRECTION_LABELS[d]} onChange={setDirection} disabled={!directionEnabled} />
              <Select label="상품 카테고리" value={category} options={categories} format={c => c || '전체 카테고리'} onChange={setCategory} disabled={!categoryEnabled} />
              {corpusReady && <label className="chat-option-date">사내문서 기준일<Help text="선택한 날짜에 유효한 사내 문서를 검색합니다. 문서 등록일 기준이 아닙니다. 예: 2026-11-14를 선택하면 해당 날짜가 문서의 시행일~종료일 안에 드는 승인 문서를 찾습니다." /><input type="date" value={asOf} onChange={e => setAsOf(e.target.value)} disabled={!asOfEnabled} /></label>}
              {ocrOptions.length > 0 && <MultiSelect label={"\uD604\uC7AC OCR \uBD84\uC11D \uD0A4\uC6CC\uB4DC"} value={ocrTerms} options={ocrOptions} onChange={setOcrTerms} disabled={!contextOptionsEnabled} />}
              <div className="chat-option-checks">
                {corpusReady && <Checkbox label={"AI \uADFC\uAC70 \uAC80\uD1A0 \uBC0F \uBD80\uC871\uD55C \uACF5\uC2DD \uCD9C\uCC98 \uCD94\uAC00 \uAC80\uC0C9"} help="검색된 근거를 AI가 검토하고, 근거가 부족하면 공식 출처를 추가로 검색합니다. 켜면 OpenAI 모델을 호출해 토큰을 사용합니다. 예: 사내 지침과 법령 내용이 다르면 차이를 검토하고 공식 자료를 더 찾습니다." checked={useLlm} onChange={setUseLlm} />}
                {corpusReady && <Checkbox label="임베딩 기반 의미 유사도 검색 (위험 판정에 반영하지 않음)" help="문구와 키워드의 의미를 벡터로 비교해 비슷한 등록 키워드 후보를 찾습니다. 위험 등급이나 자동 판정은 바꾸지 않습니다. 예: ‘피부를 환하게’와 ‘미백’처럼 표현이 달라도 후보로 찾을 수 있습니다. 서버 설정에 따라 임베딩 API를 호출하며 별도 사용량이 발생할 수 있습니다." checked={includeKeywordCandidates} onChange={setIncludeKeywordCandidates} disabled={!keywordSemanticsEnabled} />}
                <Checkbox label={"\uD604\uC7AC OCR \uBD84\uC11D \uD0A4\uC6CC\uB4DC \uAC80\uC0C9 \uD3EC\uD568"} help="현재 OCR 분석에서 추출한 키워드를 질문 문맥에 추가해 사내 문서·키워드 검색에 함께 사용합니다. 예: 질문이 ‘표현을 검토해줘’이고 OCR 키워드가 ‘미백’이면 미백 관련 근거와 키워드도 찾습니다." checked={includeOcr} onChange={setIncludeOcr} disabled={ocrOptions.length === 0 || !contextOptionsEnabled} />
                <Checkbox label={"\uD604\uC7AC \uD14D\uC2A4\uD2B8 \uBD84\uC11D \uD0A4\uC6CC\uB4DC \uAC80\uC0C9 \uD3EC\uD568"} help="현재 텍스트 분석 화면의 문구 전체를 질문 문맥에 추가해 사내 문서·키워드 검색에 함께 사용합니다. 예: 질문이 ‘이 광고를 검토해줘’이면 분석 중인 광고 문구도 검색 대상으로 포함합니다." checked={includeText} onChange={setIncludeText} disabled={!contextOptionsEnabled} />
              </div>
            </div>
            <div className={contextText.length > 20000 ? 'chat-context-count over' : 'chat-context-count'}>연결 자료 {contextText.length.toLocaleString()} / 20,000자</div>
          </div>
        </details>
        {isAdmin && corpusReady && <RegulationDocuments />}
      </div>
      <main className="chat-thread" aria-live="polite">
        {history.length === 0 && <div className="chat-welcome"><div className="chat-bot-avatar">AI</div><div className="chat-bubble assistant"><strong>안녕하세요!</strong><br />법령 근거와 키워드 정보를 확인해 드릴게요. 궁금한 내용을 입력해 주세요.</div></div>}
        {history.map((turn, i) => {
          const highlightTerms = matchedQuestionTerms(
            turn.question,
            turn.result.keyword_matches ?? [],
            (catalog?.rows ?? []).map(row => String(row[MATCH_COLUMNS[1]] ?? '')),
          )
          const sources = turn.result.sources ?? []
          const sourceKeywords = [...new Set((turn.result.keyword_matches ?? [])
            .map(row => String(row[MATCH_COLUMNS[1]] ?? row.keyword ?? row.term ?? '').trim())
            .filter(Boolean))]
          const sourceGroups = sourceKeywords.map(keyword => ({
            keyword,
            sources: sources.filter(source => `${source.label}\n${source.text}`.toLocaleLowerCase().includes(keyword.toLocaleLowerCase())),
          })).filter(group => group.sources.length > 0)
          const assignedSources = new Set(sourceGroups.flatMap(group => group.sources))
          const groupedSources = sourceGroups.length > 0
            ? [...sourceGroups, ...(sources.some(source => !assignedSources.has(source)) ? [{ keyword: '기타 출처', sources: sources.filter(source => !assignedSources.has(source)) }] : [])]
            : [{ keyword: '', sources }]
          const renderSource = (source: typeof sources[number], j: number) => {
            const sourceId = String(source.id ?? j + 1)
            const isInternal = sourceId.startsWith('INT')
            return <div className="chat-source" key={`${sourceId}-${j}`}>
              <div className="chat-source-heading"><strong>[{sourceId}] <HighlightedText text={source.label} terms={highlightTerms} /></strong>
                {isInternal && <button type="button" className="btn small" onClick={() => setFullEvidence({ id: sourceId, label: source.label, version: String(source.version ?? ''), text: String(source.text ?? ''), terms: highlightTerms })}>크게 보기</button>}
                {isInternal && typeof source.document_id === 'string' && <button type="button" className="btn small" disabled={loadingOriginalId === source.document_id} onClick={() => {
                  const documentId = source.document_id as string
                  setLoadingOriginalId(documentId)
                  setOriginalDocumentError('')
                  void loadRegulationDocumentFullText(documentId).then(document => setOriginalDocument({
                    title: document.title, version: document.version, originalName: document.original_name,
                    text: document.text, terms: highlightTerms,
                  })).catch(error => setOriginalDocumentError(error instanceof Error ? error.message : '원문을 불러오지 못했습니다.'))
                    .finally(() => setLoadingOriginalId(''))
                }}>{loadingOriginalId === source.document_id ? '불러오는 중…' : '원문 보기'}</button>}
                {isInternal && typeof source.document_id === 'string' && <button type="button" className="btn small" disabled={downloadingOriginalId === source.document_id} onClick={() => {
                  const documentId = source.document_id as string
                  setDownloadingOriginalId(documentId)
                  setOriginalDocumentError('')
                  void downloadRegulationDocumentOriginal(documentId).catch(error => setOriginalDocumentError(error instanceof Error ? error.message : '원본 파일을 다운로드하지 못했습니다.'))
                    .finally(() => setDownloadingOriginalId(''))
                }}>{downloadingOriginalId === source.document_id ? '다운로드 중…' : '다운로드'}</button>}
              </div>
              {typeof source.url === 'string' && source.url && <a href={source.url} target="_blank" rel="noreferrer">원문 열기 ↗</a>}{typeof source.version === 'string' && source.version && <small> · 버전 {source.version}</small>}<pre><HighlightedText text={String(source.text ?? '')} terms={highlightTerms} /></pre>
            </div>
          }
          return <article className="chat-turn" key={i}>
          <div className="chat-msg user"><div className="chat-bubble user">{turn.question}</div></div>
          <div className="chat-msg assistant"><div className="chat-bot-avatar">AI</div><div className={`chat-bubble assistant${turn.failed ? ' failed' : ''}`}>
            {turn.result.recommendation_only && <small className="caption">{'AI \uAD8C\uACE0\uC548 \u00B7 \uCD5C\uC885 \uD310\uC815 \uC544\uB2D8'}</small>}
            <MarkdownText text={turn.result.answer || '검색 결과가 없습니다.'}
              highlightTerms={highlightTerms} />
            {highlightTerms.relaxed && <small className="chat-highlight-mode">완화 일치: 부분 문자열 포함 {highlightTerms.partial.length ? `· 추가 강조: ${highlightTerms.partial.join(' · ')}` : '· 추가 부분 일치 항목 없음'}</small>}
            {(turn.result.search_methods ?? []).length > 0 && <small>{'\uAC80\uC0C9 \uBC29\uC2DD: '}{(turn.result.search_methods ?? []).map(method => METHOD_LABELS[method] ?? method).join(', ')}</small>}
            {Boolean(turn.result.administrator_review) && <Alert kind="warning">근거가 상충하거나 충분히 검증되지 않았습니다. 법적 판단은 관리자에게 문의해 주세요.</Alert>}
            {turn.result.keyword_matches?.length > 0 && <Expander title="관련 키워드 보기"><DataTable rows={turn.result.keyword_matches as Record<string, unknown>[]} rowKey={(_, j) => String(j)} columns={MATCH_COLUMNS.map(key => ({ key, render: row => <HighlightedText text={String(row[key] ?? '')} terms={highlightTerms} /> }))} showIndex={false} /></Expander>}
            {(turn.result.related_candidates ?? []).length > 0 && <Expander title="임베딩 기반 의미 유사 후보 · 심의자 검토용"><DataTable rows={turn.result.related_candidates as unknown as Record<string, unknown>[]} rowKey={(_, j) => String(j)} columns={[{ key: 'kwd_no' }, { key: 'keyword', render: row => <HighlightedText text={String(row.keyword ?? '')} terms={highlightTerms} /> }, { key: 'similarity' }]} showIndex={false} /></Expander>}
            {sources.length > 0 && <div className="chat-sources"><Expander title={`${sources.some(source => String(source.id ?? '').startsWith('WEB')) ? '\uCD94\uAC00 \uAC80\uC0C9 \uCD9C\uCC98\uC640 \uADFC\uAC70' : '\uAC80\uC0C9 \uCD9C\uCC98 \uBC0F \uADFC\uAC70'} (${sources.length})`}>
              {groupedSources.map((group, groupIndex) => <section className="chat-source-group" key={group.keyword || `ungrouped-${groupIndex}`}>
                {group.keyword && <h4><HighlightedText text={group.keyword} terms={highlightTerms} /></h4>}
                {group.sources.map((source, j) => renderSource(source, j))}
              </section>)}
            </Expander></div>}
          </div></div>
          </article>
        })}
        {busy && <div className="chat-msg assistant"><div className="chat-bot-avatar">AI</div><div className="chat-bubble assistant chat-thinking">답변을 확인하고 있습니다…</div></div>}
        <div ref={bottomRef} />
      </main>
      <form className="chat-composer" onSubmit={submit}><div className="chat-input-wrap">
        <textarea value={question} onChange={e => setQuestion(e.target.value.slice(0, 500))} onKeyDown={onKeyDown} maxLength={500} rows={1} disabled={busy} placeholder="메시지를 입력하세요…" aria-label="질문 입력" />
        <span className={question.length > 500 ? 'over' : ''}>{question.length}/500</span>
      </div><button className="chat-send" type="submit" disabled={busy || question.trim().length < 2} aria-label="질문 전송">➤</button></form>
      {usageSummary && <div className="chat-usage-caption" aria-live="polite">
        {usageSummary.available
          ? <>
              심의챗봇 이번 달 OpenAI 누적 {Number(usageSummary.total_tokens ?? 0).toLocaleString()} tokens
              {usageSummary.estimated_cost_usd == null
                ? ' · 비용 요율 설정 필요'
                : ` · 예상 비용 $${usageSummary.estimated_cost_usd.toFixed(4)}`}
              {usageSummary.budget_usd == null
                ? ' · 월 예산 미설정'
                : usageSummary.remaining_budget_usd == null
                  ? ' · 예상 비용을 계산할 수 없음'
                  : ` · 남은 예산 $${usageSummary.remaining_budget_usd.toFixed(2)} / $${usageSummary.budget_usd.toFixed(2)}`}
              <span> · 토큰 요금 추정치이며 웹 검색 도구 요금은 제외</span>
            </>
          : 'OpenAI 사용량을 읽을 수 없습니다. 서버 DB 마이그레이션 적용을 확인해 주세요.'}
      </div>}
      {fullEvidence && <Dialog title={`[${fullEvidence.id}] ${fullEvidence.label}`} onClose={() => setFullEvidence(null)} wide>
        <div className="chat-evidence-full">
          {fullEvidence.version && <small>버전 {fullEvidence.version}</small>}
          <pre><HighlightedText text={fullEvidence.text} terms={fullEvidence.terms} /></pre>
        </div>
      </Dialog>}
      {originalDocument && <Dialog title={`원문 보기 · ${originalDocument.title}`} onClose={() => setOriginalDocument(null)} wide>
        <div className="chat-evidence-full">
          <small>{originalDocument.originalName}{originalDocument.version && ` · 버전 ${originalDocument.version}`}</small>
          <pre><HighlightedText text={originalDocument.text} terms={originalDocument.terms} /></pre>
        </div>
      </Dialog>}
      {originalDocumentError && <Dialog title="원문 작업을 완료하지 못했습니다" onClose={() => setOriginalDocumentError('')}>
        <p role="alert">{originalDocumentError}</p>
      </Dialog>}
      {warning && <div className="chat-warning" role="alert">{warning}</div>}
      {history.length > 0 && <button className="chat-clear" type="button" onClick={() => { setHistory([]); setThreadId(null) }} disabled={busy}>새 대화</button>}
    </section>
  )
}
