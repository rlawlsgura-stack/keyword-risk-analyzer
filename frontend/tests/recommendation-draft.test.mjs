import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { stripTypeScriptTypes } from 'node:module'
import test from 'node:test'
import vm from 'node:vm'

const source = stripTypeScriptTypes(readFileSync(new URL('../src/recommendationDraft.ts', import.meta.url), 'utf8'))
const module = new vm.SourceTextModule(source)
await module.link(() => { throw new Error('Draft load decision must not require network dependencies') })
await module.evaluate()
const { shouldLoadRecommendationDraft } = module.namespace

test('loads a draft on first visit for a signed-in user', () => {
  assert.equal(shouldLoadRecommendationDraft('member-1', null, 0, 0), true)
})

test('does not reload a draft when returning to the same screen', () => {
  assert.equal(shouldLoadRecommendationDraft('member-1', 'member-1', 0, 0), false)
})

test('loads again only after an explicit refresh request', () => {
  assert.equal(shouldLoadRecommendationDraft('member-1', 'member-1', 1, 0), true)
})

test('loads the new account draft after the signed-in user changes', () => {
  assert.equal(shouldLoadRecommendationDraft('member-2', 'member-1', 0, 0), true)
})

test('does not load a draft without a signed-in user', () => {
  assert.equal(shouldLoadRecommendationDraft(undefined, null, 0, 0), false)
})
