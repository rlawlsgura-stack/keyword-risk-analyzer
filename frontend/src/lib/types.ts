export const DB_COLS = [
  'kwd_no', '키워드명', '상품카테고리', '리스크 등급', '대체키워드',
  '리스크 등급별 세부 심의기준', '증빙자료유형', '키워드 조회 수(누적카운트)', '마지막 출력일자',
] as const

export const COUNT_COL = '키워드 조회 수(누적카운트)'
export const LAST_COL = '마지막 출력일자'

export type KeywordRow = Record<string, string> & { kwd_no: string }

export type Role = 'admin' | 'member'

export type AnalysisMode = 'exact' | 'similar' | 'partial'

export type AnalysisInput = {
  analysis_id: string
  text: string
  mode: AnalysisMode
  strip_bracket_notes: boolean
  normalize_whitespace: boolean
  ignore_case: boolean
  normalize_symbols: boolean
  partial_min_len: number
  categories: string[]
  risks: string[]
}

export type Match = {
  term: string
  start: number
  end: number
  category: string
  risk: string
  detail: string
  kwd_no: string | null
  alternative: string
  evidence_type: string
  hit_count: string
  last_search_date: string
}

export type AnalysisResult = {
  analysis_id: string
  matches: Match[]
  unique_keywords: string[]
  unique_keyword_rows: KeywordRow[]
  keyword_revision: number | null
  catalog_revision: number | null
  unmatched_collection_pending: boolean
  offset_unit: 'unicode_codepoint'
  end_exclusive: boolean
  recorded: boolean
}

export type AnalysisFilters = { categories: string[]; risks: string[]; evidence_types: string[] }

export type KeywordPage = { total: number; revision: number | null; columns?: string[]; items: KeywordRow[] }

export type MatchingRules = { ignored_symbols: string[]; approved_partials: ApprovedPartialRules }

export type TopKeyword = {
  kwd_no: string
  hit_count: number
  term: string | null
  search_rank: number
  keyword_data: Record<string, string>
}

export type UnmatchedTerm = {
  term_norm: string
  display_term: string
  total_occurrences: number
  analysis_count: number
  first_seen: string
  last_seen: string
  review_status: string
}

export type UnmatchedPage = { total: number; rows: UnmatchedTerm[] }
export type UnmatchedSort = 'occurrences' | 'registered'

export type RegistrationCandidate = {
  term: string
  source_terms: string
  occurrences: number
  category: string
  risk: string
  criteria: string
  evidence_type: string
  alternative: string
}

export type NormalizationRecommendation = RegistrationCandidate & { recommendation_id?: string }

export type KeywordSuggestion = {
  status: 'suggested' | 'insufficient' | 'needs_category'
  term: string
  category: string
  risk: string
  criteria: string
  evidence_type: string
  alternative: string
  reason: string
  source_ids: string[]
  sources: { id: string; label: string; text: string; url?: string; document_id?: string; chunk_id?: string; version?: string }[]
  warnings: string[]
  category_options: {
    category: string
    risk: string
    criteria: string
    evidence_type: string
    alternative: string
    keyword: string
    source_id: string
    source_ids?: string[]
    reason?: string
    sources?: { id: string; label: string; text: string; url?: string; document_id?: string; chunk_id?: string; version?: string }[]
  }[]
}

export type UnmatchedRegistrationRequest = RegistrationCandidate & {
  id: string
  term_norm: string
  created_at: string
  requester_email?: string
}

export type KeywordRequestType = 'risk_grade_adjustment' | 'review_criteria_change' | 'new_keyword_registration'

export type KeywordRequestRecord = {
  id: string
  requester_id?: string
  requester_email?: string
  kwd_no: string
  keyword_name: string
  request_type: KeywordRequestType | string
  request_detail: string
  status: string
  admin_reply: string
  created_at: string
  updated_at?: string
  [key: string]: unknown
}

export type KeywordRequestMessage = {
  id: string
  request_id: string
  author_id: string | null
  author_email: string
  author_role: 'user' | 'admin'
  is_initial: boolean
  is_legacy: boolean
  reply_to_id: string | null
  body: string
  status: string
  created_at: string
  updated_at?: string
  [key: string]: unknown
}

export type AdminUser = { id: string; email: string; role: Role | null; email_confirmed: boolean; [key: string]: unknown }

export type DropdownSettings = {
  opt_categories: string[]
  opt_risks: string[]
  opt_details: string[]
  opt_evidences: string[]
  opt_alt_terms: string[]
}

export type NormalizationSettings = { ignored_symbols: string[]; extra_suffixes: string[]; default_suffix_count: number }

export type ApprovedPartialRules = Record<string, { term: string; expressions: string[] }>

export type OCRLine = { text: string; confidence: number; bbox: number[] | null }

export type OCRFileResult = {
  index: number
  name: string
  count: number
  error: string
  lines: OCRLine[]
  truncated?: boolean
  preview_data?: string | null
  image_width?: number
  image_height?: number
  preview_error?: string
}

export type OCRCandidate = {
  term: string
  confidence: number
  occurrences: number
  source_files: string[]
  category: string
  risk: string
  detail: string
  evidence: string
  alternative: string
  approved: boolean
  ai_suggestion?: KeywordSuggestion
}

export type RegulationSource = { label: string; url?: string; excerpt?: string; [key: string]: unknown }

export type RegulationResult = {
  answer: string
  sources: RegulationSource[]
  keyword_matches: Record<string, unknown>[]
  related_candidates?: { kwd_no: string; keyword: string; similarity: number }[]
  thread_id?: string
  administrator_review?: boolean
  recommendation_only?: boolean
  search_methods?: string[]
  llm_used?: boolean
  [key: string]: unknown
}
