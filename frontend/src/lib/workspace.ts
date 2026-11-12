import { sha256Hex } from './sha256.ts'

import type { KeywordSuggestion } from './types.ts'

/** Recommendation workspace model shared with Streamlit's draft payload (version 1). */
export const WS_COLUMNS = ['term', 'source_terms', 'occurrences', '상품카테고리', '리스크 등급', '리스크 등급별 세부 심의기준', '증빙자료유형', '대체키워드'] as const

export type WsRow = {
  recommendation_id: string
  term: string
  source_terms: string
  occurrences: number
  request_id: string
  request_date: string
  term_norm: string
  상품카테고리: string
  '리스크 등급': string
  '리스크 등급별 세부 심의기준': string
  증빙자료유형: string
  대체키워드: string
  [key: string]: unknown
}

export type Placement = { anchor_id: string | null; position: 'before' | 'after' }

export type Draft = {
  version: 1
  recommendations: Record<string, unknown>[]
  edits: Record<string, Record<string, unknown>>
  selected_ids: string[]
  hidden_ids: string[]
  manual_rows: WsRow[]
  manual_placements: Record<string, Placement>
  recommendation_version: number
  ai_suggestions: Record<string, KeywordSuggestion>
}

export const emptyDraft = (): Draft => ({
  version: 1, recommendations: [], edits: {}, selected_ids: [], hidden_ids: [], manual_rows: [], manual_placements: {}, recommendation_version: 0, ai_suggestions: {},
})

const str = (v: unknown) => (v === null || v === undefined || (typeof v === 'number' && Number.isNaN(v)) ? '' : String(v).trim())

/** Python str() of the occurrences value used inside the id hash (ints, possibly floats from JSON). */
function pyNumber(v: unknown): string {
  if (v === null || v === undefined || v === '') return ''
  return String(v)
}

/** unmatched_recommendation_id (L4722). */
export function recommendationId(row: Record<string, unknown>): string {
  const rid = str(row.recommendation_id)
  if (rid) return rid
  const requestId = str(row.request_id)
  if (requestId) return `request:${requestId}`
  const identity = [str(row.term), str(row.source_terms), pyNumber(row.occurrences).trim()].join('\0')
  return 'local:' + sha256Hex(identity)
}

export function blankRow(id: string): WsRow {
  return {
    recommendation_id: id, term: '', source_terms: '', occurrences: 0, request_id: '', request_date: '', term_norm: '',
    상품카테고리: '', '리스크 등급': '', '리스크 등급별 세부 심의기준': '', 증빙자료유형: '', 대체키워드: '-',
  }
}

export function toWsRow(raw: Record<string, unknown>): WsRow {
  const row = { ...blankRow(''), ...raw } as WsRow
  for (const k of ['상품카테고리', '리스크 등급', '리스크 등급별 세부 심의기준', '증빙자료유형'] as const) row[k] = str(row[k])
  if (row.대체키워드 === null || row.대체키워드 === undefined) row.대체키워드 = '-'
  row.occurrences = Number(row.occurrences) || 0
  row.recommendation_id = recommendationId(raw)
  return row
}

/** _order_manual_unmatched_recommendations (L4736). */
export function orderRows(base: WsRow[], manual: WsRow[], placements: Record<string, Placement>): WsRow[] {
  const before = new Map<string | null, WsRow[]>(), after = new Map<string | null, WsRow[]>()
  for (const row of manual) {
    const p = placements[row.recommendation_id] ?? { anchor_id: null, position: 'after' }
    const target = p.position === 'before' ? before : after
    const list = target.get(p.anchor_id ?? null) ?? []
    list.push(row)
    target.set(p.anchor_id ?? null, list)
  }
  const ordered: WsRow[] = []
  const emitted = new Set<string>()
  const visit = (row: WsRow) => {
    if (emitted.has(row.recommendation_id)) return
    for (const child of before.get(row.recommendation_id) ?? []) visit(child)
    ordered.push(row)
    emitted.add(row.recommendation_id)
    for (const child of after.get(row.recommendation_id) ?? []) visit(child)
  }
  base.forEach(visit)
  manual.forEach(visit)
  return ordered
}

/** unmatched_registration_source_keys (L4694) — used to tell whether a row has cleanup keys. */
export function sourceKeys(rows: WsRow[]): string[] {
  const keys = new Set<string>()
  for (const item of rows) {
    const requestKey = str(item.term_norm)
    if (requestKey) { keys.add(requestKey); continue }
    const sourceTerms = str(item.source_terms)
    const sources = sourceTerms ? sourceTerms.split(' | ') : [str(item.term)]
    for (const s of sources) if (s.trim()) keys.add(s.normalize('NFKC').toLowerCase().trim())
  }
  return [...keys].filter(k => k.length >= 1 && k.length <= 100).sort()
}
