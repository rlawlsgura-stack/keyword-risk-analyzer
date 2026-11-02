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

export async function analyzeText(text: string, mode: AnalysisMode, partialMinLen: number): Promise<AnalysisResult> {
  if (!supabase) throw new Error('연결 설정이 필요합니다.')
  const { data, error } = await supabase.auth.getSession()
  if (error || !data.session) throw new Error('로그인 세션이 만료되었습니다. 다시 로그인해 주세요.')

  const response = await fetch(`${apiBaseUrl.replace(/\/$/, '')}/api/v1/analyses`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${data.session.access_token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ text, mode, partial_min_len: partialMinLen, record: false }),
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(typeof body?.detail === 'string' ? body.detail : `분석 요청에 실패했습니다 (${response.status}).`)
  }
  return response.json() as Promise<AnalysisResult>
}
