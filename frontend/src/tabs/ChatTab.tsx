import { useEffect, useMemo, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { ApiError, askRegulation, askRegulationLegacy, deleteRegulationThread, listRegulationThreads, loadRegulationThread, loadRegulationUsage, type RegulationConversationMessage, type RegulationScope, type RegulationThread } from '../lib/api.ts'
import { koSorted, pySorted, uniqueValues } from '../lib/catalog.ts'
import type { RegulationResult, RegulationUsageSummary } from '../lib/types.ts'
import { useStore } from '../store.tsx'
import { Alert, Checkbox, DataTable, Expander, MultiSelect, Select } from '../components/ui.tsx'
import { RegulationDocuments } from './RegulationDocuments.tsx'

type Direction = 'keyword_to_law' | 'law_to_keywords'
type Turn = { question: string; result: RegulationResult; failed?: boolean }
const DIRECTIONS: Direction[] = ['keyword_to_law', 'law_to_keywords']
const DIRECTION_LABELS: Record<Direction, string> = {
  keyword_to_law: '광고 문구·키워드에서 법령 찾기',
  law_to_keywords: '법령·조항에서 등록 키워드 찾기',
}
const MATCH_COLUMNS = ['kwd_no', '키워드명', '상품카테고리', '리스크 등급', '대체키워드', '리스크 등급별 검토 의견']
const SCOPES: RegulationScope[] = ['all', 'law', 'internal', 'keyword']
const SCOPE_LABELS: Record<RegulationScope, string> = { all: '통합 검색', law: '국가법령정보센터', internal: '사내 규정 문서', keyword: '키워드 DB' }
const METHOD_LABELS: Record<string, string> = { hybrid: 'Kiwi·전문·유사 문자열·의미', lexical_fuzzy: 'Kiwi·전문·유사 문자열', lexical_fuzzy_embedding_unavailable: 'Kiwi·전문·유사 문자열 (의미 검색 장애)', lexical: '전문', fuzzy: '유사 문자열', semantic: '의미', official_web: '\uACF5\uC2DD \uC6F9 \uCD94\uAC00 \uAC80\uC0C9' }

function MarkdownText({ text }: { text: string }) {
  return <div>{text.split(/\n{2,}/).map((para, i) => <p key={i} style={{ margin: '0 0 .6rem' }}>{para.split(/(\*\*[^*]+\*\*)/g).map((part, j) => part.startsWith('**') && part.endsWith('**') ? <strong key={j}>{part.slice(2, -2)}</strong> : <span key={j}>{part}</span>)}</p>)}</div>
}

export function ChatTab() {
  const { catalog, ocr, analysisText, isAdmin } = useStore()
  const [history, setHistory] = useState<Turn[]>([])
  const [direction, setDirection] = useState<Direction>('keyword_to_law')
  const [scope, setScope] = useState<RegulationScope>('all')
  const [useLlm, setUseLlm] = useState(true)
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
  const [optionsOpen, setOptionsOpen] = useState(false)
  const [warning, setWarning] = useState('')
  const [busy, setBusy] = useState(false)
  const [usageSummary, setUsageSummary] = useState<RegulationUsageSummary | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const ocrOptions = useMemo(() => pySorted(new Set(ocr.candidates.map(c => c.term.trim()).filter(Boolean))), [ocr.candidates])
  const categories = useMemo(() => ['', ...koSorted(uniqueValues(catalog?.rows ?? [], '\uC0C1\uD488\uCE74\uD14C\uACE0\uB9AC'))], [catalog])
  const contextText = [...(includeOcr ? ocrTerms.filter(t => ocrOptions.includes(t)) : []), ...(includeText && analysisText.trim() ? [analysisText] : [])].join('\n')
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
      result = corpusReady
        ? await askRegulation({ direction, scope, use_llm: useLlm,
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
      <header className="chat-header"><div><h2>심의 Chat-bot</h2><span>공식 자료를 바탕으로 키워드·법령 문의를 이어서 상담합니다.</span></div>
        <button className={`chat-options-toggle${optionsOpen ? ' active' : ''}`} onClick={() => setOptionsOpen(open => !open)} aria-expanded={optionsOpen} aria-label="검색 옵션">⚡ 검색 옵션</button>
      </header>
      <div className="chat-controls">
        {corpusReady && <div className="chat-saved-threads"><label>저장된 대화 <select value={threadId ?? ''} onChange={e => void openThread(e.target.value)} disabled={busy}><option value="">새 대화</option>{threads.map(thread => <option key={thread.id} value={thread.id}>{new Date(thread.updated_at).toLocaleString('ko-KR')} · {SCOPE_LABELS[thread.mode as RegulationScope] ?? thread.mode}</option>)}</select></label><button type="button" className="chat-thread-delete" onClick={() => void removeThread()} disabled={!threadId || busy}>선택 대화 삭제</button></div>}
        {corpusReady && <div className="chat-scope-bar"><Select label="검색 모드" value={scope} options={SCOPES} format={s => SCOPE_LABELS[s]} onChange={setScope} /></div>}
        {corpusReady === false && <div className="chat-warning" role="alert">검색 모드를 불러오지 못했습니다. API 연결을 확인한 뒤 새로고침해 주세요.</div>}
        {isAdmin && corpusReady && <RegulationDocuments />}
        {optionsOpen && <div className="chat-options"><div className="chat-options-title">검색 옵션</div>
          <div className="chat-options-grid">
            <Select label="질문 방향" value={direction} options={DIRECTIONS} format={d => DIRECTION_LABELS[d]} onChange={setDirection} />
            <Select label="상품 카테고리" value={category} options={categories} format={c => c || '전체 카테고리'} onChange={setCategory} />
            {corpusReady && <label>사내문서 기준일 <input type="date" value={asOf} onChange={e => setAsOf(e.target.value)} /></label>}
            {ocrOptions.length > 0 && <MultiSelect label={"\uD604\uC7AC OCR \uBD84\uC11D \uD0A4\uC6CC\uB4DC"} value={ocrTerms} options={ocrOptions} onChange={setOcrTerms} />}
            <div className="chat-option-checks">
              {corpusReady && <Checkbox label={"AI \uADFC\uAC70 \uAC80\uD1A0 \uBC0F \uBD80\uC871\uD55C \uACF5\uC2DD \uCD9C\uCC98 \uCD94\uAC00 \uAC80\uC0C9"} checked={useLlm} onChange={setUseLlm} />}
              {corpusReady && <Checkbox label="키워드 의미 관련 후보 표시 (위험 판정에 반영하지 않음)" checked={includeKeywordCandidates} onChange={setIncludeKeywordCandidates} disabled={scope === 'law' || scope === 'internal'} />}
              <Checkbox label={"\uD604\uC7AC OCR \uBD84\uC11D \uD0A4\uC6CC\uB4DC \uAC80\uC0C9 \uD3EC\uD568"} checked={includeOcr} onChange={setIncludeOcr} disabled={ocrOptions.length === 0} />
              <Checkbox label={"\uD604\uC7AC \uD14D\uC2A4\uD2B8 \uBD84\uC11D \uD0A4\uC6CC\uB4DC \uAC80\uC0C9 \uD3EC\uD568"} checked={includeText} onChange={setIncludeText} />
            </div>
          </div>
          <div className={contextText.length > 20000 ? 'chat-context-count over' : 'chat-context-count'}>연결 자료 {contextText.length.toLocaleString()} / 20,000자</div>
        </div>}
      </div>
      <main className="chat-thread" aria-live="polite">
        {history.length === 0 && <div className="chat-welcome"><div className="chat-bot-avatar">AI</div><div className="chat-bubble assistant"><strong>안녕하세요!</strong><br />법령 근거와 키워드 정보를 확인해 드릴게요. 궁금한 내용을 입력해 주세요.</div></div>}
        {history.map((turn, i) => <article className="chat-turn" key={i}>
          <div className="chat-msg user"><div className="chat-bubble user">{turn.question}</div></div>
          <div className="chat-msg assistant"><div className="chat-bot-avatar">AI</div><div className={`chat-bubble assistant${turn.failed ? ' failed' : ''}`}>
            {turn.result.recommendation_only && <small className="caption">{'AI \uAD8C\uACE0\uC548 \u00B7 \uCD5C\uC885 \uD310\uC815 \uC544\uB2D8'}</small>}
            <MarkdownText text={turn.result.answer || '검색 결과가 없습니다.'} />
            {(turn.result.search_methods ?? []).length > 0 && <small>{'\uAC80\uC0C9 \uBC29\uC2DD: '}{(turn.result.search_methods ?? []).map(method => METHOD_LABELS[method] ?? method).join(', ')}</small>}
            {Boolean(turn.result.administrator_review) && <Alert kind="warning">근거가 상충하거나 충분히 검증되지 않았습니다. 법적 판단은 관리자에게 문의해 주세요.</Alert>}
            {turn.result.keyword_matches?.length > 0 && <Expander title="관련 키워드 보기"><DataTable rows={turn.result.keyword_matches as Record<string, unknown>[]} rowKey={(_, j) => String(j)} columns={MATCH_COLUMNS.map(c => ({ key: c }))} showIndex={false} /></Expander>}
            {(turn.result.related_candidates ?? []).length > 0 && <Expander title="의미상 관련 후보 · 심의자 검토용"><DataTable rows={turn.result.related_candidates as unknown as Record<string, unknown>[]} rowKey={(_, j) => String(j)} columns={[{ key: 'kwd_no' }, { key: 'keyword' }, { key: 'similarity' }]} showIndex={false} /></Expander>}
            {(turn.result.sources ?? []).length > 0 && <div className="chat-sources"><Expander title={`${turn.result.sources.some(source => String(source.id ?? '').startsWith('WEB')) ? '\uCD94\uAC00 \uAC80\uC0C9 \uCD9C\uCC98\uC640 \uADFC\uAC70' : '\uAC80\uC0C9 \uCD9C\uCC98 \uBC0F \uADFC\uAC70'} (${turn.result.sources.length})`}>{(turn.result.sources ?? []).map((source, j) => <div className="chat-source" key={j}><strong>[{String(source.id ?? j + 1)}] {source.label}</strong>{typeof source.url === 'string' && source.url && <a href={source.url} target="_blank" rel="noreferrer">원문 열기 ↗</a>}{typeof source.version === 'string' && source.version && <small> · 버전 {source.version}</small>}<pre>{String(source.text ?? '')}</pre></div>)}</Expander></div>}
          </div></div>
        </article>)}
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
      {warning && <div className="chat-warning" role="alert">{warning}</div>}
      {history.length > 0 && <button className="chat-clear" type="button" onClick={() => { setHistory([]); setThreadId(null) }} disabled={busy}>새 대화</button>}
    </section>
  )
}
