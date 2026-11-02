import { createClient } from '@supabase/supabase-js'

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL
const publishableKey = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY
const apiBaseUrl = import.meta.env.VITE_API_BASE_URL

export const configurationReady = Boolean(supabaseUrl && publishableKey && apiBaseUrl)

export const supabase = configurationReady
  ? createClient(supabaseUrl, publishableKey, {
      auth: { storage: window.sessionStorage, persistSession: true, autoRefreshToken: true },
    })
  : null

export type Match = {
  term: string
  start: number
  end: number
  category: string
  risk: string
  detail: string
  kwd_no: string | null
}

export type AnalysisResult = {
  analysis_id: string
  matches: Match[]
  unique_keywords: string[]
  offset_unit: 'unicode_codepoint'
  end_exclusive: boolean
  recorded: boolean
}

export type AnalysisMode = 'exact' | 'similar' | 'partial'

export type AnalysisInput = {
  text: string
  mode: AnalysisMode
  partial_min_len: number
  strip_bracket_notes: boolean
  normalize_whitespace: boolean
  ignore_case: boolean
  normalize_symbols: boolean
  categories: string[]
  risks: string[]
}

export type KeywordRow = {
  kwd_no: string
  키워드명: string
  상품카테고리: string
  '리스크 등급': string
  대체키워드: string
  리스크 등급별 세부 심의기준: string
  증빙자료유형: string
  '키워드 조회 수(누적카운트)': string
  마지막 출력일자: string
}

export type TopKeyword = { kwd_no: string; hit_count: number; term: string | null }

async function requestApi(path: string, init?: RequestInit) {
  if (!supabase) throw new Error('연결 설정이 필요합니다.')
  const { data, error } = await supabase.auth.getSession()
  if (error || !data.session) throw new Error('로그인 세션이 만료되었습니다. 다시 로그인해 주세요.')

  const response = await fetch(`${apiBaseUrl.replace(/\/$/, '')}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${data.session.access_token}`,
      'Content-Type': 'application/json',
    },
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(typeof body?.detail === 'string' ? body.detail : `API 요청에 실패했습니다 (${response.status}).`)
  }
  return response.json()
}

export async function loadAnalysisFilters(): Promise<{ categories: string[]; risks: string[] }> {
  return requestApi('/api/v2/analysis-filters')
}

export async function analyzeText(input: AnalysisInput, analysisId: string): Promise<AnalysisResult> {
  return requestApi('/api/v2/analyses', {
    method: 'POST',
    body: JSON.stringify({ ...input, analysis_id: analysisId }),
  })
}

export async function loadKeywords(offset: number, query: string): Promise<{
  total: number
  revision: string | null
  items: KeywordRow[]
}> {
  const params = new URLSearchParams({ offset: String(offset), limit: '100', q: query })
  return requestApi(`/api/v1/keywords?${params}`)
}

export async function loadTopKeywords(days: number, limit: number): Promise<{ items: TopKeyword[] }> {
  const params = new URLSearchParams({ days: String(days), limit: String(limit) })
  return requestApi(`/api/v1/reports/top-keywords?${params}`)
}
