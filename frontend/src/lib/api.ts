import { API_BASE_URL, supabase } from './supabase.ts'
import type {
  AdminUser, AnalysisFilters, AnalysisInput, AnalysisResult, ApprovedPartialRules, DropdownSettings,
  KeywordPage, KeywordRequestMessage, MatchingRules, KeywordRequestRecord, KeywordRequestType, KeywordRow,
  NormalizationRecommendation, NormalizationSettings, OCRCandidate, OCRFileResult,
  RegistrationCandidate, RegulationResult, RegulationUsageSummary, Role, TopKeyword, UnmatchedPage, UnmatchedRegistrationRequest,
  UnmatchedSort, UnmatchedTerm,
} from './types.ts'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function accessToken(): Promise<string> {
  if (!supabase) throw new ApiError(0, '연결 설정이 필요합니다.')
  const { data, error } = await supabase.auth.getSession()
  if (error || !data.session) throw new ApiError(401, '로그인 세션이 만료되었습니다. 다시 로그인해 주세요.')
  return data.session.access_token
}

function detailMessage(body: unknown, status: number): string {
  const detail = (body as { detail?: unknown } | null)?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    const first = detail[0] as { msg?: string } | undefined
    if (first?.msg) return first.msg
  }
  return `API 요청에 실패했습니다 (${status}).`
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = await accessToken()
  const isForm = init.body instanceof FormData
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: {
        Authorization: `Bearer ${token}`,
        ...(isForm || init.body === undefined ? {} : { 'Content-Type': 'application/json' }),
        ...(init.headers ?? {}),
      },
    })
  } catch {
    throw new ApiError(0, 'API 서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.')
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new ApiError(response.status, detailMessage(body, response.status))
  }
  const type = response.headers.get('content-type') ?? ''
  if (type.includes('application/json')) return response.json() as Promise<T>
  return response.blob() as unknown as Promise<T>
}

const json = (body: unknown) => JSON.stringify(body)
const qs = (params: Record<string, string | number | undefined>) => {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== '') search.set(key, String(value))
  }
  const text = search.toString()
  return text ? `?${text}` : ''
}

/* ---------- analysis & catalog ---------- */
export const loadAnalysisFilters = () => request<AnalysisFilters>('/api/v2/analysis-filters')

export const analyzeText = (input: AnalysisInput) =>
  request<AnalysisResult>('/api/v2/analyses', { method: 'POST', body: json(input) })

export const loadKeywords = (params: { offset?: number; limit?: number; q?: string; category?: string; risk?: string; evidence_type?: string }) =>
  request<KeywordPage>(`/api/v1/keywords${qs(params)}`)

/** Loads every catalog row in pages; rejects if the catalog revision changes mid-way. */
export async function loadAllKeywords(filters: { q?: string; category?: string; risk?: string; evidence_type?: string } = {}): Promise<KeywordPage> {
  const limit = 500
  const first = await loadKeywords({ ...filters, offset: 0, limit })
  const items = [...first.items]
  while (items.length < first.total) {
    const page = await loadKeywords({ ...filters, offset: items.length, limit })
    if (page.revision !== first.revision) throw new ApiError(409, '키워드 데이터가 바뀌었습니다. 다시 불러와 주세요.')
    if (!page.items.length) break
    items.push(...page.items)
  }
  return { total: first.total, revision: first.revision, columns: first.columns, items }
}

export const loadMatchingRules = () => request<MatchingRules>('/api/v2/matching-rules')

export const loadDropdownSettings = () => request<DropdownSettings>('/api/v1/dropdown-settings')

/* ---------- reports ---------- */
export const loadTopKeywords = (startDate: string, endDate: string, limit: number) =>
  request<{ items: TopKeyword[]; keyword_revision: number | null }>(
    `/api/v1/reports/top-keywords${qs({ start_date: startDate, end_date: endDate, limit })}`)

export const resetReport = (scope: 'all' | 'last-7-days') =>
  request<{ scope: string; reset?: boolean; removed?: number }>(`/api/v1/admin/reports/reset/${scope}`, { method: 'POST' })

/* ---------- regulation ---------- */
export type RegulationConversationMessage = { role: 'user' | 'assistant'; content: string }
export type RegulationScope = 'law' | 'internal' | 'keyword' | 'all'
export type RegulationDocument = { id: string; source_key: string; version: string; title: string; category: string; effective_from: string; effective_to: string | null; status: string; original_name: string; approved_at: string | null }
export type RegulationThread = { id: string; mode: string; created_at: string; updated_at: string }
export const askRegulation = (body: { direction: 'keyword_to_law' | 'law_to_keywords'; scope: RegulationScope; use_llm: boolean; include_keyword_candidates: boolean; thread_id: string | null; as_of: string; query: string; context_text: string; category: string; conversation_history: RegulationConversationMessage[] }) =>
  request<RegulationResult>('/api/v1/regulation/questions', { method: 'POST', body: json(body) })
export const askRegulationLegacy = (body: { direction: 'keyword_to_law' | 'law_to_keywords'; query: string; context_text: string; category: string; conversation_history: RegulationConversationMessage[] }) =>
  request<RegulationResult>('/api/v1/regulation/questions', { method: 'POST', body: json(body) })
export const loadRegulationUsage = () => request<RegulationUsageSummary>('/api/v1/regulation/usage')
export const listRegulationDocuments = () => request<{ items: RegulationDocument[] }>('/api/v1/admin/regulation/documents')
export const previewRegulationDocument = (id: string) => request<RegulationDocument & { chunks: { id: string; ordinal: number; content: string; embedding_model: string | null }[]; content_sha256: string }>(`/api/v1/admin/regulation/documents/${encodeURIComponent(id)}`)
export const uploadRegulationDocument = (fields: { source_key: string; version: string; title: string; category: string; effective_from: string; effective_to: string; file: File }) => {
  const form = new FormData()
  for (const [key, value] of Object.entries(fields)) form.append(key, value)
  return request<{ id: string; status: string }>('/api/v1/admin/regulation/documents', { method: 'POST', body: form })
}
export const approveRegulationDocument = (id: string) => request<{ id: string; status: string }>(`/api/v1/admin/regulation/documents/${encodeURIComponent(id)}/approve`, { method: 'POST' })
export const buildRegulationEmbeddings = (id: string) => request<{ id: string; embedded_chunks: number }>(`/api/v1/admin/regulation/documents/${encodeURIComponent(id)}/embeddings`, { method: 'POST' })
export const deleteRegulationDocument = (id: string) => request<{ id: string; deleted: boolean }>(`/api/v1/admin/regulation/documents/${encodeURIComponent(id)}`, { method: 'DELETE' })
export const listRegulationThreads = () => request<{ items: RegulationThread[] }>('/api/v1/regulation/threads')
export const loadRegulationThread = (id: string) => request<{ id: string; messages: { role: 'user' | 'assistant'; content: string; evidence: Record<string, unknown>[] }[] }>(`/api/v1/regulation/threads/${encodeURIComponent(id)}`)
export const deleteRegulationThread = (id: string) => request<{ id: string; deleted: boolean }>(`/api/v1/regulation/threads/${encodeURIComponent(id)}`, { method: 'DELETE' })

/* ---------- OCR ---------- */
export function extractOCR(files: File[]) {
  const form = new FormData()
  for (const file of files) form.append('files', file, file.name)
  return request<{ files: OCRFileResult[]; candidates: OCRCandidate[] }>('/api/v1/ocr/extract', { method: 'POST', body: form })
}

export const saveOCRKeywords = (revision: number, candidates: Pick<OCRCandidate, 'term' | 'category' | 'risk' | 'detail' | 'evidence' | 'alternative'>[]) =>
  request<{ added: string[]; revision: number }>('/api/v1/ocr/keywords', { method: 'POST', body: json({ revision, candidates }) })

/* ---------- unmatched candidates ---------- */
export const loadUnmatchedTerms = (offset: number, limit: number, search: string, sort: UnmatchedSort) =>
  request<UnmatchedPage>(`/api/v1/unmatched-terms${qs({ offset, limit, search, sort })}`)

export const exportUnmatchedTerms = () => request<{ items: UnmatchedTerm[] }>('/api/v1/unmatched-terms/export')

export const deleteUnmatchedTerms = (terms: string[]) =>
  request<{ deleted: number }>('/api/v1/admin/unmatched-terms/delete', { method: 'POST', body: json({ terms }) })

export const submitRegistrationRequests = (candidates: RegistrationCandidate[]) =>
  request<{ items: unknown[] }>('/api/v1/unmatched-terms/registration-requests', { method: 'POST', body: json({ candidates }) })

export const normalizeUnmatched = (candidates: { surface: string; occurrences: number }[]) =>
  request<{ items: NormalizationRecommendation[] }>('/api/v1/unmatched-terms/normalize', { method: 'POST', body: json({ candidates }) })

export const suggestKeyword = (term: string, category = '', context = '') =>
  request<import('./types.ts').KeywordSuggestion>('/api/v1/keyword-suggestions', {
    method: 'POST', body: json({ term, category, context }),
  })

export const loadRecommendationDraft = () =>
  request<{ payload: Record<string, unknown> | null }>('/api/v1/unmatched-terms/recommendation-draft')

export const saveRecommendationDraft = (payload: Record<string, unknown>) =>
  request<{ saved: boolean }>('/api/v1/unmatched-terms/recommendation-draft', { method: 'PUT', body: json({ payload }) })

export const loadRegistrationQueue = () =>
  request<{ items: UnmatchedRegistrationRequest[] }>('/api/v1/admin/unmatched-registration-requests')

export const rejectRegistrationRequests = (request_ids: string[]) =>
  request<{ rejected: number }>('/api/v1/admin/unmatched-registration-requests/reject', { method: 'POST', body: json({ request_ids }) })

export type CatalogRegistrationRow = {
  term: string; source_terms: string; term_norm: string; request_id: string | null
  category: string; risk: string; criteria: string; evidence_type: string; alternative: string
}

export const registerUnmatchedRows = (rows: CatalogRegistrationRow[]) =>
  request<{ added: string[]; cleared_requests: number; cleaned_terms: number; cleanup_error: string }>(
    '/api/v1/admin/unmatched-terms/register', { method: 'POST', body: json({ rows }) })

export const deleteRegistrationRequests = (request_ids: string[]) =>
  request<{ deleted: number }>('/api/v1/admin/unmatched-registration-requests/delete', { method: 'POST', body: json({ request_ids }) })

export const approveRegistrationRequests = (request_ids: string[], updates: (Omit<RegistrationCandidate, 'term' | 'source_terms' | 'occurrences'> & { request_id: string })[]) =>
  request<{ approved: number; added: string[]; cleared_requests: number }>(
    '/api/v1/admin/unmatched-registration-requests/approve', { method: 'POST', body: json({ request_ids, updates }) })

/* ---------- keyword inquiries ---------- */
export const loadKeywordRequests = () => request<{ items: KeywordRequestRecord[] }>('/api/v1/keyword-requests?limit=1000')

export const submitKeywordRequest = (body: { kwd_no: string; request_type: Exclude<KeywordRequestType, 'new_keyword_registration'>; request_detail: string }) =>
  request<KeywordRequestRecord & { notification: 'sent' | 'failed' | 'disabled'; notification_error: string }>(
    '/api/v1/keyword-requests', { method: 'POST', body: json(body) })

export const submitNewKeywordRequests = (terms: string[]) =>
  request<{ submitted: number }>('/api/v1/keyword-requests/new-keywords', { method: 'POST', body: json({ terms }) })

export const updateKeywordRequest = (id: string, status: string, admin_reply: string) =>
  request<KeywordRequestRecord>(`/api/v1/keyword-requests/${id}`, { method: 'PUT', body: json({ status, admin_reply }) })

export const deleteKeywordRequest = (id: string) =>
  request<unknown>(`/api/v1/keyword-requests/${id}`, { method: 'DELETE' })

export const loadRequestMessages = (id: string) =>
  request<{ items: KeywordRequestMessage[] }>(`/api/v1/keyword-requests/${id}/messages`)

export const addRequestMessage = (id: string, body: string, reply_to_id: string | null, status = '') =>
  request<unknown>(`/api/v1/keyword-requests/${id}/messages`, { method: 'POST', body: json({ body, reply_to_id, status }) })

export const editRequestMessage = (id: string, messageId: string, body: string, request_type?: KeywordRequestType) =>
  request<unknown>(`/api/v1/keyword-requests/${id}/messages/${messageId}`, { method: 'PUT', body: json({ body, request_type: request_type ?? null }) })

export const deleteRequestMessage = (id: string, messageId: string) =>
  request<unknown>(`/api/v1/keyword-requests/${id}/messages/${messageId}`, { method: 'DELETE' })

export const loadRequestNotifications = () =>
  request<{ enabled: boolean; configured: boolean }>('/api/v1/admin/keyword-request-notifications')

export const saveRequestNotifications = (enabled: boolean) =>
  request<{ enabled: boolean; configured: boolean }>('/api/v1/admin/keyword-request-notifications', { method: 'PUT', body: json({ enabled }) })

/* ---------- users ---------- */
export const loadAdminUsers = (page: number, per_page: number) =>
  request<{ items: AdminUser[]; has_more: boolean }>(`/api/v1/admin/users${qs({ page, per_page })}`)

export const setUserRole = (userId: string, role: Role, expected_role: Role | null) =>
  request<AdminUser>(`/api/v1/admin/users/${userId}/role`, { method: 'PUT', body: json({ role, expected_role }) })

/* ---------- keyword administration ---------- */
export const saveAdminKeywords = (revision: number, rows: KeywordRow[]) =>
  request<{ revision: number }>('/api/v1/admin/keywords', { method: 'PUT', body: json({ revision, rows }) })

export const deleteAdminKeywords = (revision: number, kwd_nos: string[]) =>
  request<{ deleted: number; revision: number }>('/api/v1/admin/keywords/delete', { method: 'POST', body: json({ revision, kwd_nos }) })

export function uploadAdminKeywords(file: File, mode: 'merge' | 'overwrite', revision: number) {
  const form = new FormData()
  form.append('file', file, file.name)
  form.append('mode', mode)
  form.append('revision', String(revision))
  return request<{ added_count: number; dedup_removed: number; revision: number; total: number }>(
    '/api/v1/admin/keywords/upload', { method: 'POST', body: form })
}

export const downloadKeywordTemplate = () => request<Blob>('/api/v1/admin/keywords/template.xlsx')

export const loadNormalizationSettings = () => request<NormalizationSettings>('/api/v1/admin/normalization-settings')

export const saveNormalizationSettings = (ignored_symbols: string[], extra_suffixes: string[]) =>
  request<{ ignored_symbols: string[]; extra_suffixes: string[] }>('/api/v1/admin/normalization-settings',
    { method: 'PUT', body: json({ ignored_symbols, extra_suffixes }) })

export const loadApprovedPartials = () =>
  request<{ keywords: { kwd_no: string; term: string }[]; rules: ApprovedPartialRules }>('/api/v1/admin/approved-partials')

export const saveApprovedPartials = (kwd_no: string, term: string, expected_expressions: string[], expressions: string[]) =>
  request<{ kwd_no: string; term: string; expressions: string[] }>('/api/v1/admin/approved-partials',
    { method: 'PUT', body: json({ kwd_no, term, expected_expressions, expressions }) })

export const loadAdminDropdownSettings = () => request<DropdownSettings>('/api/v1/admin/dropdown-settings')

export const saveAdminDropdownSettings = (settings: DropdownSettings) =>
  request<DropdownSettings>('/api/v1/admin/dropdown-settings', { method: 'PUT', body: json(settings) })
