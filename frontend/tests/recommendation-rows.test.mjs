import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { stripTypeScriptTypes } from 'node:module'
import test from 'node:test'
import vm from 'node:vm'

const source = stripTypeScriptTypes(readFileSync(new URL('../src/recommendationRows.ts', import.meta.url), 'utf8'))
const module = new vm.SourceTextModule(source)
await module.link(() => { throw new Error('Row editing must not require network dependencies') })
await module.evaluate()
const { insertRecommendation } = module.namespace
const ids = rows => Array.from(rows, row => row.recommendation_id)
const rows = [
  { recommendation_id: 'a', term: '기존명', category: '화장품' },
  { recommendation_id: 'b', term: '다른명', category: '식품' },
]
const blank = { recommendation_id: 'manual:new', term: '', category: '' }

test('manual first/last row can be added without overwriting existing edits', () => {
  assert.deepEqual(ids(insertRecommendation([], blank, [], 'end')), ['manual:new'])
  const result = insertRecommendation(rows, blank, [], 'end')
  assert.deepEqual(ids(result), ['a', 'b', 'manual:new'])
  assert.equal(result[0], rows[0])
  assert.deepEqual(ids(rows), ['a', 'b'])
})

test('insertion keeps the anchor ID and edits stable above and below', () => {
  assert.deepEqual(ids(insertRecommendation(rows, blank, ['a'], 'before')), ['manual:new', 'a', 'b'])
  assert.deepEqual(ids(insertRecommendation(rows, blank, ['a'], 'after')), ['a', 'manual:new', 'b'])
  assert.equal(rows[0].category, '화장품')
})

test('insertion requires exactly one existing anchor', () => {
  for (const selected of [[], ['a', 'b'], ['missing']]) {
    assert.throws(() => insertRecommendation(rows, blank, selected, 'before'), /하나만 선택/)
  }
})
