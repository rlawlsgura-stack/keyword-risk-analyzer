import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Dialog, Help } from '../components/ui.tsx'
import { approveRegulationDocument, buildRegulationEmbeddings, deleteRegulationDocument, listRegulationDocuments, matchRegulationDocument, previewRegulationDocument, uploadRegulationDocument, type RegulationDocument } from '../lib/api.ts'
import { koSorted, uniqueValues } from '../lib/catalog.ts'
import { useStore } from '../store.tsx'

type DocumentMatches = Awaited<ReturnType<typeof matchRegulationDocument>>

function DocumentManagementHelp() {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    if (!open) return
    const closeOutside = (event: PointerEvent) => {
      if (!ref.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('pointerdown', closeOutside)
    return () => document.removeEventListener('pointerdown', closeOutside)
  }, [open])
  return <button ref={ref} type="button" className="regulation-management-help" aria-label="사내 규정 문서 검색 대상 도움말"
    aria-expanded={open} onClick={event => { event.preventDefault(); event.stopPropagation(); setOpen(value => !value) }}
    onKeyDown={event => event.stopPropagation()}>
    <span aria-hidden>?</span>
    <span className={`regulation-management-tooltip${open ? ' open' : ''}`} role="tooltip">
      <strong>적용 기간과 검색 대상 안내</strong>
      <span><b>어떤 문서가 검색되나요?</b> 선택한 기준일이 문서의 시행일과 종료일 사이에 있고, 상태가 승인 또는 이전 버전이며, 카테고리가 맞는 문서가 검색 후보입니다. 종료일이 비어 있으면 종료일 제한 없이 적용 중인 것으로 봅니다. 초안은 검색하지 않습니다.</span>
      <span><b>버전은 어떻게 선택하나요?</b> 같은 문서의 버전이 여러 개면 기준일에 실제 적용 중인 버전을 찾습니다. 새 버전이 시행되기 전 날짜에는 그때 유효했던 이전 버전이 선택될 수 있습니다. 기준일에 적용 기간이 겹치면 시행일이 더 늦은 버전이 우선하며, 시행일도 같으면 승인 시각이 더 늦은 버전이 우선합니다.</span>
      <span><b>예시:</b> 1판의 적용 기간이 1월 1일~6월 30일이고 2판이 7월 1일부터 시행된다면, 5월 20일 기준 검색은 1판을 사용하고 8월 10일 기준 검색은 2판을 사용합니다. 아직 승인되지 않은 3판 초안은 어느 날짜에서도 검색 후보가 아닙니다.</span>
      <span><b>본문 확인·의미 검색 색인:</b> 본문 확인은 내용을 미리 보는 기능입니다. 의미 검색 색인은 선택한 문서에 의미 검색용 자료를 만드는 기능입니다. 둘 다 검색 대상 문서를 지정하지는 않습니다. 실제 검색은 조건에 맞는 문서들을 대상으로 관련 문단을 찾고, 그중 최대 5개를 보여줍니다.</span>
    </span>
  </button>
}

export function RegulationDocuments() {
  const { catalog, dropdowns } = useStore()
  const [documents, setDocuments] = useState<RegulationDocument[]>([])
  const [documentListOpen, setDocumentListOpen] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const [preview, setPreview] = useState<(RegulationDocument & { chunks: { id: string; ordinal: number; content: string; embedding_model: string | null }[]; content_sha256: string }) | null>(null)
  const [category, setCategory] = useState('')
  const [effectiveFrom, setEffectiveFrom] = useState('')
  const [effectiveTo, setEffectiveTo] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [matches, setMatches] = useState<DocumentMatches | null>(null)
  const [matching, setMatching] = useState(false)
  const [replacementChoice, setReplacementChoice] = useState('')
  const fileInput = useRef<HTMLInputElement>(null)
  const matchRequest = useRef(0)
  const refresh = async () => {
    try { setDocuments((await listRegulationDocuments()).items); setError('') }
    catch (cause) { setError(cause instanceof Error ? cause.message : '문서 목록을 불러오지 못했습니다.') }
  }
  useEffect(() => { void refresh() }, [])

  const inspectFile = async (selected: File | null) => {
    const requestId = ++matchRequest.current
    setFile(selected)
    setMatches(null)
    setReplacementChoice('')
    setError('')
    if (!selected) { setMatching(false); return }
    setMatching(true)
    try {
      const result = await matchRegulationDocument(selected)
      if (requestId !== matchRequest.current) return
      setMatches(result)
      const keys = new Set(result.exact.map(doc => doc.source_key))
      setReplacementChoice(result.exact.length && keys.size === 1 ? result.exact[0].id
        : result.exact.length || result.candidates.length ? '' : 'new')
    } catch (cause) {
      if (requestId === matchRequest.current) setError(cause instanceof Error ? cause.message : '문서 내용을 검사하지 못했습니다.')
    } finally {
      if (requestId === matchRequest.current) setMatching(false)
    }
  }

  const upload = async (event: FormEvent) => {
    event.preventDefault()
    if (!file || busy || matching || !matches || !replacementChoice) return
    if (!category) { setError('상품 카테고리를 선택하세요. 공통 규정이면 "공통"을 선택하세요.'); return }
    setBusy(true)
    setNotice('')
    try {
      const result = await uploadRegulationDocument({ category: category.trim() === '공통' ? '' : category.trim(), effective_from: effectiveFrom, effective_to: effectiveTo, replace_document_id: replacementChoice === 'new' ? '' : replacementChoice, new_document: String(replacementChoice === 'new'), file })
      setFile(null)
      setMatches(null)
      setReplacementChoice('')
      if (fileInput.current) fileInput.current.value = ''
      setEffectiveFrom('')
      setEffectiveTo('')
      setPreview(null)
      await refresh()
      setNotice(result.unchanged ? '동일한 내용의 문서가 이미 등록되어 있어 중복 등록하지 않았습니다.' : '새 초안을 등록했습니다. 첨부파일 목록보기 버튼을 클릭하여 본문을 확인한 뒤 문서를 승인하세요.')
    } catch (cause) { setError(cause instanceof Error ? cause.message : '문서를 등록하지 못했습니다.') }
    finally { setBusy(false) }
  }
  const approve = async (id: string) => {
    if (busy) return
    setBusy(true)
    try { await approveRegulationDocument(id); setPreview(null); await refresh() }
    catch (cause) { setError(cause instanceof Error ? cause.message : '문서를 승인하지 못했습니다.') }
    finally { setBusy(false) }
  }
  const showPreview = async (id: string) => {
    try { setPreview(await previewRegulationDocument(id)); setError('') }
    catch (cause) { setError(cause instanceof Error ? cause.message : '본문을 불러오지 못했습니다.') }
  }
  const buildEmbeddings = async (id: string) => {
    setBusy(true)
    try { await buildRegulationEmbeddings(id); await showPreview(id) }
    catch (cause) { setError(cause instanceof Error ? cause.message : '임베딩을 만들지 못했습니다.') }
    finally { setBusy(false) }
  }
  const removeDocument = async (doc: RegulationDocument) => {
    if (!window.confirm(`'${doc.title}' 문서와 첨부 원본, 검색 인덱스를 영구 삭제할까요? 이 문서는 검색에 더 이상 사용되지 않습니다.`)) return
    setBusy(true)
    try { await deleteRegulationDocument(doc.id); setPreview(null); await refresh() }
    catch (cause) { setError(cause instanceof Error ? cause.message : '문서를 삭제하지 못했습니다.') }
    finally { setBusy(false) }
  }
  const suggestedIds = new Set([...(matches?.exact.map(doc => doc.id) ?? []),
    ...(matches?.candidates.map(candidate => candidate.document.id) ?? [])])
  const categoryOptions = koSorted(new Set([
    ...(dropdowns?.opt_categories ?? []),
    ...uniqueValues(catalog?.rows ?? [], '상품카테고리'),
  ].map(value => value.trim()).filter(value => value && value !== '공통')))
  return <details className="regulation-documents"><summary className="chat-control-title">사내 규정 문서 관리 · 관리자</summary>
    <p>상품 카테고리와 파일을 등록하면 제목·식별자·버전이 자동 생성됩니다. 파일 내용으로 동일 문서와 유사한 기존 문서를 찾고, 수정본은 관리자가 연결할 문서를 선택합니다.</p>
    <form className="regulation-document-form" onSubmit={upload}>
      <label>상품 카테고리<select required disabled={busy} value={category} onChange={e => setCategory(e.target.value)}>
        <option value="">상품 카테고리 선택</option>
        <option value="공통">공통</option>
        {categoryOptions.map(value => <option key={value} value={value}>{value}</option>)}
      </select></label>
      <label>문서 파일<input ref={fileInput} required disabled={busy} type="file" accept=".txt,.md,.docx,.pdf" onChange={e => void inspectFile(e.target.files?.[0] ?? null)} /></label>
      <button type="submit" disabled={busy || matching || !file || !matches || !replacementChoice}>초안 등록</button>
      {matching && <span className="caption regulation-document-match">파일 내용을 비교하고 있습니다.</span>}
      {file && !matching && !matches && <button type="button" onClick={() => void inspectFile(file)}>파일 검사 다시 시도</button>}
      {matches && <label className="regulation-document-match">기존 문서 연결
        <select value={replacementChoice} onChange={e => setReplacementChoice(e.target.value)} required disabled={busy}>
          <option value="">연결 방식을 선택하세요</option>
          <option value="new">새 문서로 등록</option>
          {matches.exact.map(doc => <option key={doc.id} value={doc.id}>완전 동일 · {doc.title} · {doc.category || '공통'}</option>)}
          {matches.candidates.map(({ document: doc, similarity }) => <option key={doc.id} value={doc.id}>유사 후보 {Math.round(similarity * 100)}% · {doc.title} · {doc.category || '공통'}</option>)}
          {documents.filter(doc => doc.status !== 'superseded' && !suggestedIds.has(doc.id)).map(doc =>
            <option key={doc.id} value={doc.id}>기존 문서 · {doc.title} · {doc.category || '공통'}</option>)}
        </select>
        <span className="caption">유사 후보는 참고용입니다. 수정본이라면 기존 문서를 선택하고, 별도 문서라면 새 문서로 등록하세요.</span>
      </label>}
      <details className="regulation-document-dates"><summary>적용 기간 설정 · 선택<DocumentManagementHelp /></summary>
        <label>시행일<input type="date" value={effectiveFrom} onChange={e => setEffectiveFrom(e.target.value)} /></label>
        <label>종료일<input type="date" value={effectiveTo} min={effectiveFrom || undefined} onChange={e => setEffectiveTo(e.target.value)} /></label>
      </details>
    </form>
    <p className="caption">한 번에 파일 1개를 등록합니다. 원본은 비공개 파일 저장소에 보관하며 파일당 최대 50MB입니다. PDF는 200페이지 이하, 추출 본문은 250,000자, 검색 조각은 300개까지 가능합니다. 등록 문서 수 자체에는 앱 제한이 없지만 목록은 최신 200건까지 표시합니다.</p>
    {error && <div role="alert" className="chat-warning">{error}</div>}
    {notice && <div role="status" className="regulation-document-notice">{notice}</div>}
    <button type="button" className="btn small regulation-document-list-open" onClick={() => setDocumentListOpen(true)}>첨부파일 목록 보기 ({documents.length})</button>
    {documentListOpen && <Dialog title={<>{`첨부파일 목록 · ${documents.length}개`}<Help text="의미 검색 색인은 관리자 기능입니다. 문서의 본문 확인을 누르면 해당 문서의 색인 버튼이 활성화됩니다. 승인된 문서의 색인은 질문과 의미가 비슷한 문단도 찾아줍니다." /></>} onClose={() => setDocumentListOpen(false)} wide>
    <div className="regulation-document-list">{documents.map(doc => <div key={doc.id}>
      <strong>{doc.title}</strong> · {doc.source_key} · v{doc.version} · {doc.status === 'approved' ? '승인' : doc.status === 'draft' ? '초안' : '이전 버전'} · 시행 {doc.effective_from}
      <button type="button" onClick={() => void showPreview(doc.id)}>본문 확인</button>
      <button type="button" disabled={busy || preview?.id !== doc.id} onClick={() => void buildEmbeddings(doc.id)}>의미 검색 색인 생성</button>
      {doc.status === 'draft' && <button type="button" disabled={busy || preview?.id !== doc.id} onClick={() => void approve(doc.id)}>승인</button>}
      <button type="button" disabled={busy} onClick={() => void removeDocument(doc)}>문서 삭제</button>
    </div>)}</div>
    {preview && <div className="regulation-document-preview"><strong>{preview.title} · v{preview.version} · 시행 {preview.effective_from} · {preview.category || '공통'}</strong>
      <p>원본: {preview.original_name} · SHA-256: {preview.content_sha256}</p>
      {preview.chunks.map(chunk => <pre key={chunk.id}>{chunk.ordinal}. {chunk.content}</pre>)}
    </div>}
    </Dialog>}
   </details>
}
