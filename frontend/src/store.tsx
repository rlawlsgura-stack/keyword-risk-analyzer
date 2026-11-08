import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from 'react'
import type { User } from '@supabase/supabase-js'
import { analyzeText, loadAllKeywords, loadDropdownSettings } from './lib/api.ts'
import { normalizeCatalog } from './lib/catalog.ts'
import type { AnalysisInput, DropdownSettings, KeywordRow, OCRCandidate, OCRFileResult, Role } from './lib/types.ts'

export const DEFAULT_SAMPLE = '이 문장에는 필러와 안티에이징이라는 키워드가 포함되어 있습니다.'

export type TabKey = 'analysis' | 'ocr_import' | 'candidate_pool' | 'requests' | 'regulation_chat' | 'report' | 'keyword_admin' | 'user_admin'

export type Catalog = { columns: string[]; rows: KeywordRow[]; revision: number | null; loadedAt: number }

export type OcrState = {
  files: File[]
  results: OCRFileResult[]
  candidates: OCRCandidate[]
  page: number
  version: number
}

type Store = {
  user: User
  role: Role
  isAdmin: boolean
  tab: TabKey
  setTab: (t: TabKey) => void
  catalog: Catalog | null
  catalogError: string
  reloadCatalog: () => Promise<Catalog | null>
  dropdowns: DropdownSettings | null
  reloadDropdowns: () => Promise<void>
  analysisText: string
  setAnalysisText: (t: string) => void
  autoRun: boolean
  setAutoRun: (v: boolean) => void
  ocr: OcrState
  setOcr: (fn: (s: OcrState) => OcrState) => void
  /** analysis_id → request body whose unmatched-term collection still has to be saved. */
  pending: Record<string, AnalysisInput>
  addPending: (input: AnalysisInput) => void
  retryPending: () => Promise<{ failed: number }>
  /** Bumped after any catalog write so screens refresh derived data. */
  catalogVersion: number
}

const Ctx = createContext<Store | null>(null)

export function useStore(): Store {
  const value = useContext(Ctx)
  if (!value) throw new Error('Store is not available')
  return value
}

export function StoreProvider({ user, role, children }: { user: User; role: Role; children: ReactNode }) {
  const [tab, setTab] = useState<TabKey>('analysis')
  const [catalog, setCatalog] = useState<Catalog | null>(null)
  const [catalogError, setCatalogError] = useState('')
  const [catalogVersion, setCatalogVersion] = useState(0)
  const [dropdowns, setDropdowns] = useState<DropdownSettings | null>(null)
  const [analysisText, setAnalysisText] = useState(DEFAULT_SAMPLE)
  const [autoRun, setAutoRun] = useState(false)
  const [ocr, setOcrState] = useState<OcrState>({ files: [], results: [], candidates: [], page: 0, version: 0 })
  const [pending, setPending] = useState<Record<string, AnalysisInput>>({})
  const loading = useRef<Promise<Catalog | null> | null>(null)

  const reloadCatalog = useCallback(async () => {
    if (loading.current) return loading.current
    const job = (async () => {
      try {
        const page = await loadAllKeywords()
        const rawColumns = page.items.length ? Object.keys(page.items[0]) : []
        const normalized = normalizeCatalog(page.columns ?? rawColumns, page.items)
        const next: Catalog = { ...normalized, revision: page.revision, loadedAt: Date.now() }
        setCatalog(next)
        setCatalogError('')
        setCatalogVersion(v => v + 1)
        return next
      } catch (error) {
        setCatalogError(error instanceof Error ? error.message : String(error))
        return null
      } finally {
        loading.current = null
      }
    })()
    loading.current = job
    return job
  }, [])

  const reloadDropdowns = useCallback(async () => {
    try { setDropdowns(await loadDropdownSettings()) } catch { /* keep previous values */ }
  }, [])

  const setOcr = useCallback((fn: (s: OcrState) => OcrState) => setOcrState(fn), [])

  const addPending = useCallback((input: AnalysisInput) => {
    setPending(p => ({ ...p, [input.analysis_id]: input }))
  }, [])

  const retryPending = useCallback(async () => {
    let failed = 0
    const remaining: Record<string, AnalysisInput> = {}
    for (const [id, input] of Object.entries(pending)) {
      try {
        // Re-sending the same analysis_id and payload re-runs only the idempotent
        // candidate collection; counts are not incremented again.
        const result = await analyzeText(input)
        if (result.unmatched_collection_pending) { failed++; remaining[id] = input }
      } catch {
        failed++
        remaining[id] = input
      }
    }
    setPending(remaining)
    return { failed }
  }, [pending])

  const value = useMemo<Store>(() => ({
    user, role, isAdmin: role === 'admin', tab, setTab, catalog, catalogError, reloadCatalog, dropdowns, reloadDropdowns,
    analysisText, setAnalysisText, autoRun, setAutoRun, ocr, setOcr, pending, addPending, retryPending, catalogVersion,
  }), [user, role, tab, catalog, catalogError, reloadCatalog, dropdowns, reloadDropdowns, analysisText, autoRun, ocr, setOcr,
    pending, addPending, retryPending, catalogVersion])

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}
