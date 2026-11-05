import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

// 실제 API 함수의 본문을 실행해 OCR 화면용 속성이 저장 요청에 섞이지 않는지 확인한다.
const source = readFileSync(new URL('../src/api.ts', import.meta.url), 'utf8')
const start = source.indexOf('export async function saveOCRKeywords(')
assert.notEqual(start, -1)
const bodyStart = source.indexOf('  return requestApi(', start)
const bodyEnd = source.indexOf('\n}', bodyStart)
assert.ok(bodyStart > start && bodyEnd > bodyStart)
let captured
const send = new Function('requestApi', 'revision', 'candidates', source.slice(bodyStart, bodyEnd))
const candidate = {
  term: 'TEST', category: '화장품', risk: '4등급(사용가능)',
  detail: '로컬 QA 합성 분류', evidence: '-', alternative: '-',
  confidence: 0.99, occurrences: 1, source_files: ['sample.png'], approved: true,
}
send((path, options) => { captured = { path, ...options } }, 2, [candidate])
assert.equal(captured.path, '/api/v1/ocr/keywords')
assert.equal(captured.method, 'POST')
assert.deepEqual(JSON.parse(captured.body), { revision: 2, candidates: [{
  term: 'TEST', category: '화장품', risk: '4등급(사용가능)',
  detail: '로컬 QA 합성 분류', evidence: '-', alternative: '-',
}] })
assert.equal(candidate.approved, true)
console.log('OCR save payload contract: PASS')
