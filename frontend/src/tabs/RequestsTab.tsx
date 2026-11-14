import { useCallback, useEffect, useState, type ReactNode } from 'react'
import {
  addRequestMessage, deleteKeywordRequest, deleteRequestMessage, editRequestMessage, loadKeywordRequests,
  loadRequestMessages, loadRequestNotifications, saveRequestNotifications, setRequestMessageStatus,
} from '../lib/api.ts'
import { formatDatetime } from '../lib/catalog.ts'
import type { KeywordRequestMessage, KeywordRequestRecord, KeywordRequestType } from '../lib/types.ts'
import { useStore } from '../store.tsx'
import { KeywordRequestForm, REQUEST_TYPE_LABELS } from '../components/KeywordRequestForm.tsx'
import { Alert, Button, Checkbox, Dialog, Expander, Select, Spinner, TextArea, errorText } from '../components/ui.tsx'

const STATUSES = ['대기', '검토중', '처리완료'] as const
const TYPE_ORDER: KeywordRequestType[] = ['risk_grade_adjustment', 'review_criteria_change', 'new_keyword_registration']
const receipt = (request: KeywordRequestRecord) => request.receipt_no || `KR-${request.id.slice(0, 8).toUpperCase()}`
const typeLabel = (t: string) => REQUEST_TYPE_LABELS[t as KeywordRequestType] ?? t

export function RequestsTab() {
  const { user, isAdmin } = useStore()
  const [items, setItems] = useState<KeywordRequestRecord[] | null>(null)
  const [error, setError] = useState('')
  const [flash, setFlash] = useState('')
  const [open, setOpen] = useState<KeywordRequestRecord | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [notif, setNotif] = useState<{ enabled: boolean; configured: boolean } | null>(null)
  const [notifOn, setNotifOn] = useState(false)
  const [notifMsg, setNotifMsg] = useState<{ kind: 'success' | 'error'; text: string } | null>(null)
  const [notifError, setNotifError] = useState('')

  const load = useCallback(async () => {
    try {
      const all = (await loadKeywordRequests()).items
      const visible = isAdmin ? all : all.filter(item => item.requester_id === user.id)
      setItems(visible)
      setSelectedId(current => current && visible.some(item => item.id === current) ? current : visible[0]?.id ?? null)
      setError('')
    }
    catch { setError('문의 내역을 불러오지 못했습니다. 문의용 DB 설정과 RLS 정책을 확인하세요.') }
  }, [isAdmin, user.id])
  useEffect(() => { void load() }, [load])
  useEffect(() => {
    if (!isAdmin) return
    loadRequestNotifications().then(n => { setNotif(n); setNotifOn(n.enabled) })
      .catch(() => setNotifError('관리자 알림 설정을 불러오지 못했습니다. 문의용 DB 설정을 적용했는지 확인하세요.'))
  }, [isAdmin])

  const columns = [
    { key: 'receipt', label: '접수번호', render: (r: KeywordRequestRecord) => receipt(r) },
    ...(isAdmin ? [{ key: 'requester_email', label: '요청자' }] : []),
    { key: 'keyword', label: '키워드', render: (r: KeywordRequestRecord) => `${r.kwd_no || '신규'} | ${r.keyword_name || '신규 키워드'}` },
    { key: 'request_type', label: '문의 유형', render: (r: KeywordRequestRecord) => typeLabel(r.request_type) },
    { key: 'request_detail', label: '요청 내용', render: (r: KeywordRequestRecord) => <span className="request-table-summary">{r.request_detail || '상세 내용 없음'}</span> },
    { key: 'status', label: '처리 상태', render: (r: KeywordRequestRecord) => <span className={`request-status ${r.status === '처리완료' ? 'done' : 'active'}`}>{r.status || '대기'}</span> },
    { key: 'created_at', label: '접수 시각', render: (r: KeywordRequestRecord) => formatDatetime(r.created_at) },
    { key: 'detail', label: '', render: () => '상세 보기' },
  ]
  const selected = items?.find(item => item.id === selectedId) ?? null

  return (
    <div>
      {flash && <Alert kind="success">{flash}</Alert>}
      <h3>키워드 문의</h3>
      {!isAdmin && <section className="request-entry-panel">
        <h4>문의 등록</h4>
        <KeywordRequestForm onSubmitted={() => void load()} />
      </section>}
      {isAdmin && <div className="request-admin-intro">접수된 문의를 확인하고 답변 및 처리 상태를 관리합니다.</div>}
      <h4 className="request-history-heading">{isAdmin ? '접수된 문의 내역' : '내 문의 내역'}</h4>
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
      {items && !items.length && <Alert kind="info">{isAdmin ? '접수된 키워드 문의가 없습니다.' : '등록된 키워드 문의가 없습니다.'}</Alert>}
      {items && items.length > 0 && (
        <>
          <div className="caption">{isAdmin ? '행을 선택해 문의를 확인하고 상세 대화에서 답변 및 처리 상태를 관리하세요.' : '행을 선택하면 문의 내용과 관리자 답변을 확인할 수 있습니다.'}</div>
          <div className="table-wrap">
            <table className={`grid request-table${isAdmin ? ' admin' : ''}`}>
              <thead><tr>{columns.map(c => <th key={c.key}>{c.label}</th>)}</tr></thead>
              <tbody>
                {items.map(r => (
                  <tr key={r.id} className={selectedId === r.id ? 'selected' : ''} style={{ cursor: 'pointer' }} tabIndex={0}
                    onClick={() => setSelectedId(r.id)} onKeyDown={e => { if (e.key === 'Enter') setSelectedId(r.id) }}>
                    {columns.map(c => <td key={c.key} className={`request-col-${c.key}`}>{c.key === 'detail'
                      ? <Button small className={isAdmin && (r.needs_attention ?? r.status !== '처리완료') ? 'request-needs-attention' : undefined}
                          title={isAdmin && (r.needs_attention ?? r.status !== '처리완료') ? '답변 또는 후속 처리 필요' : undefined}
                          onClick={() => { setSelectedId(r.id); setFlash(''); setOpen(r) }}>{isAdmin ? '답변 및 처리' : '상세 보기'}</Button>
                      : c.render ? c.render(r) : String(r[c.key] ?? '')}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {items.length >= 1000 && <div className="caption">최근 1,000건만 표시했습니다.</div>}
        </>
      )}
      {selected && <section className="request-selected-panel">
        <div className="request-selected-heading">
          <div>
            <h4>선택한 문의 상세</h4>
            <div className="caption">{receipt(selected)} | {selected.kwd_no || '신규'} {selected.keyword_name || '신규 키워드'} | {typeLabel(selected.request_type)}{isAdmin && selected.requester_email ? ` | ${selected.requester_email}` : ''}</div>
          </div>
          <Button small onClick={() => { setFlash(''); setOpen(selected) }}>{isAdmin ? '답변 및 처리 열기' : '대화 상세 열기'}</Button>
        </div>
        <div className="request-selected-body">
          <div className="request-message-card user"><strong>사용자 문의</strong><p>{selected.request_detail || '상세 요청 내용이 없습니다.'}</p></div>
          <div className="request-message-card admin"><strong>관리자 답변</strong><p>{selected.admin_reply || '아직 관리자 답변이 없습니다.'}</p></div>
        </div>
      </section>}
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
  const [statusFor, setStatusFor] = useState<string | null>(null)
  const [followFor, setFollowFor] = useState<string | null>(null)
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null)
  const [error, setError] = useState('')
  const owner = request.requester_id === user.id

  const load = useCallback(async () => {
    try { setMessages((await loadRequestMessages(request.id)).items); setThreadError('') }
    catch (e) { setThreadError(errorText(e)); setMessages([]) }
  }, [request.id])
  useEffect(() => { void load() }, [load])

  const after = async (flash: string) => { setError(''); setFeedbackFor(null); setStatusFor(null); setFollowFor(null); setConfirmDelete(null); await load(); await onChanged(flash) }
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
    if (isAdmin && m.author_role === 'user' && !disabled) {
      if (childOf.get(m.id)?.author_role === 'admin') {
        nodes.push(statusFor === m.id ? (
          <StatusEditor key="status" code={code} message={m} requestId={request.id}
            onSaved={() => after('처리상태를 변경했습니다.')} onCancel={() => setStatusFor(null)} onError={setError} />
        ) : <Button key="statusbtn" small onClick={() => setStatusFor(m.id)}>{code} 처리상태 변경</Button>)
      } else if (!childOf.has(m.id)) {
        nodes.push(feedbackFor === m.id ? (
          <Feedback key="fb" code={code} message={m} requestId={request.id} onSaved={() => after('대화 내역에 메시지를 추가했습니다.')} onError={setError} />
        ) : <Button key="fbbtn" small className="request-feedback-button" onClick={() => setFeedbackFor(m.id)}>{code} 피드백 작성</Button>)
      }
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
      <div><b>접수번호:</b> {receipt(request)}</div>
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
          <div key={root.id} className={`thread-item request-thread-item ${i % 2 === 0 ? 'tone-blue' : 'tone-green'}`}>
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

function StatusEditor({ code, message, requestId, onSaved, onCancel, onError }: {
  code: string; message: KeywordRequestMessage; requestId: string
  onSaved: () => void; onCancel: () => void; onError: (text: string) => void
}) {
  const [status, setStatus] = useState(message.status)
  const [saving, setSaving] = useState(false)
  return <form className="request-status-editor" onSubmit={async event => {
    event.preventDefault()
    if (saving || status === message.status) return
    setSaving(true)
    try { await setRequestMessageStatus(requestId, message.id, status); onSaved() }
    catch { onError(`${code} 처리상태를 변경하지 못했습니다.`) }
    finally { setSaving(false) }
  }}>
    <Select label={`${code} 처리상태`} value={status} options={[...STATUSES]} onChange={setStatus} disabled={saving} />
    <div className="row tight"><Button primary type="submit" disabled={saving || status === message.status}>상태 저장</Button><Button onClick={onCancel} disabled={saving}>취소</Button></div>
  </form>
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
