import { useMemo, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { ApiError, askRegulation, type RegulationConversationMessage } from '../lib/api.ts'
import { pySorted, uniqueValues } from '../lib/catalog.ts'
import type { RegulationResult } from '../lib/types.ts'
import { useStore } from '../store.tsx'
import { Alert, Checkbox, DataTable, Expander, MultiSelect, Select } from '../components/ui.tsx'

type Direction = 'keyword_to_law' | 'law_to_keywords'
type Turn = { question: string; result: RegulationResult; failed?: boolean }
const DIRECTIONS: Direction[] = ['keyword_to_law', 'law_to_keywords']
const DIRECTION_LABELS: Record<Direction, string> = {
  keyword_to_law: '광고 문구·키워드에서 법령 찾기',
  law_to_keywords: '법령·조항에서 등록 키워드 찾기',
}
const MATCH_COLUMNS = ['kwd_no', '키워드명', '상품카테고리', '리스크 등급', '대체키워드', '리스크 등급별 검토 의견']

function MarkdownText({ text }: { text: string }) {
  return <div>{text.split(/\n{2,}/).map((para, i) => <p key={i} style={{ margin: '0 0 .6rem' }}>{para.split(/(\*\*[^*]+\*\*)/g).map((part, j) => part.startsWith('**') && part.endsWith('**') ? <strong key={j}>{part.slice(2, -2)}</strong> : <span key={j}>{part}</span>)}</p>)}</div>
}

export function ChatTab() {
  const { catalog, dropdowns, ocr, analysisText } = useStore()
  const [history, setHistory] = useState<Turn[]>([])
  const [direction, setDirection] = useState<Direction>('keyword_to_law')
  const [question, setQuestion] = useState('')
  const [ocrTerms, setOcrTerms] = useState<string[]>([])
  const [includeOcr, setIncludeOcr] = useState(false)
  const [includeText, setIncludeText] = useState(false)
  const [category, setCategory] = useState('')
  const [optionsOpen, setOptionsOpen] = useState(false)
  const [warning, setWarning] = useState('')
  const [busy, setBusy] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const ocrOptions = useMemo(() => pySorted(new Set(ocr.candidates.map(c => c.term.trim()).filter(Boolean))), [ocr.candidates])
  const categories = useMemo(() => ['', ...pySorted(new Set([
    ...(dropdowns?.opt_categories ?? []),
    ...uniqueValues(catalog?.rows ?? [], '\uC0C1\uD488\uCE74\uD14C\uACE0\uB9AC'),
  ].map(value => value.trim()).filter(Boolean)))], [catalog, dropdowns])
  const contextText = [...(includeOcr ? ocrTerms.filter(t => ocrOptions.includes(t)) : []), ...(includeText && analysisText.trim() ? [analysisText] : [])].join('\n')

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
      result = await askRegulation({ direction, query: q, context_text: contextText, category, conversation_history: conversation })
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
        <button className={`chat-options-toggle${optionsOpen ? ' active' : ''}`} onClick={() => setOptionsOpen(open => !open)} aria-expanded={optionsOpen} aria-label="검색 옵션">⚡</button>
      </header>
      {optionsOpen && <div className="chat-options"><div className="chat-options-title">검색 옵션</div>
        <div className="chat-options-grid"><Select label="질문 방향" value={direction} options={DIRECTIONS} format={d => DIRECTION_LABELS[d]} onChange={setDirection} />
          <Select label="상품 카테고리" value={category} options={categories} format={c => c || '전체 카테고리'} onChange={setCategory} />
          {ocrOptions.length > 0 && <MultiSelect label={"\uD604\uC7AC OCR \uBD84\uC11D \uD0A4\uC6CC\uB4DC"} value={ocrTerms} options={ocrOptions} onChange={setOcrTerms} />}
          <Checkbox label={"\uD604\uC7AC OCR \uBD84\uC11D \uD0A4\uC6CC\uB4DC \uAC80\uC0C9 \uD3EC\uD568"} checked={includeOcr} onChange={setIncludeOcr} disabled={ocrOptions.length === 0} />
          <Checkbox label="현재 텍스트 분석 키워드 검색 포함" checked={includeText} onChange={setIncludeText} />
        </div>
        <div className={contextText.length > 20000 ? 'chat-context-count over' : 'chat-context-count'}>연결 자료 {contextText.length.toLocaleString()} / 20,000자</div>
      </div>}
      <main className="chat-thread" aria-live="polite">
        {history.length === 0 && <div className="chat-welcome"><div className="chat-bot-avatar">AI</div><div className="chat-bubble assistant"><strong>안녕하세요!</strong><br />법령 근거와 키워드 정보를 확인해 드릴게요. 궁금한 내용을 입력해 주세요.</div></div>}
        {history.map((turn, i) => <article className="chat-turn" key={i}>
          <div className="chat-msg user"><div className="chat-bubble user">{turn.question}</div></div>
          <div className="chat-msg assistant"><div className="chat-bot-avatar">AI</div><div className={`chat-bubble assistant${turn.failed ? ' failed' : ''}`}>
            <MarkdownText text={turn.result.answer || '검색 결과가 없습니다.'} />
            {Boolean(turn.result.administrator_review) && <Alert kind="warning">근거가 상충하거나 충분히 검증되지 않았습니다. 법적 판단은 관리자에게 문의해 주세요.</Alert>}
            {turn.result.keyword_matches?.length > 0 && <Expander title="관련 키워드 보기"><DataTable rows={turn.result.keyword_matches as Record<string, unknown>[]} rowKey={(_, j) => String(j)} columns={MATCH_COLUMNS.map(c => ({ key: c }))} showIndex={false} /></Expander>}
            {(turn.result.sources ?? []).length > 0 && <div className="chat-sources"><Expander title={`공식 출처 및 근거 (${turn.result.sources.length})`}>{(turn.result.sources ?? []).map((source, j) => <div className="chat-source" key={j}><strong>{source.label}</strong>{source.url && <a href={String(source.url)} target="_blank" rel="noreferrer">공식 자료 열기 ↗</a>}<pre>{String(source.text ?? '')}</pre></div>)}</Expander></div>}
          </div></div>
        </article>)}
        {busy && <div className="chat-msg assistant"><div className="chat-bot-avatar">AI</div><div className="chat-bubble assistant chat-thinking">답변을 확인하고 있습니다…</div></div>}
        <div ref={bottomRef} />
      </main>
      <form className="chat-composer" onSubmit={submit}><div className="chat-input-wrap">
        <textarea value={question} onChange={e => setQuestion(e.target.value.slice(0, 500))} onKeyDown={onKeyDown} maxLength={500} rows={1} disabled={busy} placeholder="메시지를 입력하세요…" aria-label="질문 입력" />
        <span className={question.length > 500 ? 'over' : ''}>{question.length}/500</span>
      </div><button className="chat-send" type="submit" disabled={busy || question.trim().length < 2} aria-label="질문 전송">➤</button></form>
      {warning && <div className="chat-warning" role="alert">{warning}</div>}
      {history.length > 0 && <button className="chat-clear" type="button" onClick={() => setHistory([])} disabled={busy}>대화 지우기</button>}
    </section>
  )
}
