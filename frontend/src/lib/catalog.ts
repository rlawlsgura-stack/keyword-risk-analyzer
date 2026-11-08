import { COUNT_COL, DB_COLS, LAST_COL, type KeywordRow } from './types.ts'

export const CRITERIA_COL = '리스크 등급별 세부 심의기준'
export const REG_DATE_COL = '키워드 등록일자'
export const LEGACY_REG_DATE_COL = '키워드등록일자'

/** Header renames used by Streamlit tables (L330-334). */
export const DISPLAY_RENAMES: Record<string, string> = {
  [CRITERIA_COL]: `${CRITERIA_COL} (셀을 더블 클릭하여 전체 내용을 확인하세요)`,
  [LAST_COL]: '마지막 검색일자',
}
export const displayHeader = (column: string) => DISPLAY_RENAMES[column] ?? column
/** CSV downloads rename only the last-output column (L4654, L5877). */
export const csvHeader = (column: string) => (column === LAST_COL ? '마지막 검색일자' : column)

export const DATETIME_COLUMNS = new Set([
  '키워드 등록일자', '키워드등록일자', '마지막 출력일자', '마지막 검색일자', '접수 시각', '요청 접수일',
  '최초 수집 시각', '최근 수집 시각', '등록일시', 'request_date', 'created_at', 'first_seen', 'last_seen', 'ts',
])

const pad = (n: number) => String(n).padStart(2, '0')

/** pandas.to_datetime + Asia/Seoul + '%Y-%m-%d %H:%M:%S' (format_datetime_display, L2091). */
export function formatDatetime(value: unknown): string {
  if (value === null || value === undefined) return ''
  const raw = String(value).trim()
  if (!raw || raw.toLowerCase() === 'nan' || raw.toLowerCase() === 'nat' || raw === 'None') return ''
  const hasZone = /([zZ]|[+-]\d{2}:?\d{2})$/.test(raw)
  if (hasZone) {
    const date = new Date(raw)
    if (Number.isNaN(date.getTime())) return raw
    const kst = new Date(date.getTime() + 9 * 3600 * 1000)
    return `${kst.getUTCFullYear()}-${pad(kst.getUTCMonth() + 1)}-${pad(kst.getUTCDate())} ${pad(kst.getUTCHours())}:${pad(kst.getUTCMinutes())}:${pad(kst.getUTCSeconds())}`
  }
  const m = /^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})(?:[ T](\d{1,2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?)?$/.exec(raw)
  if (!m) return raw
  return `${m[1]}-${pad(+m[2])}-${pad(+m[3])} ${pad(+(m[4] ?? 0))}:${pad(+(m[5] ?? 0))}:${pad(+(m[6] ?? 0))}`
}

export function formatRowDates<R extends Record<string, unknown>>(row: R): R {
  const out: Record<string, unknown> = { ...row }
  for (const key of Object.keys(out)) if (DATETIME_COLUMNS.has(key)) out[key] = formatDatetime(out[key])
  return out as R
}

/** Mirrors _ensure_counter_columns (L519): add counters/registration date, fold the legacy column. */
export function normalizeCatalog(rawColumns: string[], rows: KeywordRow[]): { columns: string[]; rows: KeywordRow[] } {
  const columns = [...(rawColumns.length ? rawColumns : DB_COLS)]
  for (const column of DB_COLS) if (!columns.includes(column)) columns.push(column)
  if (!columns.includes(REG_DATE_COL)) columns.push(REG_DATE_COL)
  const hasLegacy = columns.includes(LEGACY_REG_DATE_COL)
  const finalColumns = columns.filter(c => c !== LEGACY_REG_DATE_COL)
  const out = rows.map(row => {
    const next: KeywordRow = { ...row }
    for (const column of finalColumns) {
      if (next[column] === undefined || next[column] === null) next[column] = column === COUNT_COL ? '0' : ''
      else next[column] = String(next[column])
    }
    if (hasLegacy) {
      if (!String(next[REG_DATE_COL] ?? '').trim()) next[REG_DATE_COL] = String(row[LEGACY_REG_DATE_COL] ?? '').trim()
      delete (next as Record<string, string>)[LEGACY_REG_DATE_COL]
    }
    return next
  })
  return { columns: finalColumns, rows: out }
}

const KWD_SPLIT = /^([A-Za-z]+)(\d+)$/
export function splitKwd(code: string): [string, number] {
  const m = KWD_SPLIT.exec(String(code))
  return m ? [m[1], parseInt(m[2], 10)] : ['', 0]
}

const cmp = (a: string, b: string) => (a < b ? -1 : a > b ? 1 : 0)

/** sort_for_display (L654): prefix, number, 키워드명 — stable. */
export function sortForDisplay<R extends Record<string, unknown>>(rows: readonly R[]): R[] {
  return rows
    .map((row, index) => ({ row, index, key: splitKwd(String(row.kwd_no ?? '')) }))
    .sort((a, b) => cmp(a.key[0], b.key[0]) || a.key[1] - b.key[1]
      || cmp(String(a.row['키워드명'] ?? ''), String(b.row['키워드명'] ?? '')) || a.index - b.index)
    .map(x => x.row)
}

/** sort_db_internal (L642): category, prefix, number, 키워드명. */
export function sortInternal<R extends Record<string, unknown>>(rows: readonly R[]): R[] {
  return rows
    .map((row, index) => ({ row, index, key: splitKwd(String(row.kwd_no ?? '')) }))
    .sort((a, b) => cmp(String(a.row['상품카테고리'] ?? ''), String(b.row['상품카테고리'] ?? ''))
      || cmp(a.key[0], b.key[0]) || a.key[1] - b.key[1]
      || cmp(String(a.row['키워드명'] ?? ''), String(b.row['키워드명'] ?? '')) || a.index - b.index)
    .map(x => x.row)
}

const CATEGORY_PREFIX: Record<string, string> = { '공통(전체)': 'A', '식품': 'F', '건강기능식품': 'G', '화장품': 'B', '공산품': 'I' }

/** next_kwd_no (L754): most common prefix in the category, its max number + 1, width ≥ 3. */
export function nextKwdNo(category: string, rows: readonly KeywordRow[], taken: ReadonlySet<string> = new Set()): string {
  const cat = String(category).trim()
  const codes = rows.filter(r => String(r['상품카테고리'] ?? '').trim() === cat).map(r => String(r.kwd_no ?? '').trim())
  const counts = new Map<string, number>()
  for (const code of codes) {
    const m = /^([A-Z]+)(\d{3,})$/.exec(code)
    if (m) counts.set(m[1], (counts.get(m[1]) ?? 0) + 1)
  }
  let prefix = [...counts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0]
  if (!prefix) {
    const first = (cat.slice(0, 1) || 'U').toUpperCase()
    prefix = CATEGORY_PREFIX[cat] ?? (/[A-Z]/.test(first) ? first : 'U')
  }
  const re = new RegExp(`^${prefix}(\\d+)$`)
  const nums = codes.map(c => re.exec(c)).filter((m): m is RegExpExecArray => Boolean(m))
  const width = Math.max(3, ...nums.map(m => m[1].length))
  let next: number
  if (nums.length) next = Math.max(...nums.map(m => parseInt(m[1], 10))) + 1
  else {
    // Session counter fallback: highest number for this prefix anywhere in the catalog.
    const any = rows.map(r => /^([A-Z]+)(\d+)$/.exec(String(r.kwd_no ?? '').trim())).filter(m => m && m[1] === prefix) as RegExpExecArray[]
    next = (any.length ? Math.max(...any.map(m => parseInt(m[2], 10))) : 0) + 1
  }
  const existing = new Set([...rows.map(r => String(r.kwd_no ?? '').trim().toUpperCase()), ...[...taken].map(t => t.toUpperCase())])
  let code = `${prefix}${String(next).padStart(width, '0')}`
  while (existing.has(code.toUpperCase())) code = `${prefix}${String(++next).padStart(width, '0')}`
  return code
}

/** normalize_dropdown_lists (L476): trimmed, de-duplicated, Korean-sorted, '-' always last. */
export function normalizedDropdown(values: Iterable<string>): string[] {
  const list = koSorted(new Set([...values].map(v => String(v ?? '').trim()).filter(v => v && v !== '-')))
  return [...list, '-']
}

/** Unique trimmed non-empty values of a column. */
export function uniqueValues(rows: readonly KeywordRow[], column: string): string[] {
  const set = new Set<string>()
  for (const row of rows) {
    const value = String(row[column] ?? '').trim()
    if (value) set.add(value)
  }
  return [...set]
}

/** Korean-aware sort used for Streamlit's _ko_sorted option lists. */
export const koSorted = (values: Iterable<string>) => [...values].sort((a, b) => a.localeCompare(b, 'ko'))
/** Python sorted() order (code points). */
export const pySorted = (values: Iterable<string>) => [...values].sort(cmp)

export function riskGrade(risk: string): number {
  const c = String(risk ?? '').trim().charAt(0)
  return c >= '1' && c <= '5' ? Number(c) : 0
}

export function nowKstString(): string {
  return formatDatetime(new Date().toISOString())
}

export function todayKst(): string {
  return nowKstString().slice(0, 10)
}

export function addDays(isoDate: string, days: number): string {
  const d = new Date(`${isoDate}T00:00:00Z`)
  d.setUTCDate(d.getUTCDate() + days)
  return d.toISOString().slice(0, 10)
}
