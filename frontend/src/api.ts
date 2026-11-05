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
  alternative?: string
  evidence_type?: string
  hit_count?: string
  last_search_date?: string
}

export type AnalysisResult = {
  analysis_id: string
  matches: Match[]
  unique_keywords: string[]
  unique_keyword_rows: KeywordRow[]
  keyword_revision: number | null
  offset_unit: 'unicode_codepoint'
  end_exclusive: boolean
  recorded: boolean
  unmatched_collection_pending: boolean
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
  [field: string]: string
  kwd_no: string
  키워드명: string
  상품카테고리: string
  '리스크 등급': string
  대체키워드: string
  '리스크 등급별 세부 심의기준': string
  증빙자료유형: string
  '키워드 조회 수(누적카운트)': string
  '마지막 출력일자': string
}

export type TopKeyword = {
  kwd_no: string
  hit_count: number
  term: string | null
  search_rank: number
  keyword_data: KeywordRow
}
export type AnalysisFilters = { categories: string[]; risks: string[]; evidence_types?: string[] }
export type RegulationQuestion = {
  direction: 'keyword_to_law' | 'law_to_keywords'
  query: string
  context_text: string
  category: string
}
export type RegulationResult = {
  status: string
  administrator_review: boolean
  answer: string
  sources: { id: string; label: string; text: string; url: string }[]
  keyword_matches: { kwd_no: string; 키워드명: string; 상품카테고리: string; '리스크 등급': string;
    대체키워드: string; '리스크 등급별 세부 심의기준': string }[]
  llm_used: boolean
}
export type UnmatchedTerm = {
  term_norm: string
  display_term: string
  total_occurrences: number
  analysis_count: number
  first_seen: string
  last_seen: string
  review_status: 'open' | 'registration_requested' | 'ignored' | string
}
export type KeywordRequestRecord = {
  id: string
  requester_email?: string
  kwd_no: string
  keyword_name: string
  request_type: string
  request_detail: string
  status: string
  admin_reply: string
  created_at: string
}
export type KeywordRequestMessage = {
  id: string; request_id: string; author_id: string | null; author_email: string
  author_role: 'user' | 'admin'; is_initial: boolean; is_legacy: boolean
  reply_to_id: string | null; body: string; status: string; created_at: string
}
export type RequestEmailNotifications = { enabled: boolean; configured: boolean }
export type AdminUser = { id: string; email: string; role: 'admin' | 'member' | null; email_confirmed: boolean }
export type UnmatchedRegistrationRequest = {
  id: string; term: string; term_norm: string; source_terms: string; occurrences: number
  category: string; risk: string; criteria: string; evidence_type: string; alternative: string; created_at: string
}
export type NormalizationSettings = { ignored_symbols: string[]; extra_suffixes: string[]; default_suffix_count: number }
export type NormalizationRecommendation = {
  recommendation_id: string; term: string; source_terms: string; occurrences: number
  category: string; risk: string; criteria: string; evidence_type: string; alternative: string
}
export type OCRCandidate = {
  term: string; confidence: number; occurrences: number; source_files: string[]
  category: string; risk: string; detail: string; evidence: string; alternative: string; approved: boolean
}
export type OCRFileResult = {
  index: number; name: string; count: number; error: string; truncated?: boolean
  lines: { text: string; confidence: number; bbox: number[] | null }[]
  preview_data?: string | null; image_width?: number; image_height?: number; preview_error?: string
}
export type ApprovedPartialKeyword = { kwd_no: string; term: string }
export type ApprovedPartialRules = Record<string, { term: string; expressions: string[] }>
export type AdminDropdownSettings = {
  opt_categories: string[]; opt_risks: string[]; opt_details: string[]
  opt_evidences: string[]; opt_alt_terms: string[]
}

async function requestApi(path: string, init?: RequestInit) {
  if (!supabase) throw new Error('연결 설정이 필요합니다.')
  const { data, error } = await supabase.auth.getSession()
  if (error || !data.session) throw new Error('로그인 세션이 만료되었습니다. 다시 로그인해 주세요.')

  const response = await fetch(`${apiBaseUrl.replace(/\/$/, '')}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${data.session.access_token}`,
      ...(init?.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
    },
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(typeof body?.detail === 'string' ? body.detail : `API 요청에 실패했습니다 (${response.status}).`)
  }
  return response.json()
}

export async function loadAnalysisFilters(): Promise<AnalysisFilters> {
  return requestApi('/api/v2/analysis-filters')
}

export async function analyzeText(input: AnalysisInput, analysisId: string): Promise<AnalysisResult> {
  return requestApi('/api/v2/analyses', {
    method: 'POST',
    body: JSON.stringify({ ...input, analysis_id: analysisId }),
  })
}

export async function loadKeywords(offset: number, query: string,
  filters: { category: string; risk: string; evidenceType: string }, limit = 100): Promise<{
  total: number
  revision: number | null
  items: KeywordRow[]
}> {
  const params = new URLSearchParams({ offset: String(offset), limit: String(limit), q: query,
    category: filters.category, risk: filters.risk, evidence_type: filters.evidenceType })
  return requestApi(`/api/v1/keywords?${params}`)
}

export async function loadKeywordSnapshot(query = '',
  filters = { category: '', risk: '', evidenceType: '' }): Promise<{ items: KeywordRow[]; revision: number }> {
  const all: KeywordRow[] = []
  let revision: number | null = null
  while (true) {
    const page = await loadKeywords(all.length, query, filters, 500)
    if (revision === null) revision = page.revision
    else if (page.revision !== revision) throw new Error('키워드 원장이 불러오는 중 변경되었습니다. 다시 불러와 주세요.')
    all.push(...page.items)
    if (all.length >= page.total || page.items.length === 0) return { items: all, revision: revision ?? 0 }
  }
}

export async function loadAllKeywords(): Promise<KeywordRow[]> {
  return (await loadKeywordSnapshot()).items
}

export async function loadTopKeywords(startDate: string, endDate: string, limit: number): Promise<{ items: TopKeyword[] }> {
  const params = new URLSearchParams({ start_date: startDate, end_date: endDate, limit: String(limit) })
  return requestApi(`/api/v1/reports/top-keywords?${params}`)
}

export async function resetAdminReportData(scope: 'all' | 'last-7-days'): Promise<{ removed?: number }> {
  return requestApi(`/api/v1/admin/reports/reset/${scope}`, { method: 'POST' })
}

export async function askRegulation(question: RegulationQuestion): Promise<RegulationResult> {
  return requestApi('/api/v1/regulation/questions', {
    method: 'POST',
    body: JSON.stringify(question),
  })
}

export async function loadUnmatchedTerms(offset: number, search: string,
  sort: 'occurrences' | 'registered'): Promise<{ total: number; rows: UnmatchedTerm[] }> {
  const params = new URLSearchParams({ offset: String(offset), limit: '100', search, sort })
  return requestApi(`/api/v1/unmatched-terms?${params}`)
}

export async function exportUnmatchedTerms(): Promise<UnmatchedTerm[]> {
  const result = await requestApi('/api/v1/unmatched-terms/export')
  return result.items
}

export async function loadAllSelectableUnmatchedTerms(search: string,
  sort: 'occurrences' | 'registered'): Promise<UnmatchedTerm[]> {
  const selected: UnmatchedTerm[] = []
  const seen = new Set<string>()
  let offset = 0
  let total: number | null = null
  while (true) {
    const page = await loadUnmatchedTerms(offset, search, sort)
    if (total === null) total = page.total
    if (page.total !== total || (!page.rows.length && offset < total)) {
      throw new Error('후보 목록이 변경되었습니다. 새로고침 후 다시 선택하세요.')
    }
    for (const row of page.rows) {
      if (seen.has(row.term_norm)) throw new Error('후보 목록 순서가 변경되었습니다. 다시 선택하세요.')
      seen.add(row.term_norm)
      if (row.review_status === 'pending') selected.push(row)
    }
    offset += page.rows.length
    if (offset >= total) return selected
  }
}

export async function deleteAdminUnmatchedTerms(terms: string[]): Promise<{ deleted: number }> {
  return requestApi('/api/v1/admin/unmatched-terms/delete', {
    method: 'POST', body: JSON.stringify({ terms }),
  })
}

export async function submitUnmatchedRegistrationRequests(candidates: {
  term: string
  source_terms: string
  occurrences: number
  category?: string
  risk?: string
  criteria?: string
  evidence_type?: string
  alternative?: string
}[]): Promise<{ items: unknown[] }> {
  return requestApi('/api/v1/unmatched-terms/registration-requests', {
    method: 'POST', body: JSON.stringify({ candidates }),
  })
}

export async function normalizeUnmatchedTerms(candidates: { surface: string; occurrences: number }[]): Promise<{
  items: { term: string; source_terms: string; occurrences: number }[]
}> {
  return requestApi('/api/v1/unmatched-terms/normalize', { method: 'POST', body: JSON.stringify({ candidates }) })
}

export async function loadUnmatchedRecommendationDraft(): Promise<{ payload: Record<string, unknown> | null }> {
  return requestApi('/api/v1/unmatched-terms/recommendation-draft')
}

export async function saveUnmatchedRecommendationDraft(payload: Record<string, unknown>): Promise<void> {
  await requestApi('/api/v1/unmatched-terms/recommendation-draft', {
    method: 'PUT', body: JSON.stringify({ payload }),
  })
}

export async function extractOCRImages(files: File[]): Promise<{ files: OCRFileResult[]; candidates: OCRCandidate[] }> {
  const form = new FormData()
  files.forEach(file => form.append('files', file))
  return requestApi('/api/v1/ocr/extract', { method: 'POST', body: form })
}

export async function saveOCRKeywords(revision: number, candidates: Pick<OCRCandidate,
  'term' | 'category' | 'risk' | 'detail' | 'evidence' | 'alternative'>[]): Promise<{
  added: string[]; revision: number
}> {
  return requestApi('/api/v1/ocr/keywords', {
    method: 'POST', body: JSON.stringify({
      revision,
      candidates: candidates.map(({ term, category, risk, detail, evidence, alternative }) =>
        ({ term, category, risk, detail, evidence, alternative })),
    }),
  })
}

export async function findKeywords(query: string): Promise<KeywordRow[]> {
  const filters = { category: '', risk: '', evidenceType: '' }
  const result = await loadKeywords(0, query, filters, 100)
  return result.items
}

export async function loadKeywordRequests(): Promise<KeywordRequestRecord[]> {
  const result = await requestApi('/api/v1/keyword-requests')
  return result.items
}

export async function loadKeywordRequestMessages(requestId: string): Promise<KeywordRequestMessage[]> {
  const result = await requestApi(`/api/v1/keyword-requests/${encodeURIComponent(requestId)}/messages`)
  return result.items
}

export async function addKeywordRequestMessage(requestId: string, body: string,
  options: { replyToId?: string; status?: string } = {}): Promise<KeywordRequestMessage> {
  return requestApi(`/api/v1/keyword-requests/${encodeURIComponent(requestId)}/messages`, {
    method: 'POST', body: JSON.stringify({ body, reply_to_id: options.replyToId, status: options.status }),
  })
}

export async function editKeywordRequestMessage(requestId: string, messageId: string, body: string,
  requestType?: string): Promise<{ id: string; action: string }> {
  return requestApi(`/api/v1/keyword-requests/${encodeURIComponent(requestId)}/messages/${encodeURIComponent(messageId)}`, {
    method: 'PUT', body: JSON.stringify({ body, request_type: requestType }),
  })
}

export async function deleteKeywordRequestMessage(requestId: string, messageId: string): Promise<{ id: string; action: string }> {
  return requestApi(`/api/v1/keyword-requests/${encodeURIComponent(requestId)}/messages/${encodeURIComponent(messageId)}`, {
    method: 'DELETE',
  })
}

export async function deleteKeywordRequest(requestId: string): Promise<KeywordRequestRecord> {
  return requestApi(`/api/v1/keyword-requests/${encodeURIComponent(requestId)}`, { method: 'DELETE' })
}

export async function submitKeywordRequest(input: {
  kwd_no: string
  request_type: 'risk_grade_adjustment' | 'review_criteria_change'
  request_detail: string
}): Promise<KeywordRequestRecord> {
  return requestApi('/api/v1/keyword-requests', { method: 'POST', body: JSON.stringify(input) })
}

export async function updateKeywordRequest(requestId: string, status: string,
  adminReply: string): Promise<{ id: string; status: string; admin_reply: string }> {
  return requestApi(`/api/v1/keyword-requests/${encodeURIComponent(requestId)}`, {
    method: 'PUT', body: JSON.stringify({ status, admin_reply: adminReply }),
  })
}

export async function loadRequestEmailNotifications(): Promise<RequestEmailNotifications> {
  return requestApi('/api/v1/admin/keyword-request-notifications')
}

export async function saveRequestEmailNotifications(enabled: boolean): Promise<RequestEmailNotifications> {
  return requestApi('/api/v1/admin/keyword-request-notifications', {
    method: 'PUT', body: JSON.stringify({ enabled }),
  })
}

export async function loadAdminUsers(page: number): Promise<{ items: AdminUser[]; has_more: boolean }> {
  const params = new URLSearchParams({ page: String(page), per_page: '100' })
  return requestApi(`/api/v1/admin/users?${params}`)
}

export async function updateAdminUserRole(userId: string, role: 'admin' | 'member',
  expectedRole: 'admin' | 'member' | null): Promise<AdminUser> {
  return requestApi(`/api/v1/admin/users/${encodeURIComponent(userId)}/role`, {
    method: 'PUT', body: JSON.stringify({ role, expected_role: expectedRole }),
  })
}

export async function saveAdminKeywords(revision: number, rows: KeywordRow[]): Promise<{ revision: number }> {
  return requestApi('/api/v1/admin/keywords', {
    method: 'PUT', body: JSON.stringify({ revision, rows }),
  })
}

export async function deleteAdminKeywords(revision: number, kwdNos: string[]): Promise<{ deleted: number; revision: number }> {
  return requestApi('/api/v1/admin/keywords/delete', {
    method: 'POST', body: JSON.stringify({ revision, kwd_nos: kwdNos }),
  })
}

export async function uploadAdminKeywords(file: File, revision: number, mode: 'merge' | 'overwrite'): Promise<{
  added_count: number; dedup_removed: number; revision: number; total: number
}> {
  const form = new FormData()
  form.append('file', file)
  form.append('revision', String(revision))
  form.append('mode', mode)
  return requestApi('/api/v1/admin/keywords/upload', { method: 'POST', body: form })
}

export async function downloadAdminKeywordTemplateXlsx(): Promise<Blob> {
  if (!supabase) throw new Error('연결 설정이 필요합니다.')
  const { data, error } = await supabase.auth.getSession()
  if (error || !data.session) throw new Error('로그인 세션이 만료되었습니다. 다시 로그인해 주세요.')
  const response = await fetch(`${apiBaseUrl.replace(/\/$/, '')}/api/v1/admin/keywords/template.xlsx`, {
    headers: { Authorization: `Bearer ${data.session.access_token}` },
  })
  if (!response.ok) {
    const detail = await response.json().catch(() => null)
    throw new Error(detail?.detail ?? 'XLSX 템플릿을 내려받지 못했습니다.')
  }
  return response.blob()
}

export async function loadAdminUnmatchedRequests(): Promise<UnmatchedRegistrationRequest[]> {
  const result = await requestApi('/api/v1/admin/unmatched-registration-requests')
  return result.items
}

export async function rejectAdminUnmatchedRequests(requestIds: string[]): Promise<number> {
  const result = await requestApi('/api/v1/admin/unmatched-registration-requests/reject', {
    method: 'POST', body: JSON.stringify({ request_ids: requestIds }),
  })
  return result.rejected
}

export async function approveAdminUnmatchedRequests(requestIds: string[], updates: {
  request_id: string; category: string; risk: string; criteria: string; evidence_type: string; alternative: string
}[]): Promise<{
  approved: number; added: string[]; cleared_requests: number
}> {
  return requestApi('/api/v1/admin/unmatched-registration-requests/approve', {
    method: 'POST', body: JSON.stringify({ request_ids: requestIds, updates }),
  })
}

export async function loadAdminNormalizationSettings(): Promise<NormalizationSettings> {
  return requestApi('/api/v1/admin/normalization-settings')
}

export async function saveAdminNormalizationSettings(settings: Omit<NormalizationSettings, 'default_suffix_count'>): Promise<{
  ignored_symbols: string[]; extra_suffixes: string[]
}> {
  return requestApi('/api/v1/admin/normalization-settings', {
    method: 'PUT', body: JSON.stringify(settings),
  })
}

export async function loadAdminApprovedPartials(): Promise<{
  keywords: ApprovedPartialKeyword[]; rules: ApprovedPartialRules
}> {
  return requestApi('/api/v1/admin/approved-partials')
}

export async function saveAdminApprovedPartials(input: {
  kwd_no: string; term: string; expected_expressions: string[]; expressions: string[]
}): Promise<{ kwd_no: string; term: string; expressions: string[] }> {
  return requestApi('/api/v1/admin/approved-partials', {
    method: 'PUT', body: JSON.stringify(input),
  })
}

export async function loadAdminDropdownSettings(): Promise<AdminDropdownSettings> {
  return requestApi('/api/v1/admin/dropdown-settings')
}

export async function loadDropdownSettings(): Promise<AdminDropdownSettings> {
  return requestApi('/api/v1/dropdown-settings')
}

export async function saveAdminDropdownSettings(settings: AdminDropdownSettings): Promise<AdminDropdownSettings> {
  return requestApi('/api/v1/admin/dropdown-settings', {
    method: 'PUT', body: JSON.stringify(settings),
  })
}
