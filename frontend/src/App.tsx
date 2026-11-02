import { useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react'
import type { Session, User } from '@supabase/supabase-js'
import { analyzeText, configurationReady, loadAnalysisFilters, supabase,
  askRegulation, loadAllKeywords, loadKeywords, loadTopKeywords, type AnalysisInput, type AnalysisMode,
  type AnalysisResult, type AnalysisFilters, type KeywordRow, type Match, type RegulationQuestion,
  type RegulationResult, type TopKeyword, type UnmatchedTerm, exportUnmatchedTerms, loadUnmatchedTerms,
  submitUnmatchedRegistrationRequests, findKeywords, loadKeywordRequests,
  submitKeywordRequest, updateKeywordRequest, type KeywordRequestRecord, loadAdminUsers,
  updateAdminUserRole, type AdminUser, loadKeywordSnapshot, saveAdminKeywords } from './api'

const modes: { value: AnalysisMode; label: string; description: string }[] = [
  { value: 'similar', label: '유사 키워드 포함', description: '등록된 표현과 변형을 함께 찾습니다.' },
  { value: 'exact', label: '정확 일치', description: '등록된 표현을 그대로 찾습니다.' },
  { value: 'partial', label: '부분 일치', description: '연속된 키워드 조각을 찾습니다.' },
]
const regulationStatusLabels: Record<string, string> = {
  supported: '근거가 확인됨', retrieved: '검색 자료 확인', conflict: '검토 필요', insufficient: '자료 부족',
}
const unmatchedStatusLabels: Record<string, string> = {
  pending: '검토 대기', approved: '등록 완료', registration_requested: '등록 요청', ignored: '관리자 거절',
}
const keywordRequestTypeLabels: Record<string, string> = {
  risk_grade_adjustment: '리스크 등급 조정', review_criteria_change: '심의 기준 변경',
  new_keyword_registration: '신규 키워드 등록',
}
const keywordRequestStatusLabels: Record<string, string> = {
  대기: '대기', 검토중: '검토 중', 처리완료: '처리 완료',
}
type EditableKeywordField = '상품카테고리' | '리스크 등급' | '대체키워드' |
  '리스크 등급별 세부 심의기준' | '증빙자료유형'
type NewKeywordForm = { term: string; category: string; risk: string; alternative: string; criteria: string; evidenceType: string }

function nextKeywordCode(category: string, rows: KeywordRow[]) {
  const categoryRows = rows.filter(row => row.상품카테고리.trim() === category.trim())
  const codePattern = /^([A-Z]+)(\d{3,})$/
  const categoryCodes = categoryRows.map(row => row.kwd_no.match(codePattern)).filter(Boolean)
  let prefix = ''
  if (categoryCodes.length) {
    const counts = new Map<string, number>()
    for (const code of categoryCodes) counts.set(code![1], (counts.get(code![1]) ?? 0) + 1)
    prefix = [...counts].sort((left, right) => right[1] - left[1])[0][0]
  } else {
    const defaultPrefixes: Record<string, string> = {
      '공통(전체)': 'A', '식품': 'F', '건강기능식품': 'G', '화장품': 'B', '공산품': 'I',
    }
    const initial = category.trim().charAt(0).toLocaleUpperCase()
    prefix = defaultPrefixes[category.trim()] ?? (/^[A-Z]$/.test(initial) ? initial : 'U')
  }
  const digitValues = (items: KeywordRow[]) => items.map(row => row.kwd_no.match(codePattern))
    .filter((match): match is RegExpMatchArray => Boolean(match && match[1] === prefix))
  const matchingCategoryCodes = digitValues(categoryRows)
  const allMatchingCodes = digitValues(rows)
  const source = matchingCategoryCodes.length ? matchingCategoryCodes : allMatchingCodes
  const next = source.reduce((max, match) => Math.max(max, Number(match[2])), 0) + 1
  const width = Math.max(3, ...matchingCategoryCodes.map(match => match[2].length))
  return `${prefix}${String(next).padStart(width, '0')}`
}

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
  const [authMode, setAuthMode] = useState<'login' | 'request-reset' | 'new-password' | 'password-updated'>('login')
  const [resetEmailSent, setResetEmailSent] = useState(false)
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
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
  const [page, setPage] = useState<'analysis' | 'keywords' | 'report' | 'regulation' | 'unmatched' | 'requests' | 'users' | 'keyword-admin'>('analysis')
  const [keywordSearch, setKeywordSearch] = useState('')
  const [keywordQuery, setKeywordQuery] = useState('')
  const [keywordOffset, setKeywordOffset] = useState(0)
  const [keywordFilter, setKeywordFilter] = useState({ category: '', risk: '', evidenceType: '' })
  const [keywordPage, setKeywordPage] = useState<{ total: number; revision: number | null; items: KeywordRow[] } | null>(null)
  const [keywordBusy, setKeywordBusy] = useState(false)
  const [keywordExportBusy, setKeywordExportBusy] = useState(false)
  const [keywordError, setKeywordError] = useState('')
  const [reportDays, setReportDays] = useState(7)
  const [reportLimit, setReportLimit] = useState(10)
  const [reportItems, setReportItems] = useState<TopKeyword[]>([])
  const [reportBusy, setReportBusy] = useState(false)
  const [reportError, setReportError] = useState('')
  const [regulationDirection, setRegulationDirection] = useState<RegulationQuestion['direction']>('keyword_to_law')
  const [regulationQuery, setRegulationQuery] = useState('')
  const [regulationContext, setRegulationContext] = useState('')
  const [regulationCategory, setRegulationCategory] = useState('')
  const [regulationResult, setRegulationResult] = useState<RegulationResult | null>(null)
  const [regulationBusy, setRegulationBusy] = useState(false)
  const [regulationError, setRegulationError] = useState('')
  const [unmatchedSearchInput, setUnmatchedSearchInput] = useState('')
  const [unmatchedSearch, setUnmatchedSearch] = useState('')
  const [unmatchedSort, setUnmatchedSort] = useState<'occurrences' | 'registered'>('occurrences')
  const [unmatchedOffset, setUnmatchedOffset] = useState(0)
  const [unmatchedPage, setUnmatchedPage] = useState<{ total: number; rows: UnmatchedTerm[] } | null>(null)
  const [unmatchedBusy, setUnmatchedBusy] = useState(false)
  const [unmatchedExportBusy, setUnmatchedExportBusy] = useState(false)
  const [unmatchedError, setUnmatchedError] = useState('')
  const [unmatchedRefresh, setUnmatchedRefresh] = useState(0)
  const [selectedUnmatched, setSelectedUnmatched] = useState<Record<string, UnmatchedTerm>>({})
  const [unmatchedSubmitBusy, setUnmatchedSubmitBusy] = useState(false)
  const [unmatchedActionMessage, setUnmatchedActionMessage] = useState('')
  const [requestSearch, setRequestSearch] = useState('')
  const [requestMatches, setRequestMatches] = useState<KeywordRow[]>([])
  const [selectedRequestKeyword, setSelectedRequestKeyword] = useState<KeywordRow | null>(null)
  const [requestType, setRequestType] = useState<'risk_grade_adjustment' | 'review_criteria_change'>('risk_grade_adjustment')
  const [requestDetail, setRequestDetail] = useState('')
  const [requestRecords, setRequestRecords] = useState<KeywordRequestRecord[]>([])
  const [requestDrafts, setRequestDrafts] = useState<Record<string, { status: string; reply: string }>>({})
  const [requestSavingId, setRequestSavingId] = useState<string | null>(null)
  const [requestRefresh, setRequestRefresh] = useState(0)
  const [requestBusy, setRequestBusy] = useState(false)
  const [requestSearchBusy, setRequestSearchBusy] = useState(false)
  const [requestError, setRequestError] = useState('')
  const [requestMessage, setRequestMessage] = useState('')
  const [adminUserPage, setAdminUserPage] = useState(1)
  const [adminUsers, setAdminUsers] = useState<AdminUser[]>([])
  const [adminUsersHasMore, setAdminUsersHasMore] = useState(false)
  const [adminUsersBusy, setAdminUsersBusy] = useState(false)
  const [adminUsersError, setAdminUsersError] = useState('')
  const [adminUserRefresh, setAdminUserRefresh] = useState(0)
  const [adminUserRoleDrafts, setAdminUserRoleDrafts] = useState<Record<string, 'admin' | 'member' | ''>>({})
  const [adminUserSavingId, setAdminUserSavingId] = useState<string | null>(null)
  const [adminUserMessage, setAdminUserMessage] = useState('')
  const [adminKeywordRows, setAdminKeywordRows] = useState<KeywordRow[]>([])
  const [adminKeywordRevision, setAdminKeywordRevision] = useState<number | null>(null)
  const [adminKeywordSearch, setAdminKeywordSearch] = useState('')
  const [adminKeywordPageNumber, setAdminKeywordPageNumber] = useState(1)
  const [adminKeywordBusy, setAdminKeywordBusy] = useState(false)
  const [adminKeywordSaving, setAdminKeywordSaving] = useState(false)
  const [adminKeywordDirty, setAdminKeywordDirty] = useState(false)
  const [adminKeywordRefresh, setAdminKeywordRefresh] = useState(0)
  const [adminKeywordError, setAdminKeywordError] = useState('')
  const [adminKeywordMessage, setAdminKeywordMessage] = useState('')
  const [newKeywordOpen, setNewKeywordOpen] = useState(false)
  const [newKeywordForm, setNewKeywordForm] = useState<NewKeywordForm>({
    term: '', category: '', risk: '', alternative: '-', criteria: '', evidenceType: '',
  })

  useEffect(() => {
    if (!supabase) {
      setRestoring(false)
      return
    }
    const client = supabase
    let active = true
    const { data: { subscription } } = client.auth.onAuthStateChange((event, nextSession) => {
      if (active) {
        if (event === 'PASSWORD_RECOVERY') setAuthMode('new-password')
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

  useEffect(() => {
    if (page !== 'unmatched' || !user || !['member', 'admin'].includes(user.app_metadata?.role)) return
    let active = true
    setUnmatchedBusy(true)
    setUnmatchedError('')
    void loadUnmatchedTerms(unmatchedOffset, unmatchedSearch, unmatchedSort).then(data => {
      if (active) setUnmatchedPage(data)
    }).catch(error => {
      if (active) setUnmatchedError(error instanceof Error ? error.message : '미매칭 후보를 불러오지 못했습니다.')
    }).finally(() => { if (active) setUnmatchedBusy(false) })
    return () => { active = false }
  }, [page, user?.id, unmatchedOffset, unmatchedSearch, unmatchedSort, unmatchedRefresh])

  useEffect(() => {
    if (page !== 'requests' || !user || !['member', 'admin'].includes(user.app_metadata?.role)) return
    let active = true
    setRequestBusy(true)
    setRequestError('')
    void loadKeywordRequests().then(items => {
      if (active) {
        setRequestRecords(items)
        setRequestDrafts(Object.fromEntries(items.map(item => [item.id,
          { status: item.status, reply: item.admin_reply ?? '' }])))
      }
    }).catch(error => {
      if (active) setRequestError(error instanceof Error ? error.message : '문의 내역을 불러오지 못했습니다.')
    }).finally(() => { if (active) setRequestBusy(false) })
    return () => { active = false }
  }, [page, user?.id, requestRefresh])

  useEffect(() => {
    if (page !== 'users' || user?.app_metadata?.role !== 'admin') return
    let active = true
    setAdminUsersBusy(true)
    setAdminUsersError('')
    void loadAdminUsers(adminUserPage).then(data => {
      if (active) {
        setAdminUsers(data.items)
        setAdminUsersHasMore(data.has_more)
        setAdminUserRoleDrafts(Object.fromEntries(data.items.map(item => [item.id, item.role ?? ''])))
      }
    }).catch(error => {
      if (active) setAdminUsersError(error instanceof Error ? error.message : '계정 목록을 불러오지 못했습니다.')
    }).finally(() => { if (active) setAdminUsersBusy(false) })
    return () => { active = false }
  }, [page, user?.id, user?.app_metadata?.role, adminUserPage, adminUserRefresh])

  useEffect(() => {
    if (page !== 'keyword-admin' || user?.app_metadata?.role !== 'admin') return
    let active = true
    setAdminKeywordBusy(true)
    setAdminKeywordError('')
    void loadKeywordSnapshot().then(snapshot => {
      if (active) {
        setAdminKeywordRows(snapshot.items)
        setAdminKeywordRevision(snapshot.revision)
        setAdminKeywordDirty(false)
      }
    }).catch(error => {
      if (active) setAdminKeywordError(error instanceof Error ? error.message : '키워드 원장을 불러오지 못했습니다.')
    }).finally(() => { if (active) setAdminKeywordBusy(false) })
    return () => { active = false }
  }, [page, user?.id, user?.app_metadata?.role, adminKeywordRefresh])

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

  async function requestPasswordReset(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!supabase) return
    setBusy(true)
    setMessage('')
    const { error } = await supabase.auth.resetPasswordForEmail(email.trim(), {
      redirectTo: window.location.origin,
    })
    setBusy(false)
    if (error) setMessage('비밀번호 재설정 메일을 보내지 못했습니다. 이메일 주소와 설정을 확인해 주세요.')
    else setResetEmailSent(true)
  }

  async function changePassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!supabase) return
    if (newPassword !== confirmPassword) {
      setMessage('새 비밀번호가 서로 다릅니다.')
      return
    }
    setBusy(true)
    setMessage('')
    const { error } = await supabase.auth.updateUser({ password: newPassword })
    setBusy(false)
    if (error) setMessage('비밀번호를 변경하지 못했습니다. 새 비밀번호를 확인해 주세요.')
    else setAuthMode('password-updated')
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

  async function submitRegulation(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setRegulationBusy(true)
    setRegulationError('')
    setRegulationResult(null)
    try {
      const question: RegulationQuestion = { direction: regulationDirection,
        query: regulationQuery.trim(),
        context_text: regulationDirection === 'keyword_to_law' ? regulationContext : '',
        category: regulationCategory }
      setRegulationResult(await askRegulation(question))
    } catch (error) {
      setRegulationError(error instanceof Error ? error.message : '법령 검색을 완료하지 못했습니다.')
    } finally {
      setRegulationBusy(false)
    }
  }

  const role = user?.app_metadata?.role
  const allowed = role === 'member' || role === 'admin'
  const selectedUnmatchedCount = Object.keys(selectedUnmatched).length
  const adminKeywordMatches = adminKeywordRows.filter(row => {
    const query = adminKeywordSearch.trim().toLocaleLowerCase()
    return !query || [row.kwd_no, row.키워드명, row.대체키워드].some(value => value.toLocaleLowerCase().includes(query))
  })
  const adminKeywordPageCount = Math.max(1, Math.ceil(adminKeywordMatches.length / 50))
  const adminKeywordPageRows = adminKeywordMatches.slice((adminKeywordPageNumber - 1) * 50, adminKeywordPageNumber * 50)

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

  async function exportKeywordCatalog() {
    setKeywordExportBusy(true)
    setKeywordError('')
    try {
      const rows = await loadAllKeywords()
      const headers = ['kwd_no', '키워드명', '상품카테고리', '리스크 등급', '대체키워드',
        '리스크 등급별 세부 심의기준', '증빙자료유형', '키워드 조회 수(누적카운트)', '마지막 출력일자']
      const csvRows = [headers, ...rows.map(row => [row.kwd_no, row.키워드명, row.상품카테고리,
        row['리스크 등급'], row.대체키워드, row['리스크 등급별 세부 심의기준'],
        row.증빙자료유형, row['키워드 조회 수(누적카운트)'], row['마지막 출력일자']]
        .map(value => String(value ?? '')))]
      const csv = '\uFEFF' + csvRows.map(row => row.map(value => `"${value.replaceAll('"', '""')}"`).join(',')).join('\r\n')
      const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }))
      const link = document.createElement('a')
      link.href = url
      link.download = 'keyword_catalog.csv'
      document.body.append(link)
      link.click()
      link.remove()
      window.setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (error) {
      setKeywordError(error instanceof Error ? error.message : '원장 CSV를 만들지 못했습니다.')
    } finally {
      setKeywordExportBusy(false)
    }
  }

  async function exportUnmatchedCsv() {
    setUnmatchedExportBusy(true)
    setUnmatchedError('')
    try {
      const rows = await exportUnmatchedTerms()
      const headers = ['미매칭 표현', '누적 출현 횟수', '분석 횟수', '상태', '최초 수집 시각', '최근 수집 시각']
      const labels: Record<string, string> = { pending: '검토 대기', approved: '등록 완료',
        registration_requested: '신규 키워드 등록 요청', ignored: '관리자 거절' }
      const formatDate = (value: string) => value ? new Date(value).toLocaleString('ko-KR') : ''
      const csvRows = [headers, ...rows.map(row => [row.display_term, String(row.total_occurrences),
        String(row.analysis_count), labels[row.review_status] ?? row.review_status,
        formatDate(row.first_seen), formatDate(row.last_seen)])]
      const csv = '\uFEFF' + csvRows.map(row => row.map(value => `"${value.replaceAll('"', '""')}"`).join(',')).join('\r\n')
      const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }))
      const link = document.createElement('a')
      link.href = url
      link.download = 'unmatched_candidates.csv'
      document.body.append(link)
      link.click()
      link.remove()
      window.setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (error) {
      setUnmatchedError(error instanceof Error ? error.message : '미매칭 후보 CSV를 만들지 못했습니다.')
    } finally {
      setUnmatchedExportBusy(false)
    }
  }

  function toggleUnmatchedRow(row: UnmatchedTerm, checked: boolean) {
    setSelectedUnmatched(previous => {
      const next = { ...previous }
      if (checked) next[row.term_norm] = row
      else delete next[row.term_norm]
      return next
    })
  }

  function toggleUnmatchedPage(checked: boolean) {
    const selectable = (unmatchedPage?.rows ?? []).filter(row => row.review_status === 'pending')
    setSelectedUnmatched(previous => {
      const next = { ...previous }
      for (const row of selectable) {
        if (checked) next[row.term_norm] = row
        else delete next[row.term_norm]
      }
      return next
    })
  }

  async function submitUnmatchedRequests() {
    const rows = Object.values(selectedUnmatched)
    if (!rows.length) return
    setUnmatchedSubmitBusy(true)
    setUnmatchedError('')
    setUnmatchedActionMessage('')
    try {
      const result = await submitUnmatchedRegistrationRequests(rows.map(row => ({
        term: row.display_term, source_terms: row.display_term, occurrences: row.total_occurrences,
      })))
      setSelectedUnmatched({})
      setUnmatchedActionMessage(`${result.items.length}개 후보를 관리자 검토 요청으로 접수했습니다.`)
      setUnmatchedRefresh(value => value + 1)
    } catch (error) {
      setUnmatchedError(error instanceof Error ? error.message : '등록 요청을 접수하지 못했습니다.')
    } finally {
      setUnmatchedSubmitBusy(false)
    }
  }

  async function searchRequestKeywords(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!requestSearch.trim()) return
    setRequestSearchBusy(true)
    setRequestError('')
    setSelectedRequestKeyword(null)
    try {
      setRequestMatches(await findKeywords(requestSearch.trim()))
    } catch (error) {
      setRequestError(error instanceof Error ? error.message : '키워드를 찾지 못했습니다.')
    } finally {
      setRequestSearchBusy(false)
    }
  }

  async function submitKeywordInquiry(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!selectedRequestKeyword || !requestDetail.trim()) return
    setRequestBusy(true)
    setRequestError('')
    setRequestMessage('')
    try {
      await submitKeywordRequest({ kwd_no: selectedRequestKeyword.kwd_no, request_type: requestType,
        request_detail: requestDetail.trim() })
      setRequestDetail('')
      setSelectedRequestKeyword(null)
      setRequestMatches([])
      setRequestMessage('문의가 접수되었습니다.')
      setRequestRefresh(value => value + 1)
    } catch (error) {
      setRequestError(error instanceof Error ? error.message : '문의를 접수하지 못했습니다.')
    } finally {
      setRequestBusy(false)
    }
  }

  async function saveKeywordRequest(requestId: string) {
    const draft = requestDrafts[requestId]
    if (!draft) return
    setRequestSavingId(requestId)
    setRequestError('')
    setRequestMessage('')
    try {
      await updateKeywordRequest(requestId, draft.status, draft.reply)
      setRequestMessage('문의 처리 상태와 답변을 저장했습니다.')
      setRequestRefresh(value => value + 1)
    } catch (error) {
      setRequestError(error instanceof Error ? error.message : '문의 처리 내용을 저장하지 못했습니다.')
    } finally {
      setRequestSavingId(null)
    }
  }

  async function saveAdminUserRole(item: AdminUser) {
    const nextRole = adminUserRoleDrafts[item.id]
    if (!nextRole || nextRole === item.role) return
    setAdminUserSavingId(item.id)
    setAdminUsersError('')
    setAdminUserMessage('')
    try {
      await updateAdminUserRole(item.id, nextRole, item.role)
      setAdminUserMessage(`${item.email || '계정'}의 역할을 변경했습니다.`)
      setAdminUserRefresh(value => value + 1)
    } catch (error) {
      setAdminUsersError(error instanceof Error ? error.message : '계정 역할을 변경하지 못했습니다.')
    } finally {
      setAdminUserSavingId(null)
    }
  }

  function updateAdminKeyword(code: string, field: EditableKeywordField, value: string) {
    setAdminKeywordRows(previous => previous.map(row => row.kwd_no === code ? { ...row, [field]: value } : row))
    setAdminKeywordDirty(true)
    setAdminKeywordMessage('')
  }

  async function saveAdminKeywordChanges() {
    if (!adminKeywordDirty || adminKeywordRevision === null) return
    setAdminKeywordSaving(true)
    setAdminKeywordError('')
    setAdminKeywordMessage('')
    try {
      const result = await saveAdminKeywords(adminKeywordRevision, adminKeywordRows)
      setAdminKeywordRevision(result.revision)
      setAdminKeywordDirty(false)
      setAdminKeywordMessage('키워드 원장을 저장했습니다.')
    } catch (error) {
      setAdminKeywordError(error instanceof Error ? error.message : '키워드 원장을 저장하지 못했습니다.')
    } finally {
      setAdminKeywordSaving(false)
    }
  }

  function addAdminKeyword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const term = newKeywordForm.term.trim()
    const category = newKeywordForm.category.trim()
    const duplicate = adminKeywordRows.some(row => row.상품카테고리.trim() === category &&
      row.키워드명.trim().toLocaleLowerCase() === term.toLocaleLowerCase())
    if (!term || !category || !newKeywordForm.risk.trim() || !newKeywordForm.criteria.trim() || !newKeywordForm.evidenceType.trim()) {
      setAdminKeywordError('키워드명, 카테고리, 리스크, 심의 기준과 증빙 유형을 입력하세요.')
      return
    }
    if (duplicate) {
      setAdminKeywordError('같은 카테고리에 같은 키워드명이 이미 있습니다.')
      return
    }
    const code = nextKeywordCode(category, adminKeywordRows)
    if (adminKeywordRows.some(row => row.kwd_no === code)) {
      setAdminKeywordError('다음 키워드 번호가 이미 사용 중입니다. 원장을 다시 불러오세요.')
      return
    }
    const row: KeywordRow = {
      kwd_no: code, 키워드명: term, 상품카테고리: category, '리스크 등급': newKeywordForm.risk.trim(),
      대체키워드: newKeywordForm.alternative.trim() || '-',
      '리스크 등급별 세부 심의기준': newKeywordForm.criteria.trim(), 증빙자료유형: newKeywordForm.evidenceType.trim(),
      '키워드 조회 수(누적카운트)': '0', '마지막 출력일자': '',
    }
    setAdminKeywordRows(previous => [...previous, row])
    setAdminKeywordDirty(true)
    setAdminKeywordError('')
    setAdminKeywordMessage(`새 행 ${code}을 추가했습니다. 변경사항 저장을 눌러 DB에 반영하세요.`)
    setAdminKeywordSearch(code)
    setAdminKeywordPageNumber(1)
    setNewKeywordForm({ term: '', category, risk: '', alternative: '-', criteria: '', evidenceType: '' })
    setNewKeywordOpen(false)
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
      <button className={`nav-item nav-button ${page === 'regulation' ? 'active' : ''}`} onClick={() => setPage('regulation')}>
        <span className="nav-icon">§</span> 법령 근거 검색
      </button>
      <button className={`nav-item nav-button ${page === 'unmatched' ? 'active' : ''}`} onClick={() => setPage('unmatched')}>
        <span className="nav-icon">?</span> 미매칭 후보
      </button>
      <button className={`nav-item nav-button ${page === 'requests' ? 'active' : ''}`} onClick={() => setPage('requests')}>
        <span className="nav-icon">✉</span> 키워드 문의
      </button>
      {role === 'admin' && <button className={`nav-item nav-button ${page === 'users' ? 'active' : ''}`} onClick={() => setPage('users')}>
        <span className="nav-icon">♙</span> 사용자 관리
      </button>}
      {role === 'admin' && <button className={`nav-item nav-button ${page === 'keyword-admin' ? 'active' : ''}`} onClick={() => setPage('keyword-admin')}>
        <span className="nav-icon">✎</span> 키워드 관리
      </button>}
      <div className="sidebar-bottom">
        <div className="version-chip">REACT PREVIEW</div>
        <p>분석 기능을 먼저 옮기는 전환용 화면입니다.</p>
      </div>
    </aside>

    <main className="main-content">
      <header className="topbar">
        <div className="breadcrumb">WORKSPACE <span>/</span> {page === 'analysis' ? '텍스트 분석' : page === 'keywords' ? '키워드 원장' : page === 'report' ? '분석 리포트' : page === 'regulation' ? '법령 근거 검색' : page === 'unmatched' ? '미매칭 후보' : page === 'requests' ? '키워드 문의' : page === 'users' ? '사용자 관리' : '키워드 관리'}</div>
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
        : authMode === 'password-updated' ? <section className="state-card">
          <h1>비밀번호를 변경했습니다</h1>
          <p>새 비밀번호로 계정을 계속 사용할 수 있습니다.</p>
          <button className="primary-button" onClick={() => setAuthMode('login')}>계속하기</button>
        </section> : authMode === 'new-password' && session ? <section className="login-card">
          <div className="eyebrow">RESET PASSWORD</div>
          <h1>새 비밀번호 설정</h1>
          <p>계정에 사용할 새 비밀번호를 입력해 주세요.</p>
          <form onSubmit={changePassword}>
            <label htmlFor="new-password">새 비밀번호</label>
            <input id="new-password" type="password" autoComplete="new-password" required
              value={newPassword} disabled={busy} onChange={event => setNewPassword(event.target.value)} />
            <label htmlFor="confirm-password">새 비밀번호 확인</label>
            <input id="confirm-password" type="password" autoComplete="new-password" required
              value={confirmPassword} disabled={busy} onChange={event => setConfirmPassword(event.target.value)} />
            <button className="primary-button" disabled={busy} type="submit">{busy ? '변경 중…' : '비밀번호 변경'}</button>
          </form>
          {message && <p className="error-message" role="alert">{message}</p>}
        </section> : !session && authMode === 'request-reset' ? <section className="login-card">
          <div className="eyebrow">PASSWORD RECOVERY</div>
          <h1>재설정 링크 받기</h1>
          {resetEmailSent ? <>
            <p>계정이 존재하면 비밀번호 재설정 링크가 포함된 이메일을 보냈습니다.</p>
            <button className="secondary-button" onClick={() => { setAuthMode('login'); setResetEmailSent(false); setMessage('') }}>로그인으로 돌아가기</button>
          </> : <>
            <p>가입한 이메일을 입력하면 재설정 링크를 보내드립니다.</p>
            <form onSubmit={requestPasswordReset}>
              <label htmlFor="reset-email">이메일</label>
              <input id="reset-email" type="email" autoComplete="username" required
                value={email} disabled={busy} onChange={event => setEmail(event.target.value)} />
              <button className="primary-button" disabled={busy} type="submit">{busy ? '메일 보내는 중…' : '재설정 링크 보내기'}</button>
            </form>
            {message && <p className="error-message" role="alert">{message}</p>}
          </>}
        </section> : !session ? <section className="login-card">
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
          <button className="text-button recovery-link" onClick={() => {
            setAuthMode('request-reset')
            setResetEmailSent(false)
            setMessage('')
          }}>비밀번호를 잊으셨나요?</button>
        </section> : !allowed ? <section className="state-card">
          <h1>사용 권한을 확인해 주세요</h1>
          <p>관리자가 계정에 사용자 또는 관리자 권한을 부여해야 합니다.</p>
          <button className="secondary-button" onClick={signOut}>로그아웃</button>
        </section> : page === 'keyword-admin' && role === 'admin' ? <>
          <div className="page-heading">
            <div><div className="eyebrow">ADMIN / 08</div><h1>키워드 관리</h1>
              <p>기존 키워드의 카테고리, 리스크, 대체 표현, 심의 기준과 증빙 유형을 수정합니다.</p></div>
            <div className="preview-pill"><span /> 관리자 전용</div>
          </div>
          <section className="catalog-section">
            <div className="panel admin-users-panel admin-keywords-panel">
              <div className="admin-keyword-toolbar">
                <label className="sr-only" htmlFor="admin-keyword-search">키워드 원장 검색</label>
                <input id="admin-keyword-search" value={adminKeywordSearch} maxLength={200}
                  placeholder="번호·키워드명·대체 키워드 검색"
                  onChange={event => { setAdminKeywordSearch(event.target.value); setAdminKeywordPageNumber(1) }} />
                <span>{adminKeywordBusy ? '원장을 불러오는 중…' : `${adminKeywordMatches.length.toLocaleString()} / ${adminKeywordRows.length.toLocaleString()}개`}</span>
                <button className="secondary-button" disabled={adminKeywordBusy || adminKeywordSaving}
                  onClick={() => {
                    if (adminKeywordDirty && !window.confirm('저장하지 않은 변경사항을 버리고 최신 원장을 불러올까요?')) return
                    setAdminKeywordDirty(false)
                    setAdminKeywordRefresh(value => value + 1)
                  }}>원장 다시 불러오기</button>
                <button className="secondary-button" disabled={adminKeywordBusy || adminKeywordSaving}
                  onClick={() => { setNewKeywordOpen(value => !value); setAdminKeywordError('') }}>새 키워드 추가</button>
                <button className="primary-button" disabled={!adminKeywordDirty || adminKeywordBusy || adminKeywordSaving || adminKeywordRevision === null}
                  onClick={saveAdminKeywordChanges}>{adminKeywordSaving ? '저장 중…' : '변경사항 저장'}</button>
              </div>
              <p className="unmatched-note">번호·키워드명·조회 횟수·마지막 출력일은 읽기 전용입니다. 행 삭제는 기존 Streamlit 관리자 화면에서 할 수 있습니다.</p>
              {newKeywordOpen && <form className="new-keyword-form" onSubmit={addAdminKeyword}>
                <h2>새 키워드 행</h2>
                <div className="new-keyword-fields">
                  <label>키워드명<input required maxLength={500} value={newKeywordForm.term}
                    onChange={event => setNewKeywordForm({ ...newKeywordForm, term: event.target.value })} /></label>
                  <label>카테고리<select required value={newKeywordForm.category}
                    onChange={event => setNewKeywordForm({ ...newKeywordForm, category: event.target.value })}>
                    <option value="">선택</option>{filters.categories.map(value => <option key={value}>{value}</option>)}
                  </select></label>
                  <label>리스크<select required value={newKeywordForm.risk}
                    onChange={event => setNewKeywordForm({ ...newKeywordForm, risk: event.target.value })}>
                    <option value="">선택</option>{filters.risks.map(value => <option key={value}>{value}</option>)}
                  </select></label>
                  <label>증빙 유형<select required value={newKeywordForm.evidenceType}
                    onChange={event => setNewKeywordForm({ ...newKeywordForm, evidenceType: event.target.value })}>
                    <option value="">선택</option>{(filters.evidence_types ?? []).map(value => <option key={value}>{value}</option>)}
                  </select></label>
                  <label>대체 키워드<input maxLength={2000} value={newKeywordForm.alternative}
                    onChange={event => setNewKeywordForm({ ...newKeywordForm, alternative: event.target.value })} /></label>
                  <label className="criteria-field">심의 기준<textarea required maxLength={5000} value={newKeywordForm.criteria}
                    onChange={event => setNewKeywordForm({ ...newKeywordForm, criteria: event.target.value })} /></label>
                </div>
                <button className="primary-button" type="submit">행 추가</button>
              </form>}
              {adminKeywordDirty && <p className="admin-dirty-note">저장하지 않은 변경사항이 있습니다.</p>}
              {adminKeywordMessage && <p className="success-message" role="status">{adminKeywordMessage}</p>}
              {adminKeywordError && <p className="error-message" role="alert">{adminKeywordError}</p>}
              {!adminKeywordError && <div className="table-scroll admin-keyword-table"><table>
                <thead><tr><th>번호</th><th>키워드명</th><th>카테고리</th><th>리스크</th><th>대체 키워드</th><th>심의 기준</th><th>증빙 유형</th></tr></thead>
                <tbody>{adminKeywordPageRows.map(row => <tr key={row.kwd_no}>
                  <td>{row.kwd_no}</td><td><strong>{row.키워드명}</strong></td>
                  <td><input aria-label={`${row.kwd_no} 카테고리`} value={row.상품카테고리}
                    disabled={adminKeywordSaving || adminKeywordBusy} onChange={event => updateAdminKeyword(row.kwd_no, '상품카테고리', event.target.value)} /></td>
                  <td><input aria-label={`${row.kwd_no} 리스크`} value={row['리스크 등급']}
                    disabled={adminKeywordSaving || adminKeywordBusy} onChange={event => updateAdminKeyword(row.kwd_no, '리스크 등급', event.target.value)} /></td>
                  <td><input aria-label={`${row.kwd_no} 대체 키워드`} value={row.대체키워드}
                    disabled={adminKeywordSaving || adminKeywordBusy} onChange={event => updateAdminKeyword(row.kwd_no, '대체키워드', event.target.value)} /></td>
                  <td><textarea aria-label={`${row.kwd_no} 심의 기준`} value={row['리스크 등급별 세부 심의기준']}
                    disabled={adminKeywordSaving || adminKeywordBusy} onChange={event => updateAdminKeyword(row.kwd_no, '리스크 등급별 세부 심의기준', event.target.value)} /></td>
                  <td><input aria-label={`${row.kwd_no} 증빙 유형`} value={row.증빙자료유형}
                    disabled={adminKeywordSaving || adminKeywordBusy} onChange={event => updateAdminKeyword(row.kwd_no, '증빙자료유형', event.target.value)} /></td>
                </tr>)}</tbody>
              </table></div>}
              {!adminKeywordBusy && !adminKeywordError && adminKeywordPageRows.length === 0 && <p className="empty-result">검색 결과가 없습니다.</p>}
              <div className="catalog-pagination">
                <button className="secondary-button" disabled={adminKeywordBusy || adminKeywordPageNumber <= 1}
                  onClick={() => setAdminKeywordPageNumber(value => Math.max(1, value - 1))}>이전</button>
                <span>페이지 {adminKeywordPageNumber} / {adminKeywordPageCount}</span>
                <button className="secondary-button" disabled={adminKeywordBusy || adminKeywordPageNumber >= adminKeywordPageCount}
                  onClick={() => setAdminKeywordPageNumber(value => value + 1)}>다음</button>
              </div>
            </div>
          </section>
        </> : page === 'keyword-admin' ? <section className="state-card">
          <h1>관리자 권한이 필요합니다</h1><p>키워드 원장은 관리자 계정만 수정할 수 있습니다.</p>
        </section> : page === 'users' && role === 'admin' ? <>
          <div className="page-heading">
            <div><div className="eyebrow">ADMIN / 07</div><h1>사용자 관리</h1>
              <p>계정 역할을 조회하고 member/admin 권한을 변경합니다.</p></div>
            <div className="preview-pill"><span /> 관리자 전용</div>
          </div>
          <section className="catalog-section">
            <div className="panel admin-users-panel">
              <div className="request-history-heading"><h2>계정 목록</h2>
                <span>{adminUsersBusy ? '불러오는 중…' : `페이지 ${adminUserPage}`}</span></div>
              {adminUserMessage && <p className="success-message" role="status">{adminUserMessage}</p>}
              {adminUsersError && <p className="error-message" role="alert">{adminUsersError}</p>}
              {!adminUsersError && <div className="table-scroll"><table>
                <thead><tr><th>이메일</th><th>계정 ID</th><th>이메일 확인</th><th>현재 역할</th><th>역할 변경</th><th /></tr></thead>
                <tbody>{adminUsers.map(item => {
                  const draft = adminUserRoleDrafts[item.id] ?? item.role ?? ''
                  const unchanged = draft === (item.role ?? '')
                  const selfDemotion = item.id === user?.id && draft === 'member'
                  return <tr key={item.id}>
                    <td><strong>{item.email || '—'}</strong></td><td className="admin-user-id">{item.id}</td>
                    <td>{item.email_confirmed ? '확인됨' : '미확인'}</td><td>{item.role ?? '미지정'}</td>
                    <td><select aria-label={`${item.email} 역할`} value={draft} disabled={adminUsersBusy || adminUserSavingId === item.id}
                      onChange={event => setAdminUserRoleDrafts(previous => ({ ...previous,
                        [item.id]: event.target.value as 'admin' | 'member' | '' }))}>
                      <option value="">미지정</option><option value="member">member</option><option value="admin">admin</option>
                    </select></td>
                    <td><button className="secondary-button" disabled={unchanged || !draft || selfDemotion || adminUserSavingId === item.id}
                      onClick={() => saveAdminUserRole(item)}>
                      {adminUserSavingId === item.id ? '저장 중…' : '저장'}
                    </button></td>
                  </tr>
                })}</tbody>
              </table></div>}
              <div className="catalog-pagination">
                <button className="secondary-button" disabled={adminUsersBusy || adminUserPage <= 1}
                  onClick={() => setAdminUserPage(value => Math.max(1, value - 1))}>이전</button>
                <span>페이지 {adminUserPage}</span>
                <button className="secondary-button" disabled={adminUsersBusy || !adminUsersHasMore}
                  onClick={() => setAdminUserPage(value => value + 1)}>다음</button>
              </div>
            </div>
          </section>
        </> : page === 'users' ? <section className="state-card">
          <h1>관리자 권한이 필요합니다</h1><p>사용자 관리는 관리자 계정만 이용할 수 있습니다.</p>
        </section> : page === 'requests' ? <>
          <div className="page-heading">
            <div><div className="eyebrow">REQUESTS / 06</div><h1>키워드 문의</h1>
              <p>기존 키워드의 리스크 등급이나 심의 기준 변경을 요청합니다.</p></div>
            <div className="preview-pill"><span /> 계정 문의</div>
          </div>
          <section className="catalog-section request-section">
            <div className="panel request-panel">
              <h2>문의할 키워드 찾기</h2>
              <form className="catalog-search" onSubmit={searchRequestKeywords}>
                <label className="sr-only" htmlFor="request-keyword-search">키워드 번호 또는 이름</label>
                <input id="request-keyword-search" maxLength={200} value={requestSearch}
                  placeholder="키워드 번호 또는 이름 검색" onChange={event => setRequestSearch(event.target.value)} />
                <button className="primary-button" disabled={requestSearchBusy || !requestSearch.trim()} type="submit">
                  {requestSearchBusy ? '검색 중…' : '검색'}
                </button>
              </form>
              {requestMatches.length > 0 && <div className="request-match-list" aria-label="검색된 키워드">
                {requestMatches.map(row => <button key={row.kwd_no}
                  className={`request-match ${selectedRequestKeyword?.kwd_no === row.kwd_no ? 'selected' : ''}`}
                  onClick={() => setSelectedRequestKeyword(row)}>
                  <strong>{row.kwd_no} · {row.키워드명}</strong><span>{row.상품카테고리} · {row['리스크 등급']}</span>
                </button>)}
              </div>}
              {selectedRequestKeyword && <form className="request-compose" onSubmit={submitKeywordInquiry}>
                <p>선택: <strong>{selectedRequestKeyword.kwd_no} · {selectedRequestKeyword.키워드명}</strong></p>
                <label>문의 유형
                  <select value={requestType} disabled={requestBusy}
                    onChange={event => setRequestType(event.target.value as typeof requestType)}>
                    <option value="risk_grade_adjustment">리스크 등급 조정 요청</option>
                    <option value="review_criteria_change">심의 기준 변경 요청</option>
                  </select>
                </label>
                <label>요청 내용
                  <textarea required minLength={1} maxLength={4000} value={requestDetail} disabled={requestBusy}
                    placeholder="변경이 필요한 이유와 제안 내용을 입력해 주세요."
                    onChange={event => setRequestDetail(event.target.value)} />
                </label>
                <button className="primary-button" disabled={requestBusy || !requestDetail.trim()} type="submit">
                  {requestBusy ? '접수 중…' : '문의 접수'}
                </button>
              </form>}
              {requestMessage && <p className="success-message" role="status">{requestMessage}</p>}
              {requestError && <p className="error-message" role="alert">{requestError}</p>}
            </div>
            <div className="panel request-history">
              <div className="request-history-heading"><h2>문의 내역</h2><span>{requestBusy ? '불러오는 중…' : `${requestRecords.length}건`}</span></div>
              {requestRecords.length ? <div className="request-record-list">{requestRecords.map(item => <details className="request-record" key={item.id}>
                <summary><strong>{item.keyword_name} · {item.kwd_no}</strong>
                  <span>{keywordRequestTypeLabels[item.request_type] ?? item.request_type} · {keywordRequestStatusLabels[item.status] ?? item.status}</span>
                </summary>
                {role === 'admin' && item.requester_email && <small>요청자: {item.requester_email}</small>}
                <p>{item.request_detail}</p>
                {item.admin_reply && <p className="admin-reply"><strong>관리자 답변</strong><br />{item.admin_reply}</p>}
                <small>{new Date(item.created_at).toLocaleString('ko-KR')}</small>
                {role === 'admin' && <div className="request-admin-controls">
                  <label>처리 상태
                    <select value={requestDrafts[item.id]?.status ?? item.status} disabled={requestSavingId === item.id}
                      onChange={event => setRequestDrafts(previous => ({ ...previous, [item.id]: {
                        status: event.target.value, reply: previous[item.id]?.reply ?? item.admin_reply ?? '',
                      } }))}>
                      <option value="대기">대기</option><option value="검토중">검토 중</option><option value="처리완료">처리 완료</option>
                    </select>
                  </label>
                  <label>관리자 답변
                    <textarea maxLength={4000} value={requestDrafts[item.id]?.reply ?? item.admin_reply ?? ''}
                      disabled={requestSavingId === item.id}
                      onChange={event => setRequestDrafts(previous => ({ ...previous, [item.id]: {
                        status: previous[item.id]?.status ?? item.status, reply: event.target.value,
                      } }))} />
                  </label>
                  <button className="secondary-button" disabled={requestSavingId === item.id}
                    onClick={() => saveKeywordRequest(item.id)}>
                    {requestSavingId === item.id ? '저장 중…' : '답변 저장'}
                  </button>
                </div>}
              </details>)}</div> : !requestBusy && <p className="empty-result">아직 문의 내역이 없습니다.</p>}
            </div>
          </section>
        </> : page === 'unmatched' ? <>
          <div className="page-heading">
            <div><div className="eyebrow">REVIEW / 05</div><h1>미매칭 후보</h1>
              <p>분석 중 등록 키워드와 일치하지 않은 표현의 누적 현황입니다.</p></div>
            <div className="preview-pill"><span /> 공유 후보</div>
          </div>
          <section className="catalog-section">
            <div className="panel catalog-panel">
              <form className="unmatched-controls" onSubmit={event => {
                event.preventDefault()
                setUnmatchedOffset(0)
                setUnmatchedSearch(unmatchedSearchInput.trim())
              }}>
                <label className="sr-only" htmlFor="unmatched-search">미매칭 표현 검색</label>
                <input id="unmatched-search" value={unmatchedSearchInput} maxLength={200}
                  placeholder="미매칭 표현 검색" onChange={event => setUnmatchedSearchInput(event.target.value)} />
                <label className="sr-only" htmlFor="unmatched-sort">정렬 기준</label>
                <select id="unmatched-sort" value={unmatchedSort}
                  onChange={event => { setUnmatchedOffset(0); setUnmatchedSort(event.target.value as 'occurrences' | 'registered') }}>
                  <option value="occurrences">출현 횟수순</option><option value="registered">최근 등록순</option>
                </select>
                <button className="primary-button" type="submit" disabled={unmatchedBusy}>검색</button>
              </form>
              <div className="catalog-meta">
                <span>{unmatchedBusy ? '목록을 불러오는 중…' : `${unmatchedPage?.total ?? 0}개 표현`}</span>
                <button className="secondary-button" disabled={unmatchedBusy || unmatchedExportBusy || !unmatchedPage?.total}
                  onClick={exportUnmatchedCsv}>{unmatchedExportBusy ? 'CSV 준비 중…' : '전체 누적 CSV'}</button>
              </div>
              <p className="unmatched-note">후보 목록에는 표현과 집계 횟수만 표시됩니다. 계정이나 원문 문서는 포함하지 않습니다.</p>
              {unmatchedError && <p className="error-message" role="alert">{unmatchedError}</p>}
              {!unmatchedError && (unmatchedPage?.rows.length ? <div className="table-scroll"><table>
                <thead><tr><th><input type="checkbox" aria-label="현재 페이지의 요청 가능 후보 선택"
                  checked={Boolean(unmatchedPage?.rows.some(row => row.review_status === 'pending')) &&
                    (unmatchedPage?.rows.filter(row => row.review_status === 'pending').every(row => selectedUnmatched[row.term_norm]) ?? false)}
                  onChange={event => toggleUnmatchedPage(event.target.checked)} /></th>
                  <th>미매칭 표현</th><th>누적 횟수</th><th>분석 횟수</th><th>상태</th><th>최초 수집</th><th>최근 수집</th></tr></thead>
                <tbody>{unmatchedPage.rows.map(row => <tr key={row.term_norm}>
                  <td><input type="checkbox" aria-label={`${row.display_term} 선택`}
                    checked={Boolean(selectedUnmatched[row.term_norm])} disabled={row.review_status !== 'pending'}
                    onChange={event => toggleUnmatchedRow(row, event.target.checked)} /></td>
                  <td><strong>{row.display_term}</strong></td><td>{row.total_occurrences.toLocaleString()}</td>
                  <td>{row.analysis_count.toLocaleString()}</td><td>{unmatchedStatusLabels[row.review_status] ?? row.review_status}</td>
                  <td>{new Date(row.first_seen).toLocaleDateString('ko-KR')}</td><td>{new Date(row.last_seen).toLocaleDateString('ko-KR')}</td>
                </tr>)}</tbody>
              </table></div> : !unmatchedBusy && <p className="empty-result">표시할 미매칭 후보가 없습니다.</p>)}
              {selectedUnmatchedCount > 0 && <div className="unmatched-actions">
                <span>{selectedUnmatchedCount}개 후보 선택됨 · 요청 후 관리자 검토 대기열로 이동합니다.
                  {selectedUnmatchedCount > 1000 && ' 한 번에 최대 1,000개까지 요청할 수 있습니다.'}</span>
                <button className="primary-button" disabled={unmatchedSubmitBusy || unmatchedBusy || selectedUnmatchedCount > 1000}
                  onClick={submitUnmatchedRequests}>{unmatchedSubmitBusy ? '요청 접수 중…' : '선택 후보 등록 요청'}</button>
              </div>}
              {unmatchedActionMessage && <p className="success-message" role="status">{unmatchedActionMessage}</p>}
              {unmatchedPage && <div className="catalog-pagination">
                <button className="secondary-button" disabled={unmatchedBusy || unmatchedOffset === 0}
                  onClick={() => setUnmatchedOffset(Math.max(0, unmatchedOffset - 100))}>이전</button>
                <span>{unmatchedPage.total ? `${unmatchedOffset + 1}–${Math.min(unmatchedOffset + 100, unmatchedPage.total)} / ${unmatchedPage.total}` : '0개'}</span>
                <button className="secondary-button" disabled={unmatchedBusy || unmatchedOffset + 100 >= unmatchedPage.total}
                  onClick={() => setUnmatchedOffset(unmatchedOffset + 100)}>다음</button>
              </div>}
            </div>
          </section>
        </> : page === 'regulation' ? <>
          <div className="page-heading">
            <div><div className="eyebrow">EVIDENCE / 04</div><h1>법령 근거 검색</h1>
              <p>공식 법령·행정규칙·판례 검색 결과와 현재 키워드 DB 후보를 함께 확인합니다.</p></div>
            <div className="preview-pill"><span /> 근거 조회</div>
          </div>
          <section className="catalog-section">
            <form className="panel regulation-form" onSubmit={submitRegulation}>
              <label>검색 방향
                <select value={regulationDirection} disabled={regulationBusy}
                  onChange={event => setRegulationDirection(event.target.value as RegulationQuestion['direction'])}>
                  <option value="keyword_to_law">광고 문구에서 관련 법령 찾기</option>
                  <option value="law_to_keywords">법령 조문에서 등록 키워드 찾기</option>
                </select>
              </label>
              <label>{regulationDirection === 'keyword_to_law' ? '질문 또는 검색어' : '법령명과 조항'}
                <input required minLength={2} maxLength={500} value={regulationQuery} disabled={regulationBusy}
                  placeholder={regulationDirection === 'keyword_to_law' ? '예: 미백 기능성 화장품 광고 표현' : '예: 화장품법 제13조'}
                  onChange={event => setRegulationQuery(event.target.value)} />
              </label>
              {regulationDirection === 'keyword_to_law' && <label>검토할 광고 문구 (선택)
                <textarea maxLength={20000} value={regulationContext} disabled={regulationBusy}
                  placeholder="광고 문구나 제품 설명을 입력하면 현재 키워드 DB 후보 검색에 함께 사용합니다."
                  onChange={event => setRegulationContext(event.target.value)} />
              </label>}
              <label>상품 카테고리 (선택)
                <select value={regulationCategory} disabled={regulationBusy}
                  onChange={event => setRegulationCategory(event.target.value)}>
                  <option value="">전체 카테고리</option>{filters.categories.map(value => <option key={value}>{value}</option>)}
                </select>
              </label>
              <button className="primary-button" type="submit" disabled={regulationBusy || !regulationQuery.trim()}>
                {regulationBusy ? '공식 자료 검색 중…' : '근거 검색하기'}
              </button>
              <p className="regulation-caution">검색 결과와 키워드 DB 등급은 참고 자료이며, 법률 판단이나 위반 여부를 확정하지 않습니다.</p>
            </form>
            {regulationError && <p className="error-message regulation-error" role="alert">{regulationError}</p>}
            {regulationResult && <section className="regulation-results" aria-live="polite">
              <div className="panel regulation-answer">
                <div className={`status-pill status-${regulationResult.status}`}>
                  {regulationStatusLabels[regulationResult.status] ?? regulationResult.status}
                </div>
                <p>{regulationResult.answer}</p>
                {regulationResult.administrator_review && <p className="review-note">자료 간 차이가 있거나 설명을 확정하지 못했습니다. 담당자가 원문을 검토해 주세요.</p>}
                {regulationResult.llm_used && <small>검색 자료를 바탕으로 설명을 생성했습니다. 인용된 원문과 출처를 직접 확인하세요.</small>}
              </div>
              {regulationResult.keyword_matches.length > 0 && <div className="panel table-panel">
                <h2 className="regulation-section-title">현재 키워드 DB 일치 항목</h2><div className="table-scroll"><table>
                  <thead><tr><th>번호</th><th>키워드명</th><th>카테고리</th><th>리스크</th><th>심의 기준</th></tr></thead>
                  <tbody>{regulationResult.keyword_matches.map((item, index) => <tr key={`${item.kwd_no}-${index}`}>
                    <td>{item.kwd_no}</td><td><strong>{item.키워드명}</strong></td><td>{item.상품카테고리 || '—'}</td>
                    <td>{item['리스크 등급'] || '—'}</td><td>{item['리스크 등급별 세부 심의기준'] || '—'}</td>
                  </tr>)}</tbody>
                </table></div>
              </div>}
              <div className="regulation-sources"><h2 className="regulation-section-title">검색 출처 ({regulationResult.sources.length})</h2>
                {regulationResult.sources.map(source => <details className="panel source-card" key={source.id}>
                  <summary><strong>{source.label}</strong><span>{source.id}</span></summary>
                  {source.url && <a href={source.url} target="_blank" rel="noreferrer">공식 원문 열기 ↗</a>}
                  <pre>{source.text}</pre>
                </details>)}
              </div>
            </section>}
          </section>
        </> : page === 'report' ? <>
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
                <button className="secondary-button" disabled={keywordBusy || keywordExportBusy}
                  onClick={exportKeywordCatalog}>{keywordExportBusy ? 'CSV 준비 중…' : '전체 원장 CSV'}</button>
              </div>
              {keywordError && <p className="error-message" role="alert">{keywordError}</p>}
              {!keywordError && <div className="table-scroll"><table>
                <thead><tr><th>번호</th><th>키워드명</th><th>카테고리</th><th>리스크</th><th>대체 키워드</th><th>심의 기준</th><th>증빙 자료</th></tr></thead>
                <tbody>{keywordPage?.items.map(row => <tr key={row.kwd_no}>
                  <td>{row.kwd_no}</td><td><strong>{row.키워드명}</strong></td><td>{row.상품카테고리 || '—'}</td>
                  <td>{row['리스크 등급'] || '—'}</td><td>{row.대체키워드 || '—'}</td>
                  <td>{row['리스크 등급별 세부 심의기준'] || '—'}</td><td>{row.증빙자료유형 || '—'}</td>
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
