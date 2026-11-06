import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import vm from 'node:vm'
import { stripTypeScriptTypes } from 'node:module'

// Execute the real API module with session/fetch stubs; never contact Supabase.
async function loadApi(pages) {
  const calls = []
  const context = vm.createContext({
    URLSearchParams, FormData, window: { sessionStorage: {} },
    fetch: async url => {
      calls.push(new URL(url))
      assert.ok(pages.length, 'unexpected API request')
      return { ok: true, json: async () => pages.shift() }
    },
  })
  const source = stripTypeScriptTypes(readFileSync(new URL('../src/api.ts', import.meta.url), 'utf8'))
  const auth = new vm.SyntheticModule(['createClient'], function () {
    this.setExport('createClient', () => ({ auth: { getSession: async () => ({
      data: { session: { access_token: 'test-only-token' } }, error: null,
    }) } }))
  }, { context })
  const module = new vm.SourceTextModule(source, {
    context,
    initializeImportMeta(meta) {
      meta.env = { VITE_SUPABASE_URL: 'https://auth.example.test',
        VITE_SUPABASE_PUBLISHABLE_KEY: 'test-only-key', VITE_API_BASE_URL: 'https://api.example.test' }
    },
  })
  await module.link(name => {
    assert.equal(name, '@supabase/supabase-js')
    return auth
  })
  await module.evaluate()
  return { api: module.namespace, calls }
}

test('filtered CSV snapshot carries every filter across pages', async () => {
  const rows = Array.from({ length: 500 }, (_, index) => ({ kwd_no: `A${index}` }))
  const { api, calls } = await loadApi([
    { total: 501, revision: 7, items: rows },
    { total: 501, revision: 7, items: [{ kwd_no: 'A500' }] },
  ])
  const filters = { category: '화장품', risk: '1등급', evidenceType: '시험성적서' }
  const result = await api.loadKeywordSnapshot('안티[에이징]', filters)
  assert.equal(result.items.length, 501)
  assert.equal(result.items[500].kwd_no, 'A500')
  assert.equal(calls.length, 2)
  calls.forEach((url, index) => {
    assert.equal(url.searchParams.get('q'), '안티[에이징]')
    assert.equal(url.searchParams.get('category'), filters.category)
    assert.equal(url.searchParams.get('risk'), filters.risk)
    assert.equal(url.searchParams.get('evidence_type'), filters.evidenceType)
    assert.equal(url.searchParams.get('offset'), String(index * 500))
  })
})

test('empty full catalog remains compatible with existing callers', async () => {
  const { api, calls } = await loadApi([{ total: 0, revision: 0, items: [] }])
  const rows = await api.loadAllKeywords()
  assert.equal(rows.length, 0)
  assert.equal(calls.length, 1)
  for (const field of ['q', 'category', 'risk', 'evidence_type']) {
    assert.equal(calls[0].searchParams.get(field), '')
  }
})

test('top-keyword report sends the selected inclusive date range and row limit', async () => {
  const { api, calls } = await loadApi([{ items: [] }])
  await api.loadTopKeywords('2026-10-30', '2026-11-05', 10)
  assert.equal(calls.length, 1)
  assert.equal(calls[0].pathname, '/api/v1/reports/top-keywords')
  assert.equal(calls[0].searchParams.get('start_date'), '2026-10-30')
  assert.equal(calls[0].searchParams.get('end_date'), '2026-11-05')
  assert.equal(calls[0].searchParams.get('limit'), '10')
})

test('CSV snapshot refuses to mix different catalog revisions', async () => {
  const { api } = await loadApi([
    { total: 2, revision: 7, items: [{ kwd_no: 'A001' }] },
    { total: 2, revision: 8, items: [{ kwd_no: 'A002' }] },
  ])
  await assert.rejects(api.loadKeywordSnapshot('안티'), /원장이 불러오는 중 변경/)
})

test('search-wide candidate selection follows server search/sort across pages and skips processed rows', async () => {
  const { api, calls } = await loadApi([
    { total: 3, rows: [
      { term_norm: 'a', review_status: 'pending' },
      { term_norm: 'b', review_status: 'registration_requested' },
    ] },
    { total: 3, rows: [{ term_norm: 'c', review_status: 'pending' }] },
  ])
  const rows = await api.loadAllSelectableUnmatchedTerms('안티_%', 'registered')
  assert.deepEqual(Array.from(rows, row => row.term_norm), ['a', 'c'])
  assert.equal(calls.length, 2)
  calls.forEach((url, index) => {
    assert.equal(url.searchParams.get('search'), '안티_%')
    assert.equal(url.searchParams.get('sort'), 'registered')
    assert.equal(url.searchParams.get('offset'), String(index * 2))
  })
})

test('empty candidate search finishes without an extra page request', async () => {
  const { api, calls } = await loadApi([{ total: 0, rows: [] }])
  assert.equal((await api.loadAllSelectableUnmatchedTerms('', 'occurrences')).length, 0)
  assert.equal(calls.length, 1)
})

test('search-wide selection rejects changing or incomplete candidate lists', async () => {
  for (const last of [
    { total: 3, rows: [{ term_norm: 'c', review_status: 'pending' }] },
    { total: 2, rows: [] },
    { total: 2, rows: [{ term_norm: 'a', review_status: 'pending' }] },
  ]) {
    const { api } = await loadApi([
      { total: 2, rows: [{ term_norm: 'a', review_status: 'pending' }] }, last,
    ])
    await assert.rejects(api.loadAllSelectableUnmatchedTerms('', 'occurrences'), /후보 목록/)
  }
})
