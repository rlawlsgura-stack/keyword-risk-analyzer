import { useCallback, useEffect, useState, type ReactNode } from 'react'
import {
  addRequestMessage, deleteKeywordRequest, deleteRequestMessage, editRequestMessage, loadKeywordRequests,
  loadRequestMessages, loadRequestNotifications, saveRequestNotifications,
} from '../lib/api.ts'
import { formatDatetime } from '../lib/catalog.ts'
import type { KeywordRequestMessage, KeywordRequestRecord, KeywordRequestType } from '../lib/types.ts'
import { useStore } from '../store.tsx'
import { REQUEST_TYPE_LABELS } from '../components/KeywordRequestForm.tsx'
import { Alert, Button, Checkbox, Dialog, Expander, Select, Spinner, TextArea, errorText } from '../components/ui.tsx'

const STATUSES = ['대기', '검토중', '처리완료'] as const
const TYPE_ORDER: KeywordRequestType[] = ['risk_grade_adjustment', 'review_criteria_change', 'new_keyword_registration']
const receipt = (id: string) => `KR-${id.slice(0, 8).toUpperCase()}`
const typeLabel = (t: string) => REQUEST_TYPE_LABELS[t as KeywordRequestType] ?? t

export function RequestsTab() {
  const { isAdmin } = useStore()
  const [items, setItems] = useState<KeywordRequestRecord[] | null>(null)
  const [error, setError] = useState('')
  const [flash, setFlash] = useState('')
  const [open, setOpen] = useState<KeywordRequestRecord | null>(null)
  const [notif, setNotif] = useState<{ enabled: boolean; configured: boolean } | null>(null)
  const [notifOn, setNotifOn] = useState(false)
  const [notifMsg, setNotifMsg] = useState<{ kind: 'success' | 'error'; text: string } | null>(null)
  const [notifError, setNotifError] = useState('')

  const load = useCallback(async () => {
    try { setItems((await loadKeywordRequests()).items); setError('') }
    catch { setError('문의 내역을 불러오지 못했습니다. 문의용 DB 설정과 RLS 정책을 확인하세요.') }
  }, [])
  useEffect(() => { void load() }, [load])
  useEffect(() => {
    if (!isAdmin) return
    loadRequestNotifications().then(n => { setNotif(n); setNotifOn(n.enabled) })
      .catch(() => setNotifError('관리자 알림 설정을 불러오지 못했습니다. 문의용 DB 설정을 적용했는지 확인하세요.'))
  }, [isAdmin])

  const columns = [
    { key: 'receipt', label: '접수번호', render: (r: KeywordRequestRecord) => receipt(r.id) },
    { key: 'kwd_no', label: 'kwd_no' },
    { key: 'keyword_name', label: '키워드명' },
    { key: 'request_type', label: '문의 유형', render: (r: KeywordRequestRecord) => typeLabel(r.request_type) },
    { key: 'request_detail', label: '요청 상세 내용' },
    { key: 'status', label: '처리상태', render: (r: KeywordRequestRecord) => r.status || '대기' },
    { key: 'admin_reply', label: '관리자 답변' },
    ...(isAdmin ? [{ key: 'requester_email', label: '요청자 이메일' }] : []),
    { key: 'created_at', label: '접수 시각', render: (r: KeywordRequestRecord) => formatDatetime(r.created_at) },
  ]

  return (
    <div>
      {flash && <Alert kind="success">{flash}</Alert>}
      <h3>키워드 문의내역</h3>
      {isAdmin && (
        <div className="mb">
          {notifError && <Alert kind="error">{notifError}</Alert>}
          {notif && !notif.configured && (
            <Alert kind="warning">이메일 알림을 사용하려면 Secrets에 RESEND_API_KEY, KEYWORD_REQUEST_ADMIN_EMAIL, KEYWORD_REQUEST_FROM_EMAIL을 설정하세요. 발신 주소의 도메인은 Resend에서 인증해야 합니다.</Alert>
          )}
          {notif && (
            <form className="row center" onSubmit={async e => {
              e.preventDefault(); setNotifMsg(null)
              try { const n = await saveRequestNotifications(notifOn); setNotif(n); setNotifMsg({ kind: 'success', text: '이메일 알림 설정을 저장했습니다.' }) }
              catch { setNotifMsg({ kind: 'error', text: '이메일 알림 설정을 저장하지 못했습니다.' }) }
            }}>
              <Checkbox label="새 문의 등록 시 관리자 이메일 알림" checked={notifOn} onChange={setNotifOn} disabled={!notif.configured && !notif.enabled} />
              <Button type="submit">알림 설정 저장</Button>
            </form>
          )}
          {notifMsg && <Alert kind={notifMsg.kind}>{notifMsg.text}</Alert>}
        </div>
      )}
      {error && <Alert kind="error">{error}</Alert>}
      {items === null && !error && <Spinner />}
      {items && !items.length && <Alert kind="info">등록된 키워드 문의가 없습니다.</Alert>}
      {items && items.length > 0 && (
        <>
          <div className="caption">문의 행을 선택하면 상세 내역과 댓글을 확인할 수 있습니다.</div>
          <div className="table-wrap">
            <table className="grid">
              <thead><tr>{columns.map(c => <th key={c.key}>{c.label}</th>)}</tr></thead>
              <tbody>
                {items.map(r => (
                  <tr key={r.id} style={{ cursor: 'pointer' }} tabIndex={0} onClick={() => { setFlash(''); setOpen(r) }}
                    onKeyDown={e => { if (e.key === 'Enter') { setFlash(''); setOpen(r) } }}>
                    {columns.map(c => <td key={c.key}>{c.render ? c.render(r) : String(r[c.key] ?? '')}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {items.length >= 1000 && <div className="caption">최근 1,000건만 표시했습니다. 더 오래된 요청은 관리자에게 문의하세요.</div>}
        </>
      )}
      {open && (
        <RequestDialog request={open} onClose={() => { setOpen(null); void load() }}
          onChanged={async (message, closeDialog) => {
            if (message) setFlash(message)
            await load()
            if (closeDialog) setOpen(null)
          }} />
      )}
    </div>
  )
}

function RequestDialog({ request, onClose, onChanged }: {
  request: KeywordRequestRecord; onClose: () => void; onChanged: (message: string, closeDialog?: boolean) => Promise<void>
}) {
  const { user, isAdmin } = useStore()
  const [messages, setMessages] = useState<KeywordRequestMessage[] | null>(null)
  const [threadError, setThreadError] = useState('')
  const [feedbackFor, setFeedbackFor] = useState<string | null>(null)
  const [followFor, setFollowFor] = useState<string | null>(null)
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null)
  const [error, setError] = useState('')
  const owner = request.requester_id === user.id

  const load = useCallback(async () => {
    try { setMessages((await loadRequestMessages(request.id)).items); setThreadError('') }
    catch (e) { setThreadError(errorText(e)); setMessages([]) }
  }, [request.id])
  useEffect(() => { void load() }, [load])

  const after = async (flash: string) => { setError(''); setFeedbackFor(null); setFollowFor(null); setConfirmDelete(null); await load(); await onChanged(flash) }
  const disabled = Boolean(threadError)

  const roots = (messages ?? []).filter(m => m.author_role === 'user' && !m.reply_to_id)
  const childOf = new Map<string, KeywordRequestMessage>()
  for (const m of messages ?? []) if (m.reply_to_id && !childOf.has(m.reply_to_id)) childOf.set(m.reply_to_id, m)
  const orphans = (messages ?? []).filter(m => m.author_role === 'admin' && !m.reply_to_id)

  const userControls = (m: KeywordRequestMessage, code: string): ReactNode => {
    const nodes: ReactNode[] = []
    if (owner && m.author_role === 'user' && m.author_id === user.id && !disabled) {
      nodes.push(<EditMessage key="edit" code={code} message={m} request={request} onSaved={() => after('문의 내용을 수정했습니다.')} onError={setError} />)
      nodes.push(confirmDelete === m.id ? (
        <div key="del">
          <Alert kind="warning">{`${code} 문의와 연결된 답변·재문의를 함께 영구 삭제합니다. 다른 문의는 유지됩니다.`}</Alert>
          <div className="row tight">
            <Button onClick={() => setConfirmDelete(null)}>취소</Button>
            <Button primary onClick={async () => {
              try { await deleteRequestMessage(request.id, m.id); await after('선택한 문의와 연결된 답변·재문의를 삭제했습니다.') }
              catch { setError(`${code} 문의를 삭제하지 못했습니다.`) }
            }}>{code} 영구 삭제 확인</Button>
          </div>
        </div>
      ) : <Button key="delbtn" small onClick={() => setConfirmDelete(m.id)}>{code} 삭제</Button>)
    }
    if (isAdmin && m.author_role === 'user' && !childOf.has(m.id) && !disabled) {
      nodes.push(feedbackFor === m.id ? (
        <Feedback key="fb" code={code} message={m} requestId={request.id} onSaved={() => after('대화 내역에 메시지를 추가했습니다.')} onError={setError} />
      ) : <Button key="fbbtn" small onClick={() => setFeedbackFor(m.id)}>{code} 피드백 작성</Button>)
    }
    if (!isAdmin && m.author_role === 'admin' && !childOf.has(m.id) && !disabled) {
      nodes.push(followFor === m.id ? (
        <Compose key="fu" label="재문의 내용" submit="재문의 등록" emptyText="재문의 내용을 입력하세요." failText="재문의를 저장하지 못했습니다."
          onSubmit={body => addRequestMessage(request.id, body, m.id)} onSaved={() => after('대화 내역에 메시지를 추가했습니다.')} onError={setError} />
      ) : <Button key="fubtn" small onClick={() => setFollowFor(m.id)}>이 답변에 재문의</Button>)
    }
    return nodes.length ? <div className="stack" style={{ marginTop: '.4rem' }}>{nodes}</div> : null
  }

  const caption = (parts: string[]) => <div className="caption">{parts.filter(Boolean).join(' | ')}</div>
  const who = (m: KeywordRequestMessage) => (m.is_legacy ? ['작성 시각 기록 없음'] : [m.author_email, formatDatetime(m.created_at)])

  return (
    <Dialog title="문의 상세 및 처리" onClose={onClose} wide>
      <div><b>접수번호:</b> {receipt(request.id)}</div>
      <div><b>키워드no.:</b> {request.kwd_no}</div>
      <div><b>키워드명:</b> {request.keyword_name}</div>
      <div className="caption">접수 시각: {formatDatetime(request.created_at)}</div>
      <div><b>문의 유형:</b> {typeLabel(request.request_type)}</div>
      <div><b>요청자 이메일:</b> {request.requester_email ?? ''}</div>
      <h4>문의 및 답변 내역</h4>
      {messages === null && <Spinner />}
      {threadError && <><Alert kind="warning">대화 내역 기능을 사용하려면 키워드 문의 댓글용 DB 설정을 적용해야 합니다.</Alert><div className="caption">{threadError}</div></>}
      {roots.map((root, i) => {
        const q = `Q${String(i + 1).padStart(2, '0')}`
        const chain: { m: KeywordRequestMessage; code: string }[] = []
        let a = 0, r = 0
        let node = childOf.get(root.id)
        while (node) {
          chain.push({ m: node, code: node.author_role === 'admin' ? `${q}_A${++a}` : `${q}-R${++r}` })
          node = childOf.get(node.id)
        }
        return (
          <div key={root.id} className="thread-item">
            {caption([q, '사용자 문의', `처리상태: ${root.status || '대기'}`, ...who(root)])}
            <div style={{ whiteSpace: 'pre-wrap' }}>{root.body}</div>
            {userControls(root, q)}
            {!chain.length && root.is_initial && request.admin_reply && (
              <><hr />{caption([`${q}_A1`, '기존 관리자 답변', '작성 시각 기록 없음'])}<div style={{ whiteSpace: 'pre-wrap' }}>{request.admin_reply}</div></>
            )}
            {chain.map(({ m, code }) => (
              <div key={m.id}>
                <hr />
                {caption([code, m.author_role === 'admin' ? (m.is_legacy ? '기존 관리자 답변' : '관리자 답변') : '사용자 재문의',
                  m.author_role === 'user' ? `처리상태: ${m.status || '대기'}` : '', ...who(m)])}
                <div style={{ whiteSpace: 'pre-wrap' }}>{m.body}</div>
                {userControls(m, code)}
              </div>
            ))}
          </div>
        )
      })}
      {orphans.map(m => (
        <div key={m.id} className="thread-item admin">
          <div className="caption">기존 관리자 답변 · {m.author_email} · {formatDatetime(m.created_at)}</div>
          <div style={{ whiteSpace: 'pre-wrap' }}>{m.body}</div>
        </div>
      ))}
      {!isAdmin && messages !== null && !threadError && (
        <Compose label="새 문의 등록" submit="새 문의 제출" primary emptyText="새 문의를 저장하지 못했습니다." failText="새 문의를 저장하지 못했습니다."
          onSubmit={body => addRequestMessage(request.id, body, null)} onSaved={() => after('대화 내역에 메시지를 추가했습니다.')} onError={setError} />
      )}
      {error && <Alert kind="error">{error}</Alert>}
      {(isAdmin || owner) && (
        <div className="mt">
          {confirmDelete === 'request' ? (
            <>
              <Alert kind="warning">이 접수건과 모든 문의·답변을 영구 삭제할까요? 삭제한 내역은 복구할 수 없습니다.</Alert>
              <div className="row tight">
                <Button onClick={() => setConfirmDelete(null)}>취소</Button>
                <Button primary onClick={async () => {
                  try { await deleteKeywordRequest(request.id); await onChanged('문의를 삭제했습니다.', true) }
                  catch { setError('문의를 삭제하지 못했습니다. 본인 문의 또는 관리자 권한을 확인하세요.') }
                }}>영구 삭제 확인</Button>
              </div>
            </>
          ) : <Button onClick={() => setConfirmDelete('request')}>접수건 전체 삭제</Button>}
        </div>
      )}
    </Dialog>
  )
}

function EditMessage({ code, message, request, onSaved, onError }: {
  code: string; message: KeywordRequestMessage; request: KeywordRequestRecord; onSaved: () => void; onError: (t: string) => void
}) {
  const [body, setBody] = useState(message.body)
  const [type, setType] = useState<KeywordRequestType>((TYPE_ORDER.includes(request.request_type as KeywordRequestType) ? request.request_type : 'risk_grade_adjustment') as KeywordRequestType)
  return (
    <Expander title={`${code} 수정`}>
      <form className="stack" onSubmit={async e => {
        e.preventDefault()
        if (!message.is_initial && !body.trim()) { onError('문의 내용을 입력하세요.'); return }
        if (message.is_initial && !String(request.kwd_no ?? '').trim() && type !== 'new_keyword_registration') {
          onError('키워드가 지정되지 않은 요청은 신규키워드 등록요청으로 저장하세요.'); return
        }
        try { await editRequestMessage(request.id, message.id, body, message.is_initial ? type : undefined); onSaved() }
        catch { onError(`${code} 문의를 수정하지 못했습니다.`) }
      }}>
        {message.is_initial && <Select label="문의 유형" value={type} options={TYPE_ORDER} format={t => REQUEST_TYPE_LABELS[t]} onChange={setType} />}
        <TextArea label="문의 내용" value={body} onChange={setBody} maxLength={4000} />
        <div><Button primary type="submit">{code} 수정 저장</Button></div>
      </form>
    </Expander>
  )
}

function Feedback({ code, message, requestId, onSaved, onError }: {
  code: string; message: KeywordRequestMessage; requestId: string; onSaved: () => void; onError: (t: string) => void
}) {
  const [body, setBody] = useState('')
  const [status, setStatus] = useState<string>(STATUSES.includes(message.status as typeof STATUSES[number]) ? message.status : '대기')
  return (
    <div className="expander" style={{ padding: '.75rem' }}>
      <div className="caption">{code} 피드백과 처리상태를 함께 저장합니다.</div>
      <form className="stack" onSubmit={async e => {
        e.preventDefault()
        if (!body.trim()) { onError('피드백 내용을 입력하세요.'); return }
        try { await addRequestMessage(requestId, body.trim(), message.id, status); onSaved() }
        catch { onError('피드백과 처리상태를 저장하지 못했습니다.') }
      }}>
        <TextArea label="관리자 피드백" value={body} onChange={setBody} maxLength={4000} />
        <Select label="처리상태" value={status} options={[...STATUSES]} onChange={setStatus} />
        <div><Button primary type="submit">피드백 및 처리상태 저장</Button></div>
      </form>
    </div>
  )
}

function Compose({ label, submit, emptyText, failText, onSubmit, onSaved, onError, primary }: {
  label: string; submit: string; emptyText: string; failText: string; primary?: boolean
  onSubmit: (body: string) => Promise<unknown>; onSaved: () => void; onError: (t: string) => void
}) {
  const [body, setBody] = useState('')
  return (
    <form className="stack mt" onSubmit={async e => {
      e.preventDefault()
      if (!body.trim()) { onError(emptyText); return }
      try { await onSubmit(body.trim()); setBody(''); onSaved() } catch { onError(failText) }
    }}>
      <TextArea label={label} value={body} onChange={setBody} maxLength={4000} />
      <div><Button primary={primary} type="submit">{submit}</Button></div>
    </form>
  )
}
