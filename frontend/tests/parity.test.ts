/**
 * Parity checks for logic ported from Streamlit FIXED329. Expected values marked "(py)" were
 * produced with the same inputs in Python (hashlib / difflib / pandas behaviour).
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { formatDatetime, nextKwdNo, normalizeCatalog, normalizedDropdown, sortForDisplay } from '../src/lib/catalog.ts'
import { csvCell, toCsv } from '../src/lib/csv.ts'
import { buildSegments, extractToken, longestCommon, tooltipRows } from '../src/lib/highlight.ts'
import { numberedHelp } from '../src/lib/help.ts'
import { applyListFilters, EMPTY_FILTERS } from '../src/lib/listFilter.ts'
import { sha256Hex } from '../src/lib/sha256.ts'
import type { KeywordRow, Match } from '../src/lib/types.ts'
import { orderRows, blankRow, recommendationId, sourceKeys } from '../src/lib/workspace.ts'

const row = (code: string, term: string, category = '화장품', extra: Record<string, string> = {}): KeywordRow => ({
  kwd_no: code, '키워드명': term, '상품카테고리': category, '리스크 등급': '1등급(사용금지)', '대체키워드': '-',
  '리스크 등급별 세부 심의기준': '기준', '증빙자료유형': '-', '키워드 조회 수(누적카운트)': '0', '마지막 출력일자': '', ...extra,
})

const match = (start: number, end: number, code: string, term: string, risk = '1등급(사용금지)'): Match => ({
  term, start, end, category: '화장품', risk, detail: '', kwd_no: code, alternative: '', evidence_type: '', hit_count: '', last_search_date: '',
})

test('sha256 and recommendation ids match hashlib (py)', () => {
  assert.equal(sha256Hex('abc'), 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad')
  assert.equal(recommendationId({ term: '필러', source_terms: '필러는 | 필러를', occurrences: 3 }),
    'local:4d43c6ec80a0d8bdd554ac0950e88dcf10dd8a563fc6d9b6a19288362fba0a5e')
  assert.equal(recommendationId({ request_id: 'abc', term: 'x' }), 'request:abc')
  assert.equal(recommendationId({ recommendation_id: 'manual:1' }), 'manual:1')
})

test('longest common substring matches difflib find_longest_match (py)', () => {
  assert.deepEqual(longestCommon('안티에이징으로', '안티에이징(anti-aging)'), { a: 0, b: 0, size: 5 })
  assert.deepEqual(longestCommon('abc', 'xyz'), { a: 0, b: 0, size: 0 })
})

test('datetime display mirrors format_datetime_display', () => {
  assert.equal(formatDatetime('2026-11-07T06:00:00+00:00'), '2026-11-07 15:00:00')
  assert.equal(formatDatetime('2026-11-07T06:00:00Z'), '2026-11-07 15:00:00')
  assert.equal(formatDatetime('2026-11-07 15:41:26'), '2026-11-07 15:41:26')
  assert.equal(formatDatetime('2026-1-7'), '2026-01-07 00:00:00')
  assert.equal(formatDatetime(''), '')
  assert.equal(formatDatetime('미정'), '미정')
})

test('catalog normalisation folds the legacy registration column', () => {
  const { columns, rows } = normalizeCatalog(['kwd_no', '키워드명', '키워드등록일자'], [
    { kwd_no: 'A001', '키워드명': 'x', '키워드등록일자': '2026-01-01' } as KeywordRow,
    { kwd_no: 'A002', '키워드명': 'y', '키워드등록일자': '2026-01-02', '키워드 등록일자': '2026-02-02' } as KeywordRow,
  ])
  assert.ok(!columns.includes('키워드등록일자'))
  assert.ok(columns.includes('키워드 등록일자'))
  assert.equal(rows[0]['키워드 등록일자'], '2026-01-01')
  assert.equal(rows[1]['키워드 등록일자'], '2026-02-02')
  assert.equal(rows[0]['키워드 조회 수(누적카운트)'], '0')
})

test('display sort uses prefix, number, then name', () => {
  const sorted = sortForDisplay([row('B010', 'b'), row('A2', 'z'), row('B9', 'a'), row('A10', 'a'), row('xx', 'q')])
  assert.deepEqual(sorted.map(r => r.kwd_no), ['xx', 'A2', 'A10', 'B9', 'B010'])
})

test('next keyword number follows next_kwd_no', () => {
  const rows = [row('B001', 'a'), row('B007', 'b'), row('F0012', 'c', '식품')]
  assert.equal(nextKwdNo('화장품', rows), 'B008')
  assert.equal(nextKwdNo('식품', rows), 'F0013')
  assert.equal(nextKwdNo('건강기능식품', rows), 'G001')
  assert.equal(nextKwdNo('공산품', [...rows, row('I004', 'x', '기타')]), 'I005')
  assert.equal(nextKwdNo('새분류', rows), 'U001')
})

test('dropdown normalisation keeps dash last', () => {
  assert.deepEqual(normalizedDropdown(['보습', '-', ' 진정 ', '보습', '']), ['보습', '진정', '-'])
})

test('csv cells match pandas minimal quoting with BOM', () => {
  assert.equal(csvCell('a,b'), '"a,b"')
  assert.equal(csvCell('say "hi"'), '"say ""hi"""')
  assert.equal(csvCell('=SUM(1)'), '=SUM(1)')
  assert.equal(toCsv(['a', 'b'], [{ a: 1, b: null }]), '﻿a,b\n1,\n')
})

test('numbered help splits sentences and strips bullets/backticks', () => {
  assert.equal(numberedHelp('첫 문장입니다. 둘째 `코드`\n\n- O · 셋째'), '1. 첫 문장입니다.\n2. 둘째 코드\n3. O · 셋째')
})

test('kwd token extraction', () => {
  assert.equal(extractToken('us 036'), 'US036')
  assert.equal(extractToken(' B001 '), 'B001')
})

test('highlight segments: merge overlaps, keep all codes, code points, skip trailing code parens', () => {
  const catalog = [row('US036', '안티에이징'), row('US037', '에이징', '화장품', { '리스크 등급': '2등급(대체키워드사용)' })]
  const columns = Object.keys(catalog[0])
  const text = '😀 안티에이징 (US036) 끝'
  // code-point offsets: 😀=0, space=1, 안=2..징=6
  const segs = buildSegments(text, [match(2, 7, 'US036', '안티에이징'), match(4, 7, 'US037', '에이징', '2등급(대체키워드사용)')],
    { catalogRows: catalog, columns, mode: 'exact', partialMinLen: 2, approvedPartials: {} })
  assert.equal(segs.length, 3)
  assert.deepEqual(segs[0], { kind: 'text', text: '😀 ' })
  const mark = segs[1]
  assert.equal(mark.kind, 'mark')
  if (mark.kind !== 'mark') return
  assert.equal(mark.core, '안티에이징')
  assert.deepEqual(mark.entries.map(e => e.code), ['US036', 'US037'])
  assert.equal(mark.grade, 0) // mixed grades → yellow
  assert.deepEqual(segs[2], { kind: 'text', text: ' 끝' })
  const tip = mark.entries[0].tooltip
  const evidence = tip.find(r => r.label === '매칭 결과')
  assert.ok(evidence && evidence.kind === 'match' && evidence.matchedCore === '안티에이징')
  assert.equal(tip.find(r => r.label === '매칭 조건')?.kind, 'plain')
})

test('similar mode reports the approved expression that fired', () => {
  const catalog = [row('B001', '안티에이징')]
  const segs = buildSegments('에이징 관리', [match(0, 3, 'B001', '안티에이징')], {
    catalogRows: catalog, columns: Object.keys(catalog[0]), mode: 'similar', partialMinLen: 2,
    approvedPartials: { B001: { term: '안티에이징', expressions: ['에이징'] } },
  })
  const mark = segs[0]
  assert.ok(mark.kind === 'mark')
  if (mark.kind !== 'mark') return
  const condition = mark.entries[0].tooltip.find(r => r.label === '매칭 조건')
  assert.ok(condition?.kind === 'plain' && condition.value.includes('‘에이징’'))
})

test('tooltip rows: skip empty, rename last date, insert formatted registration date', () => {
  const r = row('B001', '필러', '화장품', { '대체키워드': '', '키워드 등록일자': '2026-01-02T00:00:00Z' })
  const rows = tooltipRows('B001', [r], Object.keys(r))
  const labels = rows.map(x => x.label)
  assert.ok(!labels.includes('대체키워드'))
  assert.equal(labels[labels.indexOf('마지막 검색일자') + 1], '키워드 등록일자')
  assert.equal((rows.find(x => x.label === '키워드 등록일자') as { value: string }).value, '2026-01-02 09:00:00')
  assert.equal(tooltipRows('Z999', [r], Object.keys(r))[1].label, 'msg')
})

test('list filter: comma OR, parentheses stripped, regex semantics', () => {
  const rows = [row('B001', '필러'), row('B002', '안티에이징(anti-aging)'), row('F001', '홍삼', '식품')]
  assert.deepEqual(applyListFilters(rows, { ...EMPTY_FILTERS, search: '(필러), 홍삼' }).map(r => r.kwd_no), ['B001', 'F001'])
  assert.deepEqual(applyListFilters(rows, { ...EMPTY_FILTERS, search: '^b00' }).map(r => r.kwd_no), ['B001', 'B002'])
  assert.deepEqual(applyListFilters(rows, { ...EMPTY_FILTERS, categories: ['식품'] }).map(r => r.kwd_no), ['F001'])
  assert.equal(applyListFilters(rows, { ...EMPTY_FILTERS, search: '[' }).length, 0)
})

test('workspace ordering and cleanup keys', () => {
  const a = { ...blankRow('a'), term: 'A' }, b = { ...blankRow('b'), term: 'B' }
  const m1 = blankRow('m1'), m2 = blankRow('m2'), m3 = blankRow('m3')
  const ordered = orderRows([a, b], [m1, m2, m3], {
    m1: { anchor_id: 'a', position: 'before' }, m2: { anchor_id: 'm1', position: 'after' }, m3: { anchor_id: 'gone', position: 'after' },
  })
  assert.deepEqual(ordered.map(r => r.recommendation_id), ['m1', 'm2', 'a', 'b', 'm3'])
  assert.deepEqual(sourceKeys([{ ...blankRow('x'), term: 'Ｘ', source_terms: '필러는 | 필러를' }, { ...blankRow('y'), term_norm: 'k' }]),
    ['k', '필러는', '필러를'])
})
