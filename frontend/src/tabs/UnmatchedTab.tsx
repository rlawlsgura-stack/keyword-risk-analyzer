import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  deleteRegistrationRequests, deleteUnmatchedTerms, exportUnmatchedTerms, loadRecommendationDraft, loadRegistrationQueue,
  loadUnmatchedTerms, normalizeUnmatched, registerUnmatchedRows, rejectRegistrationRequests, saveRecommendationDraft, suggestKeyword,
  submitRegistrationRequests,
} from '../lib/api.ts'
import { CRITERIA_COL, formatDatetime, koSorted } from '../lib/catalog.ts'
import { downloadCsv } from '../lib/csv.ts'
import { SearchSelect } from '../components/SearchSelect.tsx'
import type { KeywordSuggestion, UnmatchedTerm, UnmatchedRegistrationRequest } from '../lib/types.ts'
import { blankRow, emptyDraft, orderRows, sourceKeys, toWsRow, type Draft, type WsRow } from '../lib/workspace.ts'
import { useStore } from '../store.tsx'
import { Alert, Button, Checkbox, Help, Spinner, TextInput, errorText } from '../components/ui.tsx'

const PAGE = 1000
const DIRECT = '(직접 입력)'
const STATUS_LABEL: Record<string, string> = { registration_requested: '신규 키워드 등록 요청', ignored: '관리자 거절' }
const EXPORT_STATUS: Record<string, string> = { registration_requested: '신규키워드 등록요청', ignored: '관리자 거절' }

type Selection = { all: boolean; ids: Record<string, boolean> }
type Msg = { kind: 'success' | 'info' | 'warning' | 'error'; text: string; caption?: string }

export function UnmatchedTab() {
  const { user, isAdmin, catalog, dropdowns, reloadCatalog } = useStore()

  /* ---------- candidate list ---------- */
  const [searchInput, setSearchInput] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(0)
  const [total, setTotal] = useState(0)
  const [rows, setRows] = useState<UnmatchedTerm[]>([])
  const [listError, setListError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)
  const [selections, setSelections] = useState<Record<string, Selection>>({})
  const [surfaceEdits, setSurfaceEdits] = useState<Record<string, string>>({})
  const [editText, setEditText] = useState('')
  const [csvRows, setCsvRows] = useState<Record<string, unknown>[] | null>(null)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [listMsg, setListMsg] = useState<Msg | null>(null)
  const [busy, setBusy] = useState(false)
  const [recommendProgress, setRecommendProgress] = useState<{ done: number; total: number; failed: string[] } | null>(null)
  const [failedRecommendationIds, setFailedRecommendationIds] = useState<string[]>([])
  const [directCells, setDirectCells] = useState<Set<string>>(() => new Set())

  const selection = selections[search] ?? { all: false, ids: {} }
  const setSelection = (next: Selection) => setSelections(s => ({ ...s, [search]: next }))
  const isSelected = (key: string) => (selection.all ? selection.ids[key] !== false : selection.ids[key] === true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    loadUnmatchedTerms(page * PAGE, PAGE, search, 'registered')
      .then(result => {
        if (cancelled) return
        if (!result.rows.length && page > 0) { setPage(0); return }
        setRows(result.rows); setTotal(result.total); setListError(null)
      })
      .catch(error => { if (!cancelled) setListError(errorText(error)) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [search, page, refreshKey])

  const surface = (r: UnmatchedTerm) => surfaceEdits[r.term_norm] ?? r.display_term
  const pageCount = Math.max(1, Math.ceil(total / PAGE))
  const selectedOnPage = rows.filter(r => isSelected(r.term_norm))
  const singleSelected = !selection.all && Object.entries(selection.ids).filter(([, v]) => v).length === 1 && selectedOnPage.length === 1
    ? selectedOnPage[0] : null
  useEffect(() => { setEditText(singleSelected ? surface(singleSelected) : '') }, [singleSelected?.term_norm]) // eslint-disable-line react-hooks/exhaustive-deps

  /** _load_unmatched_selection_rows (L3148): resolves "all" across every page of the search. */
  const resolveSelection = useCallback(async (): Promise<UnmatchedTerm[]> => {
    if (!selection.all) {
      const keys = Object.entries(selection.ids).filter(([, v]) => v).map(([k]) => k)
      const known = new Map(rows.map(r => [r.term_norm, r]))
      const missing = keys.filter(k => !known.has(k))
      if (missing.length) {
        let offset = 0
        while (missing.some(k => !known.has(k))) {
          const pageRows = await loadUnmatchedTerms(offset, PAGE, search, 'registered')
          pageRows.rows.forEach(r => known.set(r.term_norm, r))
          offset += PAGE
          if (!pageRows.rows.length || offset >= pageRows.total) break
        }
      }
      return keys.map(k => known.get(k)).filter((r): r is UnmatchedTerm => Boolean(r))
    }
    const out: UnmatchedTerm[] = []
    let offset = 0, expected = -1
    for (;;) {
      const pageRows = await loadUnmatchedTerms(offset, PAGE, search, 'registered')
      if (expected < 0) expected = pageRows.total
      else if (pageRows.total !== expected) throw new Error('후보 목록이 바뀌었습니다. 새로고침 후 다시 선택하세요.')
      out.push(...pageRows.rows.filter(r => selection.ids[r.term_norm] !== false))
      offset += PAGE
      if (!pageRows.rows.length || offset >= expected) break
    }
    return out
  }, [selection, rows, search])

  const resetReview = () => { setSelections({}); setSurfaceEdits({}) }

  const buildCsv = async () => {
    setListMsg(null)
    try {
      const { items } = await exportUnmatchedTerms()
      setCsvRows(items.map(r => ({
        '미매칭 표현': r.display_term, '누적 출현 횟수': r.total_occurrences, '분석 횟수': r.analysis_count,
        '상태': EXPORT_STATUS[r.review_status] ?? '', '최초 수집 시각': formatDatetime(r.first_seen), '최근 수집 시각': formatDatetime(r.last_seen),
      })))
    } catch { setListMsg({ kind: 'error', text: '전체 CSV를 만들지 못했습니다. 다시 시도하세요.' }) }
  }

  const removeSelected = async () => {
    setListMsg(null)
    let selected: UnmatchedTerm[]
    try { selected = await resolveSelection() } catch { setListMsg({ kind: 'error', text: '선택한 표현을 불러오지 못했습니다.' }); return }
    if (!selected.length) { setListMsg({ kind: 'warning', text: '삭제할 미매칭 표현을 선택하세요.' }); return }
    if (!confirmDelete) { setListMsg({ kind: 'warning', text: '삭제 확인란을 먼저 선택하세요.' }); return }
    setBusy(true)
    try {
      const keys = selected.map(r => r.term_norm)
      for (let i = 0; i < keys.length; i += 1000) await deleteUnmatchedTerms(keys.slice(i, i + 1000))
      resetReview(); setPage(0); setConfirmDelete(false); setRefreshKey(k => k + 1)
    } catch { setListMsg({ kind: 'error', text: '영구 삭제에 실패했습니다. 관리자 권한과 연결 상태를 확인하세요.' }) }
    finally { setBusy(false) }
  }

  /* ---------- recommendation workspace (draft-backed) ---------- */
  const [draft, setDraftState] = useState<Draft>(emptyDraft)
  const [draftReady, setDraftReady] = useState(false)
  const [draftError, setDraftError] = useState(false)
  const [queue, setQueue] = useState<UnmatchedRegistrationRequest[]>([])
  const [queueError, setQueueError] = useState('')
  const [wsMsg, setWsMsg] = useState<Msg | null>(null)
  const draftRef = useRef(draft)
  draftRef.current = draft
  const saveTimer = useRef(0)

  const persist = useCallback(async (next: Draft) => {
    window.clearTimeout(saveTimer.current)
    try { await saveRecommendationDraft(next as unknown as Record<string, unknown>); setDraftError(false) } catch { setDraftError(true) }
  }, [])
  /** Update the draft; immediate=true saves now (actions), otherwise after a short pause (cell edits). */
  const setDraft = useCallback((fn: (d: Draft) => Draft, immediate = false) => {
    setDraftState(prev => {
      const next = fn(prev)
      window.clearTimeout(saveTimer.current)
      if (immediate) void persist(next)
      else saveTimer.current = window.setTimeout(() => void persist(draftRef.current), 1500)
      return next
    })
  }, [persist])
  useEffect(() => () => { window.clearTimeout(saveTimer.current) }, [])

  useEffect(() => {
    loadRecommendationDraft()
      .then(({ payload }) => {
        if (payload && (payload as { version?: number }).version === 1) {
          const p = payload as unknown as Draft
          setDraftState({ ...emptyDraft(), ...p, ai_suggestions: p.ai_suggestions ?? {}, manual_rows: (p.manual_rows ?? []).map(r => toWsRow(r)) })
        }
      })
      .catch(() => setDraftError(true))
      .finally(() => setDraftReady(true))
  }, [user.id])

  const loadQueue = useCallback(async () => {
    if (!isAdmin) return
    try { setQueue((await loadRegistrationQueue()).items); setQueueError('') } catch (e) { setQueueError(errorText(e)) }
  }, [isAdmin])
  useEffect(() => { void loadQueue() }, [loadQueue])

  const baseRows = useMemo<WsRow[]>(() => {
    let recs = draft.recommendations.map(r => toWsRow(r))
    if (!recs.length) recs = [blankRow(`manual:new:${draft.recommendation_version}`)]
    const requests = queue.map(r => toWsRow({
      term: r.term, source_terms: r.source_terms ?? '', occurrences: r.occurrences ?? 0, request_id: r.id, term_norm: r.term_norm ?? '',
      request_date: formatDatetime(r.created_at), 상품카테고리: r.category ?? '', '리스크 등급': r.risk ?? '',
      '리스크 등급별 세부 심의기준': r.criteria ?? '', 증빙자료유형: r.evidence_type ?? '', 대체키워드: r.alternative ?? '-',
    }))
    return [...requests, ...recs]
  }, [draft.recommendations, draft.recommendation_version, queue])

  const wsRows = useMemo(() => {
    const hidden = new Set(draft.hidden_ids)
    return orderRows(baseRows, draft.manual_rows, draft.manual_placements)
      .filter(r => !hidden.has(r.recommendation_id))
      .map(r => ({ ...r, ...(draft.edits[r.recommendation_id] ?? {}) }) as WsRow)
  }, [baseRows, draft])

  const selectedIds = new Set(draft.selected_ids)
  const selectedRows = wsRows.filter(r => selectedIds.has(r.recommendation_id))
  const allWsSelected = wsRows.length > 0 && wsRows.every(r => selectedIds.has(r.recommendation_id))

  const options = useMemo(() => {
    const merged = (configured: string[], column: string) => {
      const values = new Set([
        ...configured,
        ...(catalog?.rows ?? []).map(row => String(row[column] ?? '').trim()),
      ].map(value => String(value).trim()).filter(Boolean))
      return ['', ...koSorted(values)]
    }
    return {
      상품카테고리: merged(dropdowns?.opt_categories ?? [], '상품카테고리'),
      '리스크 등급': merged(dropdowns?.opt_risks ?? [], '리스크 등급'),
      [CRITERIA_COL]: merged(dropdowns?.opt_details ?? [], CRITERIA_COL),
      증빙자료유형: merged(dropdowns?.opt_evidences ?? [], '증빙자료유형'),
      대체키워드: merged(dropdowns?.opt_alt_terms ?? [], '대체키워드'),
    }
  }, [catalog, dropdowns])

  const editCell = (id: string, column: string, value: unknown) => {
    setDraft(d => {
      const ai_suggestions = { ...d.ai_suggestions }
      delete ai_suggestions[id]
      const manual = d.manual_rows.some(r => r.recommendation_id === id)
      if (manual) return { ...d, ai_suggestions, manual_rows: d.manual_rows.map(r => (r.recommendation_id === id ? { ...r, [column]: value } : r)) }
      return { ...d, ai_suggestions, edits: { ...d.edits, [id]: { ...(d.edits[id] ?? {}), [column]: value } } }
    })
  }
  const toggleRow = (id: string, on: boolean) => setDraft(d => ({
    ...d, selected_ids: on ? [...new Set([...d.selected_ids, id])] : d.selected_ids.filter(x => x !== id),
  }), true)

  const applySuggestedFields = (row: WsRow, suggestion: KeywordSuggestion) => {
    const values: Record<string, string> = {
      상품카테고리: suggestion.category, '리스크 등급': suggestion.risk,
      [CRITERIA_COL]: suggestion.criteria, 증빙자료유형: suggestion.evidence_type,
      대체키워드: suggestion.alternative,
    }
    const fillBlanks = (current: WsRow) => Object.fromEntries(
      Object.entries(values).filter(([column, value]) => value.trim() &&
        (!String(current[column] ?? '').trim() || String(current[column]).trim() === '-')),
    )
    setDraft(d => {
      const id = row.recommendation_id
      const ai_suggestions = { ...d.ai_suggestions, [id]: suggestion }
      if (d.manual_rows.some(item => item.recommendation_id === id))
        return { ...d, ai_suggestions, manual_rows: d.manual_rows.map(item => item.recommendation_id === id ? { ...item, ...fillBlanks(item) } : item) }
      const current = { ...row, ...(d.edits[id] ?? {}) } as WsRow
      return { ...d, ai_suggestions, edits: { ...d.edits, [id]: { ...(d.edits[id] ?? {}), ...fillBlanks(current) } } }
    }, true)
  }

  const applyCategoryOption = (row: WsRow, suggestion: KeywordSuggestion,
                                     option: KeywordSuggestion['category_options'][number]) => {
    const categorySuggestion: KeywordSuggestion = {
      ...suggestion, status: 'suggested', category: option.category, risk: option.risk,
      criteria: option.criteria, evidence_type: option.evidence_type, alternative: option.alternative,
      reason: option.reason ?? `기존 DB 사례 '${option.keyword}'에 기반한 추천 초안입니다. 상품과 광고 전체 맥락을 확인하세요.`,
      source_ids: option.source_ids ?? [option.source_id], sources: option.sources ?? suggestion.sources,
    }
    applySuggestedFields(row, categorySuggestion)
    setWsMsg({ kind: 'success', text: '선택한 카테고리의 추천 초안을 빈 셀에 적용했습니다. 근거를 확인한 뒤 승인하세요.' })
  }

  const recommendSelected = async (retryOnly = false) => {
    const currentDraft = draftRef.current
    const currentRows = orderRows(baseRows, currentDraft.manual_rows, currentDraft.manual_placements)
      .filter(row => !currentDraft.hidden_ids.includes(row.recommendation_id))
      .map(row => ({ ...row, ...(currentDraft.edits[row.recommendation_id] ?? {}) }) as WsRow)
    const checkedRows = currentRows.filter(row => currentDraft.selected_ids.includes(row.recommendation_id))
    const targets = (retryOnly ? currentRows.filter(row => failedRecommendationIds.includes(row.recommendation_id)) : checkedRows)
      .filter(row => row.term.trim())
    if (!targets.length) { setWsMsg({ kind: 'warning', text: 'AI 추천을 받을 키워드를 선택하세요.' }); return }
    if (!retryOnly && targets.length > 5) { setWsMsg({ kind: 'warning', text: '한 번에 최대 5개 키워드까지 추천할 수 있습니다.' }); return }
    setBusy(true); setWsMsg(null)
    setRecommendProgress({ done: 0, total: targets.length, failed: [] })
    setFailedRecommendationIds([])
    const failed: string[] = []
    let cursor = 0
    const worker = async () => {
      while (cursor < targets.length) {
        const row = targets[cursor++]
        try {
          const suggestion = await suggestKeyword(row.term.trim(), row.상품카테고리, row.source_terms)
          if (suggestion.status === 'suggested') applySuggestedFields(row, suggestion)
          else setDraft(d => ({ ...d, ai_suggestions: { ...d.ai_suggestions, [row.recommendation_id]: suggestion } }), true)
        } catch (e) {
          failed.push(row.recommendation_id)
          setDraft(d => ({ ...d, ai_suggestions: { ...d.ai_suggestions, [row.recommendation_id]: {
            status: 'insufficient', term: row.term, category: '', risk: '', criteria: '', evidence_type: '', alternative: '',
            reason: `AI 추천에 실패했습니다: ${errorText(e)}`, source_ids: [], sources: [], warnings: [], category_options: [],
          } } }), true)
        } finally {
          setRecommendProgress(p => p ? { ...p, done: p.done + 1, failed: [...failed] } : p)
        }
      }
    }
    await Promise.all(Array.from({ length: Math.min(2, targets.length) }, worker))
    setFailedRecommendationIds(failed)
    setWsMsg(failed.length
      ? { kind: 'warning', text: `${targets.length - failed.length}/${targets.length}개 추천 완료. 실패 키워드: ${failed.map(id => targets.find(row => row.recommendation_id === id)?.term).join(', ')}` }
      : { kind: 'success', text: `${targets.length}개 키워드 추천을 완료했습니다. 근거를 확인하고 승인하세요.` })
    setBusy(false)
  }

  const normalize = async () => {
    setWsMsg(null)
    let selected: UnmatchedTerm[]
    try { selected = await resolveSelection() } catch (e) { setWsMsg({ kind: 'error', text: `미매칭 후보를 불러오지 못했습니다: ${errorText(e)}` }); return }
    if (!selected.length) { setWsMsg({ kind: 'warning', text: '분석할 행을 표에서 선택하세요.' }); return }
    setBusy(true)
    try {
      const { items } = await normalizeUnmatched(selected.slice(0, 1000).map(r => ({ surface: surface(r), occurrences: r.total_occurrences })))
      setDraft(d => ({
        ...d, recommendations: items.map(r => ({ term: r.term, occurrences: r.occurrences, source_terms: r.source_terms })),
        edits: {}, selected_ids: [], hidden_ids: [], ai_suggestions: {}, recommendation_version: d.recommendation_version + 1,
      }), true)
      setWsMsg({ kind: 'success', text: `정규화 추천 ${items.length}건을 만들었습니다. 검토 후 승인하세요.` })
    } catch (e) { setWsMsg({ kind: 'error', text: `미매칭 후보군 분석에 실패했습니다: ${errorText(e)}` }) }
    finally { setBusy(false) }
  }

  const addRow = (anchor: string | null, position: 'before' | 'after') => {
    const id = `manual:${crypto.randomUUID()}`
    setDraft(d => ({
      ...d, manual_rows: [...d.manual_rows, blankRow(id)],
      manual_placements: { ...d.manual_placements, [id]: { anchor_id: anchor, position } },
      recommendation_version: d.recommendation_version + 1,
    }), true)
  }
  const insertAt = (position: 'before' | 'after') => {
    setWsMsg(null)
    if (selectedRows.length !== 1) { setWsMsg({ kind: 'warning', text: '삽입 위치로 사용할 행을 하나만 선택하세요.' }); return }
    addRow(selectedRows[0].recommendation_id, position)
  }

  const removeRows = async () => {
    setWsMsg(null)
    if (!selectedRows.length) { setWsMsg({ kind: 'warning', text: '삭제할 항목을 선택하세요.' }); return }
    const requestIds = selectedRows.map(r => r.request_id).filter(Boolean)
    if (requestIds.length && !isAdmin) { setWsMsg({ kind: 'error', text: '선택한 항목을 삭제하지 못했습니다: 관리자만 요청을 삭제할 수 있습니다.' }); return }
    try {
      if (requestIds.length) { await deleteRegistrationRequests(requestIds); await loadQueue() }
      const ids = selectedRows.filter(r => !r.request_id).map(r => r.recommendation_id)
      setDraft(d => ({
        ...d, hidden_ids: [...new Set([...d.hidden_ids, ...ids])],
        selected_ids: d.selected_ids.filter(x => !selectedRows.some(r => r.recommendation_id === x)),
        recommendation_version: d.recommendation_version + 1,
      }), true)
    } catch (e) { setWsMsg({ kind: 'error', text: `선택한 항목을 삭제하지 못했습니다: ${errorText(e)}` }) }
  }

  const removeManual = (ids: string[]) => (d: Draft): Draft => {
    const remove = new Set(ids)
    const placements = { ...d.manual_placements }
    ids.forEach(id => delete placements[id])
    return { ...d, manual_rows: d.manual_rows.filter(r => !remove.has(r.recommendation_id)), manual_placements: placements }
  }

  const approve = async () => {
    setWsMsg(null)
    if (!selectedRows.length) { setWsMsg({ kind: 'warning', text: '먼저 등록할 후보를 선택하세요.' }); return }
    const required = ['term', '상품카테고리', '리스크 등급', '리스크 등급별 세부 심의기준', '증빙자료유형'] as const
    if (selectedRows.some(r => required.some(k => !String(r[k] ?? '').trim()))) {
      setWsMsg({ kind: 'warning', text: '선택한 후보의 키워드명, 카테고리, 리스크 등급, 심의기준, 증빙자료유형을 모두 입력하세요.' }); return
    }
    setBusy(true)
    try {
      const result = await registerUnmatchedRows(selectedRows.map(r => ({
        term: String(r.term).trim(), source_terms: String(r.source_terms ?? ''), term_norm: String(r.term_norm ?? ''),
        request_id: r.request_id || null, category: String(r.상품카테고리).trim(), risk: String(r['리스크 등급']).trim(),
        criteria: String(r['리스크 등급별 세부 심의기준']).trim(), evidence_type: String(r.증빙자료유형).trim(),
        alternative: String(r.대체키워드 ?? '').trim() || '-',
      })))
      await reloadCatalog()
      await loadQueue()
      setRefreshKey(k => k + 1)
      if (result.cleanup_error) {
        setWsMsg({ kind: 'error', text: result.added.length ? `DB 저장은 완료했지만 미매칭 표현과 요청 정리에 실패했습니다: ${result.cleanup_error}`
          : `미매칭 표현과 요청 정리에 실패했습니다: ${result.cleanup_error}` })
        return
      }
      const ids = selectedRows.map(r => r.recommendation_id)
      if (result.added.length) {
        setDraft(d => ({ ...removeManual(ids)(d), recommendations: [], selected_ids: [], recommendation_version: d.recommendation_version + 1 }), true)
        setWsMsg({ kind: 'success', text: `승인된 키워드 ${result.added.length}건을 DB에 등록하고 요청 ${result.cleared_requests}건을 정리했습니다.` })
      } else if (result.cleared_requests || sourceKeys(selectedRows).length) {
        setDraft(d => ({ ...removeManual(ids)(d), selected_ids: d.selected_ids.filter(x => !ids.includes(x)) }), true)
        setWsMsg({ kind: 'success', text: `이미 등록된 후보의 미매칭 통계와 요청 ${result.cleared_requests}건을 정리했습니다.` })
      } else {
        setWsMsg({ kind: 'info', text: '선택 후보는 이미 같은 카테고리에 등록되어 있습니다.' })
      }
    } catch (e) { setWsMsg({ kind: 'error', text: errorText(e) }) }
    finally { setBusy(false) }
  }

  const reject = async () => {
    setWsMsg(null)
    const targets = selectedRows.filter(r => r.request_id)
    if (!targets.length) { setWsMsg({ kind: 'warning', text: '거절할 등록 요청을 선택하세요.' }); return }
    try {
      const { rejected } = await rejectRegistrationRequests(targets.map(r => r.request_id))
      const ids = targets.map(r => r.recommendation_id)
      setDraft(d => ({ ...d, hidden_ids: [...new Set([...d.hidden_ids, ...ids])], selected_ids: d.selected_ids.filter(x => !ids.includes(x)) }), true)
      await loadQueue(); setRefreshKey(k => k + 1)
      setWsMsg({ kind: 'success', text: `등록 요청 ${rejected}건을 거절했습니다.` })
    } catch (e) { setWsMsg({ kind: 'error', text: `등록 요청을 거절하지 못했습니다: ${errorText(e)}` }) }
  }

  const requestRegistration = async () => {
    setWsMsg(null)
    if (!selectedRows.length) { setWsMsg({ kind: 'warning', text: '정규화 후보를 선택하세요.' }); return }
    if (selectedRows.some(r => !String(r.term).trim() || !String(r.상품카테고리).trim() || !String(r['리스크 등급']).trim())) {
      setWsMsg({ kind: 'warning', text: '선택 후보의 키워드명, 카테고리, 리스크 등급을 입력하세요.' }); return
    }
    if (selectedRows.some(r => { const t = String(r.term).trim(); return t.length < 1 || t.length > 150 || String(r.source_terms ?? '').trim().length > 500 })) {
      setWsMsg({ kind: 'warning', text: '후보 키워드 또는 원본 표현 길이를 확인하세요.' }); return
    }
    setBusy(true)
    try {
      await submitRegistrationRequests(selectedRows.map(r => ({
        term: String(r.term).trim(), source_terms: String(r.source_terms ?? '').trim(), occurrences: Number(r.occurrences) || 0,
        category: String(r.상품카테고리).trim(), risk: String(r['리스크 등급']).trim(), criteria: String(r['리스크 등급별 세부 심의기준'] ?? '').trim(),
        evidence_type: String(r.증빙자료유형 ?? '').trim(), alternative: String(r.대체키워드 ?? '').trim() || '-',
      })))
      const ids = selectedRows.map(r => r.recommendation_id)
      setDraft(d => ({ ...d, hidden_ids: [...new Set([...d.hidden_ids, ...ids])], selected_ids: d.selected_ids.filter(x => !ids.includes(x)), recommendation_version: d.recommendation_version + 1 }), true)
      setRefreshKey(k => k + 1)
      setWsMsg({ kind: 'success', text: '관리자 정규화 추천 및 분류 입력란에 요청이 누적되었습니다.' })
    } catch (e) {
      const status = (e as { status?: number }).status
      setWsMsg(status === 422 ? { kind: 'error', text: '선택한 등록 후보 입력을 확인하세요.' }
        : { kind: 'error', text: 'DB 등록 요청을 접수하지 못했습니다. 연결 상태를 확인하고 다시 시도하세요.', caption: errorText(e) })
    } finally { setBusy(false) }
  }

  const selectCell = (row: WsRow, column: keyof typeof options) => {
    const value = String(row[column] ?? '')
    const key = `${row.recommendation_id}\u0000${column}`
    const directEnabled = column !== '상품카테고리' && column !== '리스크 등급'
    const direct = directEnabled && (directCells.has(key) || (value !== '' && !options[column].includes(value)))
    const list = direct || options[column].includes(value) ? options[column] : [...options[column], value]
    if (column === CRITERIA_COL || column === '대체키워드') {
      const searchableOptions = [DIRECT, ...list]
      return <div className={direct ? 'cell-direct-entry' : undefined}>
        <SearchSelect value={direct ? DIRECT : value} options={searchableOptions} placeholder="검색하거나 목록에서 선택" listClassName="criteria-options"
          onChange={next => {
            if (next === DIRECT) setDirectCells(current => new Set(current).add(key))
            else {
              setDirectCells(current => { const copy = new Set(current); copy.delete(key); return copy })
              editCell(row.recommendation_id, column, next ?? '')
            }
          }} />
        {direct && <textarea rows={2} value={value} placeholder={`${column} 직접 입력`}
          onChange={e => editCell(row.recommendation_id, column, e.target.value)} aria-label={`${column} 직접 입력`} />}
      </div>
    }
    return (
      <div className={direct ? 'cell-direct-entry' : undefined}>
        <select value={direct ? DIRECT : value} onChange={e => {
          const next = e.target.value
          if (directEnabled && next === DIRECT) {
            setDirectCells(current => new Set(current).add(key))
          } else {
            if (directEnabled) setDirectCells(current => {
                const nextRows = new Set(current)
                nextRows.delete(key)
                return nextRows
              })
            editCell(row.recommendation_id, column, next)
          }
        }} aria-label={column}>
          {directEnabled && <option value={DIRECT} data-direct-entry>{DIRECT}</option>}
          {list.map(o => <option key={o} value={o}>{o}</option>)}
        </select>
        {direct && <textarea rows={2} value={value} placeholder={`${column} 직접 입력`}
          onChange={e => editCell(row.recommendation_id, column, e.target.value)} aria-label={`${column} 직접 입력`} />}
      </div>
    )
  }

  return (
    <div>
      <h3>미매칭 후보군 분석 및 검토</h3>
      <div className="caption">모든 승인 계정의 공용 누적 통계입니다. 로그아웃 후에도 유지됩니다. OCR은 신뢰도 60% 이상만 수집합니다.</div>
      <div style={{ maxWidth: 520 }} className="mt">
        <TextInput label="미매칭 표현 검색" value={searchInput} maxLength={100} onChange={setSearchInput}
          onEnter={() => { setSearch(searchInput.trim()); setPage(0) }} />
      </div>
      <div className="row tight center mt">
        {total > PAGE && (
          <>
            <span className="caption">검색 결과 {total.toLocaleString()}종 · {page + 1}/{pageCount} 페이지</span>
            <Button small disabled={page <= 0} onClick={() => setPage(p => p - 1)}>이전</Button>
            <Button small disabled={page >= pageCount - 1} onClick={() => setPage(p => p + 1)}>다음</Button>
          </>
        )}
        <Button small onClick={() => { setSearch(searchInput.trim()); setRefreshKey(k => k + 1) }}>목록 새로고침</Button>
      </div>
      <div className="row tight mt">
        <Button onClick={buildCsv}>전체 누적 CSV 만들기</Button>
        {csvRows && <Button onClick={() => downloadCsv('unmatched_candidates.csv',
          ['미매칭 표현', '누적 출현 횟수', '분석 횟수', '상태', '최초 수집 시각', '최근 수집 시각'], csvRows)}>전체 누적 CSV 다운로드</Button>}
      </div>
      {listMsg && <Alert kind={listMsg.kind}>{listMsg.text}</Alert>}
      {loading && <Spinner />}
      {listError !== null ? (
        <>
          <Alert kind="error">공용 미매칭 후보를 불러오지 못했습니다. 잠시 후 새로고침하세요.</Alert>
          <div className="caption">진단 정보: {listError.slice(0, 200)}</div>
        </>
      ) : !rows.length && !loading ? (
        <Alert kind="info">아직 후보가 없습니다. 텍스트 분석 또는 한국어 OCR을 실행하면 자동으로 수집됩니다.</Alert>
      ) : (
        <>
          <div className="table-wrap mt">
            <table className="grid">
              <thead><tr>
                <th className="sel"><input type="checkbox" aria-label="전체 선택/해제" checked={selection.all && !Object.values(selection.ids).some(v => v === false)}
                  disabled={!rows.length} onChange={e => setSelection({ all: e.target.checked, ids: {} })} /></th>
                <th>미매칭 표현</th><th>최근 등록일시</th><th>처리상태</th><th className="num">검출횟수(중복포함)</th><th className="num">분석 횟수</th>
              </tr></thead>
              <tbody>
                {rows.map(r => {
                  const on = isSelected(r.term_norm)
                  return (
                    <tr key={r.term_norm} className={on ? 'selected' : undefined}>
                      <td className="sel"><input type="checkbox" checked={on} aria-label={`${surface(r)} 선택`} onChange={e => {
                        const ids = { ...selection.ids }
                        if (selection.all) { if (e.target.checked) delete ids[r.term_norm]; else ids[r.term_norm] = false }
                        else if (e.target.checked) ids[r.term_norm] = true
                        else delete ids[r.term_norm]
                        setSelection({ all: selection.all, ids })
                      }} /></td>
                      <td>{surface(r)}</td>
                      <td>{formatDatetime(r.last_seen)}</td>
                      <td>{STATUS_LABEL[r.review_status] ?? ''}</td>
                      <td className="num">{r.total_occurrences}</td>
                      <td className="num">{r.analysis_count}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          <div className="caption">페이지가 바뀌어도 선택은 유지됩니다. 전체 선택은 현재 검색결과 전체에 적용됩니다.</div>
          {singleSelected && (
            <form className="row mt" onSubmit={e => {
              e.preventDefault()
              if (!editText.trim()) { setListMsg({ kind: 'warning', text: '미매칭 표현을 입력하세요.' }); return }
              setSurfaceEdits(s => ({ ...s, [singleSelected.term_norm]: editText.trim() }))
              setListMsg({ kind: 'success', text: '선택한 표현을 수정했습니다.' })
            }}>
              <div className="col"><TextInput label="선택 후보 표현 수정" value={editText} onChange={setEditText} /></div>
              <Button type="submit">표현 수정 저장</Button>
            </form>
          )}
          {isAdmin && (
            <div className="mt">
              <Checkbox label="현재 누적 통계와 관측 기록을 삭제합니다. 이후 새 분석에서는 다시 수집될 수 있습니다." checked={confirmDelete} onChange={setConfirmDelete} />
              <Button onClick={removeSelected} disabled={busy}>선택 표현 영구 삭제</Button>
            </div>
          )}
        </>
      )}
      <div className="mt"><Button primary onClick={normalize} disabled={busy}>선택후보군 정규화 작업</Button></div>
      {busy && <Spinner />}
      {draftError && <Alert kind="warning">정규화 작업본을 저장하거나 복원하지 못했습니다. 연결 상태를 확인하세요.</Alert>}
      {queueError && <Alert kind="error">{`등록 요청을 불러오지 못했습니다: ${queueError}`}</Alert>}
      {isAdmin && queue.length > 0 && <div className="caption">누적된 DB 등록 요청: {queue.length}건</div>}
      {draftReady && wsRows.length > 0 && (
        <>
          <h4>정규화 추천 및 분류 입력</h4>
          <div className="caption">새 행은 + 버튼으로 추가하거나 행을 선택해 위·아래에 삽입할 수 있습니다.</div>
          <div className="table-wrap mt">
            <table className="grid normalization-grid">
              <thead><tr>
                <th className="sel"><input type="checkbox" aria-label="선택" title="누르면 표의 항목을 모두 선택하거나 해제합니다." checked={allWsSelected}
                  onChange={e => setDraft(d => ({ ...d, selected_ids: e.target.checked ? wsRows.map(r => r.recommendation_id) : [] }), true)} /></th>
                <th>추천 키워드</th><th>원본 표현</th><th className="num">출현 횟수</th><th>상품카테고리</th><th>리스크 등급</th>
                <th>세부 심의기준</th><th>증빙자료유형</th><th>대체키워드</th><th>요청 접수일</th>
              </tr></thead>
              <tbody>
                {wsRows.map(r => (
                  <tr key={r.recommendation_id} className={selectedIds.has(r.recommendation_id) ? 'selected' : undefined}>
                    <td className="sel"><input type="checkbox" aria-label={`${r.term || '빈 행'} 선택`} checked={selectedIds.has(r.recommendation_id)}
                      onChange={e => toggleRow(r.recommendation_id, e.target.checked)} /></td>
                    <td><input type="text" value={String(r.term ?? '')} onChange={e => editCell(r.recommendation_id, 'term', e.target.value)} aria-label="추천 키워드" /></td>
                    <td><input type="text" value={String(r.source_terms ?? '')} onChange={e => editCell(r.recommendation_id, 'source_terms', e.target.value)} aria-label="원본 표현" /></td>
                    <td className="num">{r.occurrences}</td>
                    <td>{selectCell(r, '상품카테고리')}</td>
                    <td>{selectCell(r, '리스크 등급')}</td>
                    <td>{selectCell(r, '리스크 등급별 세부 심의기준')}</td>
                    <td>{selectCell(r, '증빙자료유형')}</td>
                    <td>{selectCell(r, '대체키워드')}</td>
                    <td>{r.request_date}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="row tight mt">
            <Button small onClick={() => addRow(wsRows[wsRows.length - 1]?.recommendation_id ?? null, 'after')} title="표 끝에 빈 행 추가">＋</Button>
            <Button onClick={() => insertAt('before')}>선택 행 위에 빈 행 추가</Button>
            <Button onClick={() => insertAt('after')}>선택 행 아래에 빈 행 추가</Button>
            <Button onClick={removeRows}>선택 항목 삭제</Button>
          </div>
          <div className="row tight mt">
            <Button onClick={() => recommendSelected(false)} disabled={busy}>선택 키워드 AI 추천 초안</Button>
            {recommendProgress && <span className="caption">AI 추천 {recommendProgress.done}/{recommendProgress.total} 처리 완료</span>}
            {failedRecommendationIds.length > 0 && <Button small disabled={busy} onClick={() => recommendSelected(true)}>실패 키워드만 재시도 ({failedRecommendationIds.length})</Button>}
            {isAdmin ? (
              <>
                <Button primary onClick={approve} disabled={busy}>선택 후보 승인 및 DB 등록</Button>
                <Button onClick={reject} disabled={busy}>선택 요청 거절</Button>
                <Button onClick={async () => { await persist(draftRef.current); await loadQueue() }}>등록 요청 목록 새로고침</Button>
              </>
            ) : (
              <Button primary onClick={requestRegistration} disabled={busy}>선택 후보 DB 등록요청</Button>
            )}
            <Help text="선택한 행만 처리합니다. 셀 편집 내용은 작업본으로 자동 저장되어 다시 로그인해도 유지됩니다." />
          </div>
          {selectedRows.length === 1 && draft.ai_suggestions?.[selectedRows[0].recommendation_id] && (
            <div className="mt">
              <strong>분류 추천 · {selectedRows[0].term}</strong>
              <p>{draft.ai_suggestions[selectedRows[0].recommendation_id].reason}</p>
              {draft.ai_suggestions[selectedRows[0].recommendation_id].status === 'needs_category' &&
                draft.ai_suggestions[selectedRows[0].recommendation_id].category_options.map(option => (
                  <div className="row tight mt" key={option.category}>
                    <Button small disabled={busy} onClick={() => applyCategoryOption(selectedRows[0], draft.ai_suggestions[selectedRows[0].recommendation_id], option)}>
                      {option.category} · {option.risk} 적용
                    </Button>
                    <span className="caption">DB 사례: {option.keyword} / {option.criteria}</span>
                  </div>
                ))}
              {draft.ai_suggestions[selectedRows[0].recommendation_id].warnings.map((warning, index) => <div className="caption" key={index}>{warning}</div>)}
              {draft.ai_suggestions[selectedRows[0].recommendation_id].source_ids.map(id => {
                const source = draft.ai_suggestions[selectedRows[0].recommendation_id].sources.find(item => item.id === id)
                return source && <details key={id}><summary>[{id}] {source.label}</summary><pre style={{ whiteSpace: 'pre-wrap' }}>{source.text}</pre></details>
              })}
            </div>
          )}
          {selectedRows.length > 1 && selectedRows.map(row => {
            const suggestion = draft.ai_suggestions?.[row.recommendation_id]
            if (!suggestion) return null
            return <div className="mt" key={row.recommendation_id}>
              <strong>분류 추천 · {row.term}</strong>
              <p>{suggestion.reason}</p>
              {suggestion.status === 'needs_category' && suggestion.category_options.map(option => (
                <div className="row tight mt" key={option.category}>
                  <Button small disabled={busy} onClick={() => applyCategoryOption(row, suggestion, option)}>
                    {option.category} · {option.risk} 적용
                  </Button>
                  <span className="caption">DB 사례: {option.keyword} / {option.criteria}</span>
                </div>
              ))}
              {suggestion.warnings.map((warning, index) => <div className="caption" key={index}>{warning}</div>)}
            </div>
          })}
          {wsMsg && (
            <>
              <Alert kind={wsMsg.kind}>{wsMsg.text}</Alert>
              {wsMsg.caption && <div className="caption">{wsMsg.caption}</div>}
            </>
          )}
        </>
      )}
    </div>
  )
}
