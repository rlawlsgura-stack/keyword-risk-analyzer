import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { stripTypeScriptTypes } from 'node:module'

const source = stripTypeScriptTypes(readFileSync(new URL('../src/reportCsv.ts', import.meta.url), 'utf8'))
const moduleUrl = `data:text/javascript;base64,${Buffer.from(source).toString('base64')}`
const { buildTopKeywordCsv } = await import(moduleUrl)

function parseCsv(csv) {
  const input = csv.replace(/^\uFEFF/, '')
  const rows = []
  let row = []
  let cell = ''
  let quoted = false

  for (let index = 0; index < input.length; index += 1) {
    const character = input[index]
    if (quoted) {
      if (character === '"' && input[index + 1] === '"') {
        cell += '"'
        index += 1
      } else if (character === '"') quoted = false
      else cell += character
    } else if (character === '"') quoted = true
    else if (character === ',') {
      row.push(cell)
      cell = ''
    } else if (character === '\r' && input[index + 1] === '\n') {
      row.push(cell)
      rows.push(row)
      row = []
      cell = ''
      index += 1
    } else cell += character
  }

  if (cell || row.length) {
    row.push(cell)
    rows.push(row)
  }
  return rows
}

test('report CSV keeps the 14-column order, Korean text, date and count', () => {
  const item = {
    search_rank: 1,
    hit_count: 63,
    keyword_data: {
      kwd_no: 'B245',
      키워드명: '안티에이징',
      상품카테고리: '화장품',
      '리스크 등급': '3등급(조건부사용)',
      대체키워드: '피부',
      '리스크 등급별 세부 심의기준': '관련 시험자료 확인',
      증빙자료유형: '인체적용시험결과서',
      '키워드 조회 수(누적카운트)': '22',
      '마지막 출력일자': '2026-11-05T00:03:34',
      키워드등록인: '',
      비고: '',
      '키워드 등록일자': '',
    },
  }
  const csv = buildTopKeywordCsv([item], value => value.replace('T', ' '))
  const rows = parseCsv(csv)

  assert.ok(csv.startsWith('\uFEFF"검색순위"'))
  assert.deepEqual(rows[0], [
    '검색순위', 'kwd_no', '키워드명', '상품카테고리', '리스크 등급', '대체키워드',
    '기간내_조회수', '리스크 등급별 세부 심의기준', '증빙자료유형',
    '키워드 조회 수(누적카운트)', '마지막 검색일자', '키워드등록인', '비고', '키워드 등록일자',
  ])
  assert.equal(rows[0].length, 14)
  assert.equal(rows[1].length, 14)
  assert.equal(rows[1][2], '안티에이징')
  assert.equal(rows[1][6], '63')
  assert.equal(rows[1][10], '2026-11-05 00:03:34')
})

test('report CSV quotes commas and doubles quotes without allowing formulas', () => {
  const item = {
    search_rank: 1,
    hit_count: 1,
    keyword_data: {
      대체키워드: '"피부, 진정"',
      비고: ' =1+1',
    },
  }
  const rows = parseCsv(buildTopKeywordCsv([item], value => value))
  assert.equal(rows[0][1], '대체키워드')
  assert.equal(rows[0][2], '기간내_조회수')
  assert.equal(rows[1][1], '"피부, 진정"')
  assert.equal(rows[1][2], '1')
  assert.equal(rows[1][3], "' =1+1")
})
