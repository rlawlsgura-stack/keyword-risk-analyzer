import { CRITERIA_COL, LEGACY_REG_DATE_COL, REG_DATE_COL, formatDatetime, riskGrade } from './catalog.ts'
import { LAST_COL, type AnalysisMode, type ApprovedPartialRules, type KeywordRow, type Match } from './types.ts'

/** Port of highlight_text (Streamlit FIXED329 L1215-1424) as structured data instead of HTML. */

export const RISK_BG: Record<number, string> = { 1: '#ffc9c9', 2: '#a5d8ff', 3: '#d0bfff', 4: '#b2f2bb', 5: '#d8f5a2', 0: '#ffd43b' }
export const RISK_TEXT: Record<number, string> = { 1: '#e03131', 2: '#1c7ed6', 3: '#7048e8', 4: '#2f9e44' }

export type TooltipRow =
  | { kind: 'plain'; label: string; value: string }
  | { kind: 'match'; label: string; matched: string; registered: string; matchedCore: string; registeredCore: string }

export type CodeEntry = {
  code: string
  token: string
  toggleKey: string
  groupKey: string
  color: string
  tooltip: TooltipRow[]
}

export type Segment =
  | { kind: 'text'; text: string }
  | { kind: 'mark'; lead: string; core: string; trail: string; grade: number; entries: CodeEntry[] }

const TOKEN_RE = /([A-Za-z]{2})\s*([0-9]{3,})/

export function extractToken(raw: string | null | undefined): string {
  const s = raw === null || raw === undefined ? '' : String(raw)
  const m = TOKEN_RE.exec(s)
  return m ? (m[1] + m[2]).toUpperCase() : s.trim()
}

function splitToken(raw: string): string {
  const m = TOKEN_RE.exec(raw)
  return m ? (m[1] + m[2]).toUpperCase() : raw
}

/** difflib.SequenceMatcher(autojunk=False).find_longest_match over whole strings. */
export function longestCommon(a: string, b: string): { a: number; b: number; size: number } {
  const A = Array.from(a), B = Array.from(b)
  let best = { a: 0, b: 0, size: 0 }
  let prev = new Array<number>(B.length + 1).fill(0)
  for (let i = 1; i <= A.length; i++) {
    const cur = new Array<number>(B.length + 1).fill(0)
    for (let j = 1; j <= B.length; j++) {
      if (A[i - 1] === B[j - 1]) {
        cur[j] = prev[j - 1] + 1
        if (cur[j] > best.size) best = { a: i - cur[j], b: j - cur[j], size: cur[j] }
      }
    }
    prev = cur
  }
  return best
}

const sliceCp = (cps: string[], start: number, end: number) => cps.slice(start, end).join('')

/** build_kwd_tooltip_data (L1168-1212). */
export function tooltipRows(code: string, catalogRows: readonly KeywordRow[], columns: readonly string[]): TooltipRow[] {
  if (!catalogRows.length) return [{ kind: 'plain', label: 'kwd_no', value: code }, { kind: 'plain', label: 'msg', value: 'DB가 로드되지 않았습니다.' }]
  let row: KeywordRow | undefined
  for (const r of catalogRows) if (String(r.kwd_no ?? '').trim() === String(code).trim()) row = r
  if (!row) return [{ kind: 'plain', label: 'kwd_no', value: code }, { kind: 'plain', label: 'msg', value: '해당 번호의 행을 찾지 못했습니다.' }]
  let registration = ''
  for (const col of [REG_DATE_COL, LEGACY_REG_DATE_COL]) {
    const value = String(row[col] ?? '').trim()
    if (value) { registration = value; break }
  }
  const out: TooltipRow[] = []
  const keys = [...columns, ...Object.keys(row).filter(k => !columns.includes(k))]
  for (const col of keys) {
    if (col === REG_DATE_COL || col === LEGACY_REG_DATE_COL) continue
    const value = String(row[col] ?? '').trim()
    if (!value && col !== LAST_COL) continue
    const label = col === CRITERIA_COL ? CRITERIA_COL : col === LAST_COL ? '마지막 검색일자' : col
    out.push({ kind: 'plain', label, value })
  }
  const lastIdx = out.findIndex(r => r.label === '마지막 검색일자')
  out.splice(lastIdx >= 0 ? lastIdx + 1 : out.length, 0, { kind: 'plain', label: '키워드 등록일자', value: formatDatetime(registration) })
  return out.length ? out : [{ kind: 'plain', label: 'kwd_no', value: code }]
}

export function buildSegments(text: string, matches: readonly Match[], opts: {
  catalogRows: readonly KeywordRow[]; columns: readonly string[]; mode: AnalysisMode; partialMinLen: number
  approvedPartials: ApprovedPartialRules
}): Segment[] {
  const cps = Array.from(text)
  if (!matches.length) return [{ kind: 'text', text }]

  type Info = { start: number; end: number; ids: string[]; risk: Map<string, number>; records: { norm: string; match: Match; seg: string }[] }
  const spans = new Map<string, Info>()
  for (const m of matches) {
    const seg = sliceCp(cps, m.start, m.end)
    if (!seg) continue
    const key = `${m.start}:${m.end}`
    let info = spans.get(key)
    if (!info) { info = { start: m.start, end: m.end, ids: [], risk: new Map(), records: [] }; spans.set(key, info) }
    if (m.kwd_no) {
      info.ids.push(m.kwd_no)
      const norm = extractToken(m.kwd_no)
      info.risk.set(norm, riskGrade(m.risk))
      info.records.push({ norm, match: m, seg })
    }
  }
  if (!spans.size) return [{ kind: 'text', text }]

  const ordered: Info[] = []
  for (const info of [...spans.values()].sort((a, b) => a.start - b.start || b.end - a.end)) {
    const last = ordered[ordered.length - 1]
    if (last && info.start < last.end) {
      last.end = Math.max(last.end, info.end)
      last.ids.push(...info.ids)
      for (const [k, v] of info.risk) last.risk.set(k, v)
      last.records.push(...info.records)
    } else {
      ordered.push({ ...info, ids: [...info.ids], risk: new Map(info.risk), records: [...info.records] })
    }
  }

  const out: Segment[] = []
  let cur = 0
  const parenRe = /^[ \t\r\f\v\n]*\(([\s\S]{0,200}?)\)/
  for (const info of ordered) {
    if (info.start < cur) continue
    if (cur < info.start) out.push({ kind: 'text', text: sliceCp(cps, cur, info.start) })
    const seg = sliceCp(cps, info.start, info.end)
    const seen = new Set<string>()
    const ids = info.ids.filter(raw => {
      const norm = extractToken(raw) || String(raw).trim()
      if (seen.has(norm)) return false
      seen.add(norm)
      return true
    })
    const core = seg.trim()
    const entries: CodeEntry[] = ids.map(raw => {
      const norm = extractToken(raw) || String(raw).trim()
      const token = splitToken(String(raw))
      const grade = info.risk.get(norm) ?? 0
      const tooltip = tooltipRows(norm, opts.catalogRows, opts.columns)
      const evidence = info.records.find(r => r.norm === norm)
      if (evidence) {
        const registered = String(evidence.match.term).trim()
        const common = longestCommon(evidence.seg, registered)
        const mcp = Array.from(evidence.seg), rcp = Array.from(registered)
        const matchedCore = common.size >= 2 ? mcp.slice(common.a, common.a + common.size).join('') : ''
        const registeredCore = common.size >= 2 ? rcp.slice(common.b, common.b + common.size).join('') : ''
        let condition: string
        if (opts.mode === 'similar') {
          const saved = opts.approvedPartials[String(evidence.match.kwd_no ?? '')]
          const approved = saved && saved.term === registered ? saved.expressions : []
          const hit = approved.find(expr => evidence.seg.toLowerCase().includes(String(expr).toLowerCase()))
          condition = hit ? `2글자 이상 승인 표현 ‘${hit}’가 입력 문구의 단어 경계와 일치했습니다.`
            : '2글자 이상인 입력·등록 내용어 토큰을 Kiwi로 분석해 일치했습니다.'
        } else if (opts.mode === 'partial') {
          condition = `글자 수 매칭 방식에서 최소 ${Math.max(2, opts.partialMinLen)}글자 조건을 충족한 부분 문자열이 일치했습니다.`
        } else {
          condition = '키워드 완전 일치 방식으로 등록 표현이 입력 문구에서 발견됐습니다. 설정한 표기 비교 옵션이 적용될 수 있습니다.'
        }
        const dateIdx = tooltip.findIndex(r => r.label === '마지막 검색일자')
        let at = dateIdx >= 0 ? dateIdx + 1 : tooltip.length
        if (at < tooltip.length && tooltip[at].label === '키워드 등록일자') at++
        tooltip.splice(at, 0,
          { kind: 'match', label: '매칭 결과', matched: evidence.seg, registered, matchedCore, registeredCore },
          { kind: 'plain', label: '매칭 조건', value: condition })
      }
      const key = JSON.stringify([norm, core])
      return { code: norm, token: token || norm, toggleKey: key, groupKey: core, color: RISK_TEXT[grade] ?? 'inherit', tooltip }
    })
    const grades = new Set([...info.risk.values()].filter(Boolean))
    const grade = grades.size === 1 ? [...grades][0] : 0
    out.push({ kind: 'mark', lead: seg.slice(0, seg.length - seg.trimStart().length), core, trail: seg.slice(seg.trimEnd().length), grade, entries })
    cur = info.end
    const tail = sliceCp(cps, cur, cps.length)
    const paren = parenRe.exec(tail)
    if (paren && TOKEN_RE.test(paren[1] ?? '')) cur += Array.from(paren[0]).length
  }
  if (cur < cps.length) out.push({ kind: 'text', text: sliceCp(cps, cur, cps.length) })
  return out
}
