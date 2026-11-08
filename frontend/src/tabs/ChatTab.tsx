import { useMemo, useState, type FormEvent } from 'react'
import { askRegulation } from '../lib/api.ts'
import { pySorted, uniqueValues } from '../lib/catalog.ts'
import type { RegulationResult } from '../lib/types.ts'
import { useStore } from '../store.tsx'
import { Alert, Button, Checkbox, DataTable, Expander, MultiSelect, Select, Spinner, TextInput } from '../components/ui.tsx'
import { ApiError } from '../lib/api.ts'

type Direction = 'keyword_to_law' | 'law_to_keywords'
const DIRECTIONS: Direction[] = ['keyword_to_law', 'law_to_keywords']
const DIRECTION_LABELS: Record<Direction, string> = {
  keyword_to_law: '광고 문구·키워드에서 법령 찾기',
  law_to_keywords: '법령·조항에서 등록 키워드 찾기',
}
const MATCH_COLUMNS = ['kwd_no', '키워드명', '상품카테고리', '리스크 등급', '대체키워드', '리스크 등급별 세부 심의기준']

type Turn = { question: string; result: RegulationResult }

/** Plain Markdown subset for answers: paragraphs, **bold** and line breaks. */
function MarkdownText({ text }: { text: string }) {
  return (
    <div>
      {text.split(/\n{2,}/).map((para, i) => (
        <p key={i} style={{ margin: '0 0 .6rem' }}>
          {para.split(/(\*\*[^*]+\*\*)/g).map((part, j) => (part.startsWith('**') && part.endsWith('**')
            ? <strong key={j}>{part.slice(2, -2)}</strong> : <span key={j}>{part}</span>))}
        </p>
      ))}
    </div>
  )
}

export function ChatTab() {
  const { catalog, ocr, analysisText } = useStore()
  const [history, setHistory] = useState<Turn[]>([])
  const [direction, setDirection] = useState<Direction>('keyword_to_law')
  const [question, setQuestion] = useState('')
  const [ocrTerms, setOcrTerms] = useState<string[]>([])
  const [includeText, setIncludeText] = useState(false)
  const [category, setCategory] = useState('')
  const [warning, setWarning] = useState('')
  const [busy, setBusy] = useState(false)

  const ocrOptions = useMemo(() => pySorted(new Set(ocr.candidates.map(c => c.term.trim()).filter(Boolean))), [ocr.candidates])
  const categories = useMemo(() => ['', ...pySorted(uniqueValues(catalog?.rows ?? [], '상품카테고리'))], [catalog])

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setWarning('')
    const q = question.trim()
    // The API requires at least two characters; Streamlit only rejected blanks.
    if (q.length < 2) { setWarning('질문이나 검색어를 입력해 주세요.'); return }
    const context = [...ocrTerms.filter(t => ocrOptions.includes(t)), ...(includeText && analysisText.trim() ? [analysisText] : [])].join('\n')
    setBusy(true)
    let result: RegulationResult
    try {
      result = await askRegulation({ direction, query: q, context_text: context, category })
    } catch (error) {
      const answer = error instanceof ApiError && error.status === 0
        ? '법령 검색 API에 연결할 수 없습니다. 기존 키워드/OCR 분석은 계속 사용할 수 있습니다.'
        : error instanceof Error ? error.message.slice(0, 500) || '법령 검색을 완료하지 못했습니다.' : '법령 검색을 완료하지 못했습니다.'
      result = { answer, sources: [], keyword_matches: [] }
    }
    setHistory(h => [...h, { question: q, result }])
    // clear_on_submit: every field returns to its default.
    setDirection('keyword_to_law'); setQuestion(''); setOcrTerms([]); setIncludeText(false); setCategory('')
    setBusy(false)
  }

  return (
    <div>
      <h3>심의 Chat-bot</h3>
      <div className="caption">기존 분석과 별도로, 질문을 보냈을 때만 키워드 DB와 공식 법령·판례 검색을 수행합니다. 검색 결과가 법적 결론을 뜻하지는 않습니다.</div>
      {history.map((turn, i) => (
        <div key={i}>
          <div className="chat-msg"><div className="chat-avatar user">🙂</div><div className="chat-body">{turn.question}</div></div>
          <div className="chat-msg">
            <div className="chat-avatar assistant">🤖</div>
            <div className="chat-body" style={{ whiteSpace: 'normal' }}>
              <MarkdownText text={turn.result.answer || '검색 결과가 없습니다.'} />
              {Boolean(turn.result.administrator_review) && (
                <Alert kind="warning">검색 근거가 상충하거나 설명을 검증하지 못했습니다. 세부 판단은 관리자에게 문의해 주세요.</Alert>
              )}
              {turn.result.keyword_matches?.length > 0 && (
                <div aria-label="법령 조문에서 확인한 키워드 DB 결과">
                  <DataTable rows={turn.result.keyword_matches as Record<string, unknown>[]} rowKey={(_, j) => String(j)}
                    columns={MATCH_COLUMNS.map(c => ({ key: c }))} showIndex={false} />
                </div>
              )}
              {(turn.result.sources ?? []).map((source, j) => (
                <Expander key={j} title={`근거: ${source.label}`}>
                  {source.url && <div className="mb"><a className="btn small" href={String(source.url)} target="_blank" rel="noreferrer">원문/API 응답 열기</a></div>}
                  <pre style={{ whiteSpace: 'pre-wrap', fontSize: '.85rem', margin: 0 }}>{String(source.text ?? '')}</pre>
                </Expander>
              ))}
            </div>
          </div>
        </div>
      ))}
      <form onSubmit={submit} className="expander stack" style={{ padding: '1rem', marginTop: '1rem' }}>
        <Select label="질문 방향" value={direction} options={DIRECTIONS} format={d => DIRECTION_LABELS[d]} onChange={setDirection} />
        <TextInput label="질문 또는 검색어" value={question} onChange={setQuestion} maxLength={500}
          placeholder="예: 화장품 광고의 주름 개선 표현 관련 조항 / 화장품법 제13조에서 등록 키워드 찾기" />
        {ocrOptions.length > 0 && <MultiSelect label="현재 OCR 후보 연결 (선택)" value={ocrTerms} options={ocrOptions} onChange={setOcrTerms} />}
        <Checkbox label="현재 텍스트 분석 문구도 검색에 포함" checked={includeText} onChange={setIncludeText} />
        <Select label="상품 분류" value={category} options={categories} format={c => c || '모든 분류'} onChange={setCategory} />
        <div><Button primary type="submit" disabled={busy}>검색하고 답변 보기</Button></div>
      </form>
      {busy && <Spinner text="검색 중입니다." />}
      {warning && <Alert kind="warning">{warning}</Alert>}
      <div className="mt"><Button onClick={() => setHistory([])}>대화 지우기</Button></div>
    </div>
  )
}
