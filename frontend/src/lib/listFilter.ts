import type { KeywordRow } from './types.ts'

export type ListFilters = { search: string; categories: string[]; risks: string[]; proofs: string[] }
export const EMPTY_FILTERS: ListFilters = { search: '', categories: [], risks: [], proofs: [] }

/** pandas str.contains(part, case=False) — regex semantics, literal fallback for invalid patterns. */
function containsMatcher(part: string): (value: string) => boolean {
  try {
    const re = new RegExp(part, 'i')
    return value => re.test(value)
  } catch {
    const lower = part.toLowerCase()
    return value => value.toLowerCase().includes(lower)
  }
}

/** "🧰 리스트 필터" (L4463-4654): comma-separated OR search over four fields, AND across multiselects. */
export function applyListFilters(rows: readonly KeywordRow[], f: ListFilters): KeywordRow[] {
  let out = [...rows]
  const parts = f.search.split(',').map(p => p.trim().replace(/^[\s()]+|[\s()]+$/g, '')).filter(Boolean)
  if (parts.length) {
    const matchers = parts.map(containsMatcher)
    const fields = ['키워드명', '대체키워드', 'kwd_no', '리스크 등급별 세부 심의기준']
    out = out.filter(r => fields.some(c => matchers.some(m => m(String(r[c] ?? '')))))
  }
  if (f.categories.length) out = out.filter(r => f.categories.includes(String(r['상품카테고리'] ?? '')))
  if (f.risks.length) out = out.filter(r => f.risks.includes(String(r['리스크 등급'] ?? '')))
  if (f.proofs.length) out = out.filter(r => f.proofs.includes(String(r['증빙자료유형'] ?? '')))
  return out
}
