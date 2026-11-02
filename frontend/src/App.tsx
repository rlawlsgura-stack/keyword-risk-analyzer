import { useEffect, useState, type FormEvent, type ReactNode } from 'react'
import type { Session, User } from '@supabase/supabase-js'
import { analyzeText, configurationReady, supabase, type AnalysisMode, type AnalysisResult, type Match } from './api'

const modes: { value: AnalysisMode; label: string; description: string }[] = [
  { value: 'similar', label: '유사 키워드 포함', description: '등록된 표현과 변형을 함께 찾습니다.' },
  { value: 'exact', label: '정확 일치', description: '등록된 표현을 그대로 찾습니다.' },
  { value: 'partial', label: '부분 일치', description: '연속된 키워드 조각을 찾습니다.' },
]

function HighlightedText({ text, matches }: { text: string; matches: Match[] }) {
  // API offsets count Unicode code points; JavaScript string slicing counts UTF-16 units.
  const characters = Array.from(text)
  const pieces: ReactNode[] = []
  let cursor = 0
  for (const match of [...matches].sort((a, b) => a.start - b.start || b.end - a.end)) {
    if (!Number.isInteger(match.start) || !Number.isInteger(match.end) ||
        match.start < cursor || match.end > characters.length || match.end <= match.start) continue
    if (match.start > cursor) pieces.push(characters.slice(cursor, match.start).join(''))
    pieces.push(<mark key={`${match.start}-${match.end}`} title={match.term}>
      {characters.slice(match.start, match.end).join('')}
    </mark>)
    cursor = match.end
  }
  pieces.push(characters.slice(cursor).join(''))
  return <div className="highlighted-text">{pieces}</div>
}

function App() {
  const [session, setSession] = useState<Session | null>(null)
  const [user, setUser] = useState<User | null>(null)
  const [restoring, setRestoring] = useState(true)
  const [checkingUser, setCheckingUser] = useState(false)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [text, setText] = useState('')
  const [mode, setMode] = useState<AnalysisMode>('similar')
  const [partialMinLen, setPartialMinLen] = useState(2)
  const [result, setResult] = useState<{ text: string; data: AnalysisResult } | null>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')

  useEffect(() => {
    if (!supabase) {
      setRestoring(false)
      return
    }
    const client = supabase
    let active = true
    const { data: { subscription } } = client.auth.onAuthStateChange((_event, nextSession) => {
      if (active) {
        setSession(nextSession)
        setRestoring(false)
      }
    })
    void client.auth.getSession().then(({ data }) => {
      if (active) {
        setSession(data.session)
        setRestoring(false)
      }
    })
    return () => { active = false; subscription.unsubscribe() }
  }, [])

  useEffect(() => {
    if (!supabase || !session) {
      setUser(null)
      setCheckingUser(false)
      setResult(null)
      return
    }
    const client = supabase
    let active = true
    setCheckingUser(true)
    void client.auth.getUser().then(({ data, error }) => {
      if (active) {
        setUser(error ? null : data.user)
        setCheckingUser(false)
      }
    })
    return () => { active = false }
  }, [session?.access_token])

  async function signIn(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!supabase) return
    setBusy(true)
    setMessage('')
    const { error } = await supabase.auth.signInWithPassword({ email: email.trim(), password })
    setPassword('')
    setBusy(false)
    if (error) setMessage('로그인에 실패했습니다. 이메일과 비밀번호를 확인해 주세요.')
  }

  async function signOut() {
    setBusy(true)
    setMessage('')
    const { error } = await supabase?.auth.signOut() ?? { error: null }
    setBusy(false)
    if (error) setMessage('로그아웃에 실패했습니다. 다시 시도해 주세요.')
  }

  async function submitAnalysis(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!text.trim()) {
      setMessage('분석할 텍스트를 입력해 주세요.')
      return
    }
    setBusy(true)
    setMessage('')
    setResult(null)
    try {
      const data = await analyzeText(text, mode, partialMinLen)
      if (data.offset_unit !== 'unicode_codepoint' || !data.end_exclusive) {
        throw new Error('지원하지 않는 분석 위치 형식입니다.')
      }
      setResult({ text, data })
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '분석 중 오류가 발생했습니다.')
    } finally {
      setBusy(false)
    }
  }

  const role = user?.app_metadata?.role
  const allowed = role === 'member' || role === 'admin'

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand-mark">K<span>·</span>R</div>
      <div className="brand-name">Keyword Risk<br />Analyzer</div>
      <div className="sidebar-divider" />
      <div className="sidebar-label">WORKSPACE</div>
      <div className="nav-item active"><span className="nav-icon">⌕</span> 텍스트 분석</div>
      <div className="sidebar-bottom">
        <div className="version-chip">REACT PREVIEW · FIXED328</div>
        <p>분석 기능을 먼저 옮기는 전환용 화면입니다.</p>
      </div>
    </aside>

    <main className="main-content">
      <header className="topbar">
        <div className="breadcrumb">WORKSPACE <span>/</span> 텍스트 분석</div>
        {allowed && <div className="account">
          <span className="account-name">{user?.email}</span>
          <span className="role-pill">{role === 'admin' ? '관리자' : '사용자'}</span>
          <button className="text-button" disabled={busy} onClick={signOut}>로그아웃</button>
        </div>}
      </header>

      {!configurationReady ? <section className="state-card">
        <h1>연결 설정이 필요합니다</h1>
        <p><code>frontend/.env.example</code>을 참고해 Supabase 공개 키와 API 주소를 설정해 주세요.</p>
      </section> : restoring || checkingUser ? <section className="state-card" role="status">로그인 상태를 확인하고 있습니다…</section>
        : !session ? <section className="login-card">
          <div className="eyebrow">WELCOME BACK</div>
          <h1>계정에 로그인</h1>
          <p>기존 Keyword Risk Analyzer 계정을 사용합니다.</p>
          <form onSubmit={signIn}>
            <label htmlFor="email">이메일</label>
            <input id="email" type="email" autoComplete="username" required value={email} onChange={event => setEmail(event.target.value)} />
            <label htmlFor="password">비밀번호</label>
            <input id="password" type="password" autoComplete="current-password" required value={password} onChange={event => setPassword(event.target.value)} />
            <button className="primary-button" disabled={busy} type="submit">{busy ? '로그인 중…' : '로그인'}</button>
          </form>
          {message && <p className="error-message" role="alert">{message}</p>}
        </section> : !allowed ? <section className="state-card">
          <h1>사용 권한을 확인해 주세요</h1>
          <p>관리자가 계정에 사용자 또는 관리자 권한을 부여해야 합니다.</p>
          <button className="secondary-button" onClick={signOut}>로그아웃</button>
        </section> : <>
          <div className="page-heading">
            <div><div className="eyebrow">ANALYSIS / 01</div><h1>텍스트 분석</h1>
              <p>입력한 문장에서 등록된 키워드와 리스크 정보를 확인합니다.</p></div>
            <div className="preview-pill"><span /> 전환 프리뷰</div>
          </div>

          <form onSubmit={submitAnalysis} className="analysis-grid">
            <section className="panel editor-panel">
              <div className="panel-heading"><div><div className="panel-index">01 / INPUT</div><h2>분석할 문장</h2></div>
                <span className="counter">{Array.from(text).length.toLocaleString()} / 20,000</span></div>
              <label className="sr-only" htmlFor="analysis-text">분석할 텍스트</label>
              <textarea id="analysis-text" placeholder="분석할 문장을 여기에 입력하세요…" maxLength={20000}
                value={text} disabled={busy} onChange={event => setText(event.target.value)} />
              <div className="panel-footer">입력한 텍스트는 결과를 표시하는 동안에만 이 화면에 보관됩니다.</div>
            </section>

            <section className="panel settings-panel">
              <div className="panel-heading"><div><div className="panel-index">02 / SETTINGS</div><h2>분석 방식</h2></div></div>
              <div className="mode-options">{modes.map(option => <label key={option.value} className={`mode-option ${mode === option.value ? 'selected' : ''}`}>
                <input type="radio" name="mode" value={option.value} checked={mode === option.value} disabled={busy}
                  onChange={() => setMode(option.value)} />
                <span className="mode-copy"><strong>{option.label}</strong><small>{option.description}</small></span>
              </label>)}</div>
              {mode === 'partial' && <label className="number-setting">최소 일치 글자 수
                <input type="number" min={2} max={30} value={partialMinLen} disabled={busy}
                  onChange={event => setPartialMinLen(Number(event.target.value))} /></label>}
              <button type="submit" className="primary-button analyze-button" disabled={busy || !text.trim()}>
                {busy ? '분석 중…' : '텍스트 분석하기'} <span aria-hidden="true">↗</span>
              </button>
            </section>
          </form>

          {message && <div className="error-message inline-error" role="alert">{message}</div>}
          {result && <section className="results-section" aria-live="polite">
            <div className="results-heading"><div><div className="eyebrow">RESULT / 03</div><h2>분석 결과</h2></div>
              <div className="result-count"><strong>{result.data.matches.length}</strong>건 발견</div></div>
            <div className="panel preview-panel"><h3>문장 속 키워드</h3>
              <HighlightedText text={result.text} matches={result.data.matches} /></div>
            {result.data.matches.length > 0 ? <div className="panel table-panel"><div className="table-scroll"><table>
              <thead><tr><th>키워드</th><th>상품 카테고리</th><th>리스크 등급</th><th>심의 기준</th><th>위치</th></tr></thead>
              <tbody>{result.data.matches.map((match, index) => <tr key={`${match.start}-${match.end}-${index}`}>
                <td><strong>{match.term}</strong></td><td>{match.category || '—'}</td>
                <td>{match.risk || '—'}</td><td>{match.detail || '—'}</td>
                <td>{match.start + 1}–{match.end}</td>
              </tr>)}</tbody>
            </table></div></div> : <p className="empty-result">일치하는 등록 키워드가 없습니다.</p>}
            <p className="result-note">이 프리뷰는 분석 결과 조회만 제공합니다. 기존 앱의 미매칭 후보 수집과 통계 기록은 아직 연결되지 않았습니다.</p>
          </section>}
        </>}
    </main>
  </div>
}

export default App
