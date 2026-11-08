import { useEffect, useMemo, useState } from 'react'
import { loadAdminUsers, setUserRole } from '../lib/api.ts'
import type { AdminUser, Role } from '../lib/types.ts'
import { useStore } from '../store.tsx'
import { Alert, Button, Checkbox, DataTable, Select, Spinner, errorText } from '../components/ui.tsx'

const ROLE_LABEL = (role: Role | null | undefined) => (role === 'admin' ? '관리자' : role === 'member' ? '일반 사용자' : '앱 권한 미지정')
const PER_PAGE = 1000

export function UsersTab() {
  const { user: me } = useStore()
  const [loaded, setLoaded] = useState(false)
  const [page, setPage] = useState(1)
  const [users, setUsers] = useState<AdminUser[]>([])
  const [hasMore, setHasMore] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [target, setTarget] = useState('')
  const [role, setRole] = useState<Role | ''>('')
  const [confirm, setConfirm] = useState(false)
  const [msg, setMsg] = useState<{ kind: 'success' | 'warning' | 'error'; text: string } | null>(null)

  const load = async (p: number) => {
    setBusy(true); setError('')
    try {
      const result = await loadAdminUsers(p, PER_PAGE)
      setUsers(result.items); setHasMore(result.has_more); setPage(p); setLoaded(true)
    } catch (e) {
      const text = errorText(e)
      setError(/permissions are not configured/i.test(text) ? '인증 또는 데이터 접근 권한을 확인하세요.' : text)
    } finally { setBusy(false) }
  }

  const sorted = useMemo(() => [...users].sort((a, b) => (a.email || a.id).toLowerCase().localeCompare((b.email || b.id).toLowerCase())), [users])
  useEffect(() => { if (sorted.length && !sorted.some(u => u.id === target)) setTarget(sorted[0].id) }, [sorted, target])
  const selected = sorted.find(u => u.id === target)
  useEffect(() => { setRole(selected?.role === 'admin' || selected?.role === 'member' ? selected.role : ''); setConfirm(false) }, [selected?.id, selected?.role])
  const isSelf = selected?.id === me.id

  const save = async () => {
    setMsg(null)
    if (!selected) { setMsg({ kind: 'error', text: '목록에서 계정을 선택하세요.' }); return }
    if (!confirm) { setMsg({ kind: 'warning', text: '역할 변경 확인에 체크하세요.' }); return }
    if (!role) { setMsg({ kind: 'warning', text: '변경할 역할을 선택하세요.' }); return }
    try {
      const updated = await setUserRole(selected.id, role, selected.role === 'admin' || selected.role === 'member' ? selected.role : null)
      setUsers(list => list.map(u => (u.id === updated.id ? { ...u, ...updated } : u)))
      setConfirm(false)
      setMsg({ kind: 'success', text: '역할을 저장했습니다. 해당 사용자는 로그아웃 후 다시 로그인하세요.' })
    } catch (e) {
      setMsg({ kind: 'error', text: errorText(e) })
    }
  }

  return (
    <div>
      {msg?.kind === 'success' && <Alert kind="success">{msg.text}</Alert>}
      <h3>사용자 관리</h3>
      <div className="caption">이 Supabase 프로젝트의 계정을 조회하고 앱 사용 역할을 변경합니다.</div>
      <div className="caption">한 페이지에 최대 1,000개 계정을 표시합니다.</div>
      {!loaded ? (
        <div className="mt">
          <Button onClick={() => load(1)} disabled={busy}>사용자 목록 불러오기</Button>
          <Alert kind="info">사용자 목록을 불러오려면 버튼을 누르세요.</Alert>
        </div>
      ) : (
        <div className="row tight center mt">
          {(page > 1 || hasMore) && (
            <>
              <Button small disabled={page <= 1 || busy} onClick={() => load(page - 1)}>이전</Button>
              <Button small disabled={!hasMore || busy} onClick={() => load(page + 1)}>다음</Button>
              <span className="caption">{page}페이지</span>
            </>
          )}
          <Button small disabled={busy} onClick={() => load(page)}>목록 새로고침</Button>
        </div>
      )}
      {busy && loaded && <Alert kind="info">선택한 페이지를 불러오고 있습니다.</Alert>}
      {busy && !loaded && <Spinner />}
      {error && <Alert kind="error">{error}</Alert>}
      {loaded && !users.length && !error && <Alert kind="info">이 페이지에 계정이 없습니다.</Alert>}
      {loaded && users.length > 0 && (
        <>
          <div className="mt">
            <DataTable rows={users} rowKey={u => u.id} columns={[
              { key: 'email', label: '이메일' },
              { key: 'role', label: '역할', render: u => ROLE_LABEL(u.role) },
              { key: 'email_confirmed', label: '이메일 확인', render: u => (u.email_confirmed ? '완료' : '미완료') },
            ]} />
          </div>
          <div className="stack mt" style={{ maxWidth: 520 }}>
            <Select label="변경할 계정" value={target} options={sorted.map(u => u.id)} format={id => { const u = sorted.find(x => x.id === id); return u?.email || id }} onChange={setTarget} />
            <div className="caption">현재 역할: {ROLE_LABEL(selected?.role)}</div>
            {isSelf && <Alert kind="info">자신의 관리자 권한은 해제할 수 없습니다.</Alert>}
            <div className="expander stack" style={{ padding: '1rem' }}>
              <Select label="변경할 역할" value={role} options={(role === '' ? ['', 'admin', 'member'] : ['admin', 'member']) as (Role | '')[]}
                format={r => (r === '' ? '' : ROLE_LABEL(r))} onChange={setRole} disabled={isSelf} />
              <Checkbox label="선택한 계정의 역할 변경을 확인했습니다." checked={confirm} onChange={setConfirm} disabled={isSelf} />
              <div><Button onClick={save} disabled={isSelf}>역할 저장</Button></div>
            </div>
            {msg && msg.kind !== 'success' && <Alert kind={msg.kind}>{msg.text}</Alert>}
          </div>
        </>
      )}
    </div>
  )
}
