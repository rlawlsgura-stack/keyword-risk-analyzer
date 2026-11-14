import { useMemo, useState } from 'react'
import { submitKeywordRequest, submitNewKeywordRequests } from '../lib/api.ts'
import type { KeywordRequestType } from '../lib/types.ts'
import { useStore } from '../store.tsx'
import { SearchSelect } from './SearchSelect.tsx'
import { Alert, Button, Select, TextArea, errorText } from './ui.tsx'

export const REQUEST_TYPE_LABELS: Record<KeywordRequestType, string> = {
  risk_grade_adjustment: '리스크 등급 조정요청',
  review_criteria_change: '심의기준 변경요청',
  new_keyword_registration: '신규키워드 등록요청',
}
// Streamlit sorts the options by label (L1900).
const TYPE_OPTIONS = (Object.keys(REQUEST_TYPE_LABELS) as KeywordRequestType[])
  .sort((a, b) => REQUEST_TYPE_LABELS[a].localeCompare(REQUEST_TYPE_LABELS[b], 'ko'))

type Msg = { kind: 'success' | 'error' | 'warning'; text: string; caption?: string }

export function KeywordRequestForm({ onSubmitted }: { onSubmitted?: () => void }) {
  const { catalog, reloadCatalog } = useStore()
  const [type, setType] = useState<KeywordRequestType>('risk_grade_adjustment')
  const [keyword, setKeyword] = useState<string | null>(null)
  const [detail, setDetail] = useState('')
  const [busy, setBusy] = useState(false)
  const [messages, setMessages] = useState<Msg[]>([])
  const isNew = type === 'new_keyword_registration'

  const options = useMemo(() => (catalog?.rows ?? [])
    .filter(r => String(r.kwd_no ?? '').trim())
    .map(r => ({ code: String(r.kwd_no).trim().toUpperCase(), name: String(r['키워드명'] ?? '') }))
    .sort((a, b) => a.code.toLowerCase().localeCompare(b.code.toLowerCase()) || a.name.toLowerCase().localeCompare(b.name.toLowerCase()))
    .map(o => `${o.code} | ${o.name}`), [catalog])

  const submit = async () => {
    setMessages([])
    if (isNew) {
      const seen = new Set<string>()
      const terms = detail.split(',').map(s => s.trim()).filter(s => {
        const key = s.normalize('NFKC').toLowerCase()
        if (!s || seen.has(key)) return false
        seen.add(key)
        return true
      })
      if (!terms.length) { setMessages([{ kind: 'error', text: '등록 요청할 키워드를 쉼표로 구분해 입력하세요.' }]); return }
      setBusy(true)
      try {
        const result = await submitNewKeywordRequests(terms)
        setMessages([{ kind: 'success', text: `신규 키워드 ${result.submitted}건을 미매칭 표현 목록에 요청 상태로 추가했습니다.` }])
        onSubmitted?.()
        setDetail(''); setKeyword(null)
      } catch (error) {
        setMessages([{ kind: 'error', text: '신규 키워드 등록 요청을 접수하지 못했습니다. Supabase 연결과 입력을 확인하세요.', caption: errorText(error) }])
      } finally { setBusy(false) }
      return
    }
    if (!keyword) { setMessages([{ kind: 'error', text: '목록에서 키워드 번호 또는 키워드명을 검색해 선택하세요.' }]); return }
    setBusy(true)
    try {
      const fresh = await reloadCatalog()
      const code = keyword.split(' | ')[0].trim()
      const row = fresh?.rows.find(r => String(r.kwd_no).trim().toUpperCase() === code)
      if (!row) { setMessages([{ kind: 'error', text: '현재 공유 DB에서 kwd_no를 찾을 수 없습니다. 최신 번호를 확인하세요.' }]); return }
      const result = await submitKeywordRequest({ kwd_no: String(row.kwd_no).trim(), request_type: type, request_detail: detail.trim() })
      const next: Msg[] = [{ kind: 'success', text: `문의가 등록되었습니다. 접수번호: ${result.receipt_no}. 키워드 문의 화면의 내 문의 내역에서 확인할 수 있습니다.` }]
      if (result.notification === 'failed') {
        next.push({ kind: 'warning', text: '문의는 등록됐지만 관리자 이메일 알림은 발송되지 않았습니다.', caption: result.notification_error })
      }
      setMessages(next)
      onSubmitted?.()
      setDetail(''); setKeyword(null)
    } catch (error) {
      setMessages([{ kind: 'error', text: '문의 등록을 완료하지 못했습니다. Supabase 설정과 접근 권한을 확인하세요.', caption: errorText(error) }])
    } finally { setBusy(false) }
  }

  return (
    <div className="stack request-entry-form">
      <div className="request-entry-fields">
        <Select label="문의 유형" value={type} options={TYPE_OPTIONS} format={t => REQUEST_TYPE_LABELS[t]} onChange={setType} />
      <SearchSelect label="키워드 검색 (kwd_no / 키워드명)" value={keyword} options={options} onChange={setKeyword}
        placeholder="번호 또는 키워드명을 입력하세요." disabled={!options.length} />
      </div>
      {isNew && <div className="caption">신규키워드는 한 항목씩 입력해 주세요. 여러 키워드는 쉼표(,)로 구분하세요. 예: 키워드A, 키워드B</div>}
      <div className="request-detail-row">
        <TextArea rows={2} label={isNew ? '요청 상세 내용' : '요청 상세 내용 (선택)'} value={detail} onChange={setDetail} maxLength={4000}
          placeholder={isNew ? '키워드A, 키워드B' : ''}
          help={isNew ? '신규키워드는 쉼표(,)로 구분해 입력하세요.' : '변경이 필요한 이유나 원하는 내용을 적어주세요. 최대 4,000자까지 입력할 수 있습니다.'} />
        <div><Button primary onClick={submit} disabled={busy}>문의 등록</Button></div>
      </div>
      {messages.map(m => (
        <div key={m.text}>
          <Alert kind={m.kind}>{m.text}</Alert>
          {m.caption && <div className="caption">{m.caption}</div>}
        </div>
      ))}
    </div>
  )
}
