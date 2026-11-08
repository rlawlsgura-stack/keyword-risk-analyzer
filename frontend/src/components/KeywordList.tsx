import { useMemo, useState } from 'react'
import { DATETIME_COLUMNS, csvHeader, displayHeader, formatDatetime, formatRowDates, pySorted, sortForDisplay, uniqueValues } from '../lib/catalog.ts'
import { downloadCsv } from '../lib/csv.ts'
import { EMPTY_FILTERS as EMPTY, applyListFilters, type ListFilters as Filters } from '../lib/listFilter.ts'
import type { KeywordRow } from '../lib/types.ts'
import { Button, DataTable, MultiSelect, TextInput } from './ui.tsx'

/** The "🧰 리스트 필터" section (L4463-4654): filters apply only when 필터 적용 is pressed. */
export function KeywordList({ rows, columns }: { rows: readonly KeywordRow[]; columns: readonly string[] }) {
  const [draft, setDraft] = useState<Filters>(EMPTY)
  const [applied, setApplied] = useState<Filters>(EMPTY)
  const catOptions = useMemo(() => pySorted(uniqueValues(rows, '상품카테고리')), [rows])
  const riskOptions = useMemo(() => pySorted(uniqueValues(rows, '리스크 등급')), [rows])
  const proofOptions = useMemo(() => pySorted(uniqueValues(rows, '증빙자료유형')), [rows])
  const filtered = useMemo(() => sortForDisplay(applyListFilters(rows, applied)), [rows, applied])
  return (
    <div>
      <form onSubmit={e => { e.preventDefault(); setApplied(draft) }}>
        <div className="row" style={{ alignItems: 'flex-start' }}>
          <div className="col" style={{ flex: 3 }}>
            <TextInput label="키워드 검색" value={draft.search} placeholder="키워드명 / 대체키워드 / kwd_no 검색"
              onChange={v => setDraft(d => ({ ...d, search: v }))} />
          </div>
          <div className="col" style={{ flex: 2 }}><MultiSelect label="상품카테고리" value={draft.categories} options={catOptions} onChange={v => setDraft(d => ({ ...d, categories: v }))} /></div>
          <div className="col" style={{ flex: 2 }}><MultiSelect label="리스크 등급" value={draft.risks} options={riskOptions} onChange={v => setDraft(d => ({ ...d, risks: v }))} /></div>
          <div className="col" style={{ flex: 2 }}><MultiSelect label="증빙자료유형" value={draft.proofs} options={proofOptions} onChange={v => setDraft(d => ({ ...d, proofs: v }))} /></div>
        </div>
        <div className="row tight mt">
          <Button type="submit">필터 적용</Button>
          <Button onClick={() => { setDraft(EMPTY); setApplied(EMPTY) }}>필터 초기화</Button>
        </div>
      </form>
      <div className="caption mt">현재 표시된 항목: {filtered.length} / 전체: {rows.length}</div>
      <DataTable rows={filtered} rowKey={(r, i) => `${r.kwd_no}-${i}`}
        columns={columns.map(c => ({
          key: c, label: displayHeader(c),
          render: (r: KeywordRow) => (DATETIME_COLUMNS.has(c) ? formatDatetime(r[c]) : r[c] ?? ''),
        }))} />
      <div className="mt">
        <Button onClick={() => {
          // Downloads the whole catalog (not the filtered view), as in Streamlit.
          const out = sortForDisplay(rows).map(r => {
            const formatted = formatRowDates(r)
            return Object.fromEntries(columns.map(c => [csvHeader(c), formatted[c] ?? '']))
          })
          downloadCsv('keywords_current.csv', columns.map(csvHeader), out)
        }}>키워드 CSV 다운로드</Button>
      </div>
    </div>
  )
}
