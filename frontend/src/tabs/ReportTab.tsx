import { useCallback, useEffect, useState } from 'react'
import { loadTopKeywords, resetReport } from '../lib/api.ts'
import { CRITERIA_COL, DATETIME_COLUMNS, addDays, csvHeader, displayHeader, formatDatetime, todayKst } from '../lib/catalog.ts'
import { downloadCsv } from '../lib/csv.ts'
import { COUNT_COL, type TopKeyword } from '../lib/types.ts'
import { useStore } from '../store.tsx'
import { Alert, Button, Checkbox, DataTable, NumberInput, Spinner, TextInput, errorText } from '../components/ui.tsx'

const PERIOD_COL = '기간내_조회수'

/** Column order of the Streamlit report table (L5841-5876). */
export function reportColumns(catalogColumns: readonly string[]): string[] {
  const base = catalogColumns.filter(c => c !== 'kwd_no')
  const cols = ['검색순위', 'kwd_no', ...base]
  const anchor = cols.indexOf('대체키워드') >= 0 ? cols.indexOf('대체키워드') : cols.indexOf('증빙자료유형')
  if (anchor >= 0) cols.splice(anchor + 1, 0, PERIOD_COL)
  else cols.push(PERIOD_COL)
  return cols
}

export function reportRows(items: readonly TopKeyword[], columns: readonly string[]): Record<string, string | number>[] {
  return items.map(item => {
    const row: Record<string, string | number> = {}
    for (const c of columns) {
      if (c === '검색순위') row[c] = item.search_rank
      else if (c === 'kwd_no') row[c] = item.kwd_no
      else if (c === PERIOD_COL) row[c] = item.hit_count
      else row[c] = DATETIME_COLUMNS.has(c) ? formatDatetime(item.keyword_data[c]) : item.keyword_data[c] ?? ''
    }
    return row
  })
}

export function ReportTab({ active }: { active: boolean }) {
  const { catalog, isAdmin, reloadCatalog } = useStore()
  const today = todayKst()
  const [limit, setLimit] = useState(10)
  const [start, setStart] = useState(addDays(today, -6))
  const [end, setEnd] = useState(today)
  const [items, setItems] = useState<TopKeyword[] | null>(null)
  const [hasLog, setHasLog] = useState(true)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [confirmAll, setConfirmAll] = useState(false)
  const [confirmWeek, setConfirmWeek] = useState(false)
  const [resetMsg, setResetMsg] = useState<{ kind: 'success' | 'warning' | 'error'; text: string } | null>(null)

  const load = useCallback(async () => {
    setBusy(true); setError('')
    try {
      // Streamlit's empty-state message depends on "no hits in the last 7 days".
      const recent = await loadTopKeywords(addDays(todayKst(), -6), todayKst(), 1)
      setHasLog(recent.items.length > 0)
      const s = start <= end ? start : end
      const result = await loadTopKeywords(s, end < s ? s : end, limit)
      setItems(result.items)
    } catch (e) {
      setError(`리포트 생성 중 오류: ${errorText(e)}`)
    } finally { setBusy(false) }
  }, [start, end, limit])

  useEffect(() => { if (active) void load() }, [active, load])

  const columns = reportColumns(catalog?.columns ?? [])
  const rows = items ? reportRows(items, columns) : []

  const doReset = async (scope: 'all' | 'last-7-days') => {
    setResetMsg(null)
    if (scope === 'all' && !confirmAll) { setResetMsg({ kind: 'warning', text: '전체 초기화 확인란을 먼저 선택하세요.' }); return }
    if (scope === 'last-7-days' && !confirmWeek) { setResetMsg({ kind: 'warning', text: '최근 7일 초기화 확인란을 먼저 선택하세요.' }); return }
    try {
      const result = await resetReport(scope)
      if (scope === 'all') { setResetMsg({ kind: 'success', text: '전체 초기화 완료 (로그 유지)' }); setConfirmAll(false) }
      else { setResetMsg({ kind: 'success', text: `최근 7일 기록 ${result.removed ?? 0}건을 리포트에서 제외했습니다.` }); setConfirmWeek(false) }
      await reloadCatalog()
      await load()
    } catch (e) {
      setResetMsg({ kind: 'error', text: `${scope === 'all' ? '초기화 실패' : '최근 7일 초기화 실패'}: ${errorText(e)}` })
    }
  }

  return (
    <div>
      <h3>📈 분석리포트</h3>
      {busy && <Spinner />}
      {error && <Alert kind="error">{error}</Alert>}
      {!hasLog && items !== null ? (
        <Alert kind="info">조회 로그가 아직 없습니다. 분석을 몇 번 실행하면 리포트가 생성됩니다.</Alert>
      ) : (
        <>
          <div className="row">
            <div className="col"><NumberInput label="Top N" value={limit} min={1} max={100} onChange={setLimit} /></div>
            <div className="col">
              <label className="field">기간</label>
              <div className="row tight" style={{ flexWrap: 'nowrap' }}>
                <TextInput type="date" value={start} onChange={v => setStart(v > today ? today : v)} />
                <span style={{ alignSelf: 'center' }}>–</span>
                <TextInput type="date" value={end} onChange={v => setEnd(v ? (v > today ? today : v) : start)} />
              </div>
            </div>
          </div>
          <div className="mt">
            <DataTable rows={rows} rowKey={(r, i) => `${r.kwd_no}-${i}`} showIndex={false} emptyText="선택한 기간에 조회 기록이 없습니다."
              columns={columns.map(c => ({ key: c, label: displayHeader(c), num: c === PERIOD_COL || c === COUNT_COL }))} />
          </div>
          <div className="mt">
            <Button onClick={() => downloadCsv('period_topN_report.csv', columns.map(c => (c === CRITERIA_COL ? c : csvHeader(c))),
              rows.map(r => Object.fromEntries(columns.map(c => [c === CRITERIA_COL ? c : csvHeader(c), r[c]]))))}>
              리포트 CSV 다운로드 (선택 기간 Top N)
            </Button>
          </div>
        </>
      )}
      {isAdmin && (
        <>
          <hr />
          <h3>🔁 조회 수 초기화</h3>
          <div className="row" style={{ alignItems: 'flex-start' }}>
            <div className="col">
              <Checkbox label="전체 조회 수를 0으로 초기화하고 '마지막 검색일자'를 비우기" checked={confirmAll} onChange={setConfirmAll} />
              <Button onClick={() => doReset('all')}>전체 초기화 실행</Button>
            </div>
            <div className="col">
              <Checkbox label="최근 7일 조회수 초기화 (로그에서 최근 7일 기록 삭제)" checked={confirmWeek} onChange={setConfirmWeek} />
              <Button onClick={() => doReset('last-7-days')}>최근 7일 초기화 실행</Button>
            </div>
          </div>
          {resetMsg && <Alert kind={resetMsg.kind}>{resetMsg.text}</Alert>}
        </>
      )}
    </div>
  )
}
