import { useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react'
import type { Session, User } from '@supabase/supabase-js'
import { analyzeText, configurationReady, loadAnalysisFilters, supabase,
  loadKeywords, loadTopKeywords, type AnalysisInput, type AnalysisMode, type AnalysisResult,
  type AnalysisFilters, type KeywordRow, type Match, type TopKeyword } from './api'

const modes: { value: AnalysisMode; label: string; description: string }[] = [
  { value: 'similar', label: '유사 키워드 포함', description: '등록된 표현과 변형을 함께 찾습니다.' },
  { value: 'exact', label: '정확 일치', description: '등록된 표현을 그대로 찾습니다.' },
  { value: 'partial', label: '부분 일치', description: '연속된 키워드 조각을 찾습니다.' },
]

function HighlightedText({ text, matches }: { text: string; matches: Match[] }) {
  // API offsets count Unicode code points; JavaScript string slicing counts UTF-16 units.
  const characters = Array.from(text)
  const pieces: ReactNode[] = []
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})
  const [selectedKeyword, setSelectedKeyword] = useState<string | null>(null)
  let cursor = 0
  const sorted = [...matches].sort((a, b) => a.start - b.start || b.end - a.end)
  const groups: Match[][] = []
  for (const match of sorted) {
    const lastGroup = groups[groups.length - 1]
    if (lastGroup && lastGroup[0].start === match.start && lastGroup[0].end === match.end) lastGroup.push(match)
    else groups.push([match])
  }
  for (const group of groups) {
    const match = group[0]
    if (!Number.isInteger(match.start) || !Number.isInteger(match.end) ||
        match.start < cursor || match.end > characters.length || match.end <= match.start) continue
    if (match.start > cursor) pieces.push(characters.slice(cursor, match.start).join(''))
    const key = `${match.start}-${match.end}`
    const keywords = group.filter((item, index) => item.kwd_no &&
      group.findIndex(candidate => candidate.kwd_no === item.kwd_no) === index)
    const selectedMatch = selectedKeyword ? group.find(item => item.kwd_no === selectedKeyword) : undefined
    pieces.push(<span className="highlight-group" key={key}>
      <button className="highlight-toggle" aria-expanded={Boolean(expanded[key])}
        onClick={() => setExpanded(previous => ({ ...previous, [key]: !previous[key] }))}>
        <mark title={group.map(item => item.term).join(', ')}>{characters.slice(match.start, match.end).join('')}</mark>
      </button>
      {expanded[key] && keywords.length > 0 && <span className="highlight-keywords" aria-label="연결된 키워드 번호">
        {keywords.map((item, index) => <button className="keyword-tag" key={item.kwd_no ?? index}
          aria-expanded={selectedKeyword === item.kwd_no}
          onClick={() => setSelectedKeyword(selectedKeyword === item.kwd_no ? null : item.kwd_no)}>{item.kwd_no}</button>)}
        {selectedMatch && <span className="keyword-detail"><strong>{selectedMatch.term}</strong>
          <span>{[selectedMatch.category, selectedMatch.risk].filter(Boolean).join(' · ') || '분류 정보 없음'}</span>
          {selectedMatch.detail && <small>{selectedMatch.detail}</small>}
        </span>}
      </span>}
    </span>)
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
  const [options, setOptions] = useState({ strip_bracket_notes: true, normalize_whitespace: true,
    ignore_case: true, normalize_symbols: true })
  const [filters, setFilters] = useState<AnalysisFilters>({ categories: [], risks: [], evidence_types: [] })
  const [categories, setCategories] = useState<string[]>([])
  const [risks, setRisks] = useState<string[]>([])
  const [filterMessage, setFilterMessage] = useState('')
  const pending = useRef<{ payload: string; id: string } | null>(null)
  const [result, setResult] = useState<{ text: string; data: AnalysisResult } | null>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [page, setPage] = useState<'analysis' | 'keywords' | 'report'>('analysis')
  const [keywordSearch, setKeywordSearch] = useState('')
  const [keywordQuery, setKeywordQuery] = useState('')
  const [keywordOffset, setKeywordOffset] = useState(0)
  const [keywordFilter, setKeywordFilter] = useState({ category: '', risk: '', evidenceType: '' })
  const [keywordPage, setKeywordPage] = useState<{ total: number; revision: string | null; items: KeywordRow[] } | null>(null)
  const [keywordBusy, setKeywordBusy] = useState(false)
  const [keywordError, setKeywordError] = useState('')
  const [reportDays, setReportDays] = useState(7)
  const [reportLimit, setReportLimit] = useState(10)
  const [reportItems, setReportItems] = useState<TopKeyword[]>([])
  const [reportBusy, setReportBusy] = useState(false)
  const [reportError, setReportError] = useState('')

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
      pending.current = null
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

  useEffect(() => {
    if (!user || !['member', 'admin'].includes(user.app_metadata?.role)) return
    let active = true
    void loadAnalysisFilters().then(data => {
      if (active) { setFilters(data); setFilterMessage('') }
    }).catch(() => {
      if (active) setFilterMessage('필터 목록을 불러오지 못했습니다. 분석은 계속할 수 있습니다.')
    })
    return () => { active = false }
  }, [user?.id])

  useEffect(() => { setResult(null) }, [text, mode, partialMinLen, options, categories, risks])

  useEffect(() => {
    if (page !== 'keywords' || !user || !['member', 'admin'].includes(user.app_metadata?.role)) return
    let active = true
    setKeywordBusy(true)
    setKeywordError('')
    void loadKeywords(keywordOffset, keywordQuery, keywordFilter).then(data => {
      if (active) setKeywordPage(data)
    }).catch(error => {
      if (active) setKeywordError(error instanceof Error ? error.message : '키워드 목록을 불러오지 못했습니다.')
    }).finally(() => { if (active) setKeywordBusy(false) })
    return () => { active = false }
  }, [page, user?.id, keywordOffset, keywordQuery, keywordFilter])

  useEffect(() => {
    if (page !== 'report' || !user || !['member', 'admin'].includes(user.app_metadata?.role)) return
    let active = true
    setReportBusy(true)
    setReportError('')
    void loadTopKeywords(reportDays, reportLimit).then(data => {
      if (active) setReportItems(data.items)
    }).catch(error => {
      if (active) setReportError(error instanceof Error ? error.message : '리포트를 불러오지 못했습니다.')
    }).finally(() => { if (active) setReportBusy(false) })
    return () => { active = false }
  }, [page, user?.id, reportDays, reportLimit])

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
      const input: AnalysisInput = { text, mode, partial_min_len: partialMinLen,
        ...options, categories, risks }
      const payload = JSON.stringify(input)
      const id = pending.current?.payload === payload ? pending.current.id : crypto.randomUUID()
      pending.current = { payload, id }
      const data = await analyzeText(input, id)
      if (data.offset_unit !== 'unicode_codepoint' || !data.end_exclusive) {
        throw new Error('지원하지 않는 분석 위치 형식입니다.')
      }
      setResult({ text, data })
      pending.current = null
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '분석 중 오류가 발생했습니다.')
    } finally {
      setBusy(false)
    }
  }

  const role = user?.app_metadata?.role
  const allowed = role === 'member' || role === 'admin'

  function toggleFilter(value: string, selected: string[], setSelected: (values: string[]) => void) {
    setSelected(selected.includes(value) ? selected.filter(item => item !== value) : [...selected, value])
  }

  function downloadCsv() {
    if (!result) return
    const cells = [
      ['kwd_no', '키워드명', '상품카테고리', '리스크등급', '심의기준', '시작위치', '끝위치'],
      ...result.data.matches.map(match => [match.kwd_no ?? '', match.term, match.category,
        match.risk, match.detail, String(match.start), String(match.end)]),
    ]
    const csv = '\uFEFF' + cells.map(row => row.map(value => `"${value.replaceAll('"', '""')}"`).join(',')).join('\r\n')
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }))
    const link = document.createElement('a')
    link.href = url
    link.download = 'analysis_results.csv'
    document.body.append(link)
    link.click()
    link.remove()
    window.setTimeout(() => URL.revokeObjectURL(url), 1000)
  }

  function downloadReportCsv() {
    const rows = [
      ['검색순위', 'kwd_no', '키워드명', '기간내_조회수'],
      ...reportItems.map((item, index) => [String(index + 1), item.kwd_no, item.term ?? '', String(item.hit_count)]),
    ]
    const csv = '\uFEFF' + rows.map(row => row.map(value => `"${value.replaceAll('"', '""')}"`).join(',')).join('\r\n')
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }))
    const link = document.createElement('a')
    link.href = url
    link.download = `top_keywords_${reportDays}days.csv`
    document.body.append(link)
    link.click()
    link.remove()
    window.setTimeout(() => URL.revokeObjectURL(url), 1000)
  }

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand-mark">K<span>·</span>R</div>
      <div className="brand-name">Keyword Risk<br />Analyzer</div>
      <div className="sidebar-divider" />
      <div className="sidebar-label">WORKSPACE</div>
      <button className={`nav-item nav-button ${page === 'analysis' ? 'active' : ''}`} onClick={() => setPage('analysis')}>
        <span className="nav-icon">⌕</span> 텍스트 분석
      </button>
      <button className={`nav-item nav-button ${page === 'keywords' ? 'active' : ''}`} onClick={() => setPage('keywords')}>
        <span className="nav-icon">▤</span> 키워드 원장
      </button>
      <button className={`nav-item nav-button ${page === 'report' ? 'active' : ''}`} onClick={() => setPage('report')}>
        <span className="nav-icon">↗</span> 분석 리포트
      </button>
      <div className="sidebar-bottom">
        <div className="version-chip">REACT PREVIEW</div>
        <p>분석 기능을 먼저 옮기는 전환용 화면입니다.</p>
      </div>
    </aside>

    <main className="main-content">
      <header className="topbar">
        <div className="breadcrumb">WORKSPACE <span>/</span> {page === 'analysis' ? '텍스트 분석' : page === 'keywords' ? '키워드 원장' : '분석 리포트'}</div>
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
        </section> : page === 'report' ? <>
          <div className="page-heading">
            <div><div className="eyebrow">REPORT / 03</div><h1>분석 리포트</h1>
              <p>선택한 최근 기간에 가장 많이 검출된 키워드를 보여줍니다.</p></div>
              <div className="preview-pill"><span /> 공유 집계</div>
          </div>
          <section className="catalog-section">
            <div className="panel report-panel">
              <div className="report-controls">
                <label>조회 기간
                  <select value={reportDays} onChange={event => setReportDays(Number(event.target.value))}>
                    <option value={7}>최근 7일</option><option value={30}>최근 30일</option>
                    <option value={90}>최근 90일</option>
                  </select>
                </label>
                <label>표시 개수
                  <input type="number" min={1} max={100} value={reportLimit}
                    onChange={event => setReportLimit(Math.min(100, Math.max(1, Number(event.target.value) || 1)))} />
                </label>
                {reportItems.length > 0 && <button className="secondary-button" onClick={downloadReportCsv}>CSV 다운로드</button>}
              </div>
              <p className="report-period-note">최근 {reportDays}일의 공유 분석 기록 기준입니다.</p>
              {reportBusy && <p className="catalog-status" role="status">리포트를 불러오는 중…</p>}
              {reportError && <p className="error-message" role="alert">{reportError}</p>}
              {!reportBusy && !reportError && (reportItems.length ? <div className="table-scroll"><table>
                <thead><tr><th>순위</th><th>키워드 번호</th><th>키워드명</th><th>기간 내 조회수</th></tr></thead>
                <tbody>{reportItems.map((item, index) => <tr key={item.kwd_no}>
                  <td>{index + 1}</td><td>{item.kwd_no}</td><td><strong>{item.term || '등록 키워드 정보 없음'}</strong></td>
                  <td>{item.hit_count.toLocaleString()}</td>
                </tr>)}</tbody>
              </table></div> : <p className="empty-result">해당 기간에 분석 기록이 없습니다.</p>)}
            </div>
          </section>
        </> : page === 'keywords' ? <>
          <div className="page-heading">
            <div><div className="eyebrow">CATALOG / 02</div><h1>키워드 원장</h1>
              <p>등록된 키워드와 분류 정보를 조회합니다. 원장 수정은 기존 관리자 화면에서 할 수 있습니다.</p></div>
            <div className="preview-pill"><span /> 읽기 전용</div>
          </div>
          <section className="catalog-section">
            <div className="panel catalog-panel">
              <form className="catalog-search" onSubmit={event => {
                event.preventDefault()
                setKeywordOffset(0)
                setKeywordQuery(keywordSearch.trim())
              }}>
                <label className="sr-only" htmlFor="keyword-search">번호, 키워드명 또는 대체 키워드 검색</label>
                <input id="keyword-search" value={keywordSearch} maxLength={200}
                  placeholder="번호·키워드명·대체 키워드 검색" onChange={event => setKeywordSearch(event.target.value)} />
                <select aria-label="카테고리 필터" value={keywordFilter.category}
                  onChange={event => { setKeywordOffset(0); setKeywordFilter({ ...keywordFilter, category: event.target.value }) }}>
                  <option value="">전체 카테고리</option>{filters.categories.map(value => <option key={value}>{value}</option>)}
                </select>
                <select aria-label="리스크 필터" value={keywordFilter.risk}
                  onChange={event => { setKeywordOffset(0); setKeywordFilter({ ...keywordFilter, risk: event.target.value }) }}>
                  <option value="">전체 리스크</option>{filters.risks.map(value => <option key={value}>{value}</option>)}
                </select>
                <select aria-label="증빙 자료 필터" value={keywordFilter.evidenceType}
                  onChange={event => { setKeywordOffset(0); setKeywordFilter({ ...keywordFilter, evidenceType: event.target.value }) }}>
                  <option value="">전체 증빙 유형</option>{(filters.evidence_types ?? []).map(value => <option key={value}>{value}</option>)}
                </select>
                <button className="primary-button" type="submit" disabled={keywordBusy}>검색</button>
              </form>
              <div className="catalog-meta">
                <span>{keywordBusy ? '목록을 불러오는 중…' : `${keywordPage?.total ?? 0}개 키워드`}</span>
                {keywordPage?.revision && <span>원장 버전 {keywordPage.revision}</span>}
              </div>
              {keywordError && <p className="error-message" role="alert">{keywordError}</p>}
              {!keywordError && <div className="table-scroll"><table>
                <thead><tr><th>번호</th><th>키워드명</th><th>카테고리</th><th>리스크</th><th>대체 키워드</th><th>심의 기준</th><th>증빙 자료</th></tr></thead>
                <tbody>{keywordPage?.items.map(row => <tr key={row.kwd_no}>
                  <td>{row.kwd_no}</td><td><strong>{row.키워드명}</strong></td><td>{row.상품카테고리 || '—'}</td>
                  <td>{row['리스크 등급'] || '—'}</td><td>{row.대체키워드 || '—'}</td>
                  <td>{row.리스크 등급별 세부 심의기준 || '—'}</td><td>{row.증빙자료유형 || '—'}</td>
                </tr>)}</tbody>
              </table></div>}
              {keywordPage && <div className="catalog-pagination">
                <button className="secondary-button" disabled={keywordBusy || keywordOffset === 0}
                  onClick={() => setKeywordOffset(Math.max(0, keywordOffset - 100))}>이전</button>
                <span>{keywordPage.total ? `${keywordOffset + 1}–${Math.min(keywordOffset + 100, keywordPage.total)} / ${keywordPage.total}` : '0개'}</span>
                <button className="secondary-button" disabled={keywordBusy || keywordOffset + 100 >= keywordPage.total}
                  onClick={() => setKeywordOffset(keywordOffset + 100)}>다음</button>
              </div>}
            </div>
          </section>
        </> : <>
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
                <input type="number" min={2} max={20} value={partialMinLen} disabled={busy}
                  onChange={event => setPartialMinLen(Number(event.target.value))} /></label>}
              <details className="analysis-options"><summary>사전 필터 및 매칭 옵션</summary>
                {filterMessage && <p className="filter-message">{filterMessage}</p>}
                <div className="filter-label">상품 카테고리</div>
                <div className="filter-list">{filters.categories.map(value => <label key={value}>
                  <input type="checkbox" disabled={busy} checked={categories.includes(value)}
                    onChange={() => toggleFilter(value, categories, setCategories)} />{value}
                </label>)}</div>
                <div className="filter-label">리스크 등급</div>
                <div className="filter-list">{filters.risks.map(value => <label key={value}>
                  <input type="checkbox" disabled={busy} checked={risks.includes(value)}
                    onChange={() => toggleFilter(value, risks, setRisks)} />{value}
                </label>)}</div>
                <div className="filter-label">매칭 옵션</div>
                {([
                  ['strip_bracket_notes', '등록 키워드의 괄호 설명 제외'],
                  ['normalize_whitespace', '띄어쓰기·줄바꿈 차이 허용'],
                  ['ignore_case', '영문 대소문자 무시'],
                  ['normalize_symbols', '설정된 기호를 공백으로 처리'],
                ] as const).map(([key, label]) => <label className="option-check" key={key}>
                  <input type="checkbox" disabled={busy} checked={options[key]}
                    onChange={event => setOptions({ ...options, [key]: event.target.checked })} />{label}
                </label>)}
              </details>
              <button type="submit" className="primary-button analyze-button" disabled={busy || !text.trim()}>
                {busy ? '분석 중…' : '텍스트 분석하기'} <span aria-hidden="true">↗</span>
              </button>
            </section>
          </form>

          {message && <div className="error-message inline-error" role="alert">{message}</div>}
          {result && <section className="results-section" aria-live="polite">
            <div className="results-heading"><div><div className="eyebrow">RESULT / 03</div><h2>분석 결과</h2></div>
              <div className="results-actions"><div className="result-count"><strong>{result.data.unique_keywords.length}</strong>개 키워드 · {result.data.matches.length}회 발견</div>
                {result.data.matches.length > 0 && <button className="secondary-button" onClick={downloadCsv}>CSV 다운로드</button>}
              </div></div>
            <div className="panel preview-panel"><h3>문장 속 키워드</h3>
              <p className="highlight-help">검출 문구를 누르면 연결된 키워드 번호를, 번호를 누르면 상세 정보를 확인할 수 있습니다.</p>
              <HighlightedText text={result.text} matches={result.data.matches} /></div>
            {result.data.matches.length > 0 ? <div className="panel table-panel"><div className="table-scroll"><table>
              <thead><tr><th>키워드</th><th>상품 카테고리</th><th>리스크 등급</th><th>심의 기준</th><th>위치</th></tr></thead>
              <tbody>{result.data.matches.map((match, index) => <tr key={`${match.start}-${match.end}-${index}`}>
                <td><strong>{match.term}</strong></td><td>{match.category || '—'}</td>
                <td>{match.risk || '—'}</td><td>{match.detail || '—'}</td>
                <td>{match.start + 1}–{match.end}</td>
              </tr>)}</tbody>
            </table></div></div> : <p className="empty-result">일치하는 등록 키워드가 없습니다.</p>}
            <p className="result-note">분석 기록과 미매칭 후보 수집이 완료되었습니다. 동일 요청 재시도에는 같은 분석 ID를 사용합니다.</p>
          </section>}
        </>}
    </main>
  </div>
}

export default App
