import { useEffect, useRef, useState, type FormEvent } from 'react'
import { approveRegulationDocument, buildRegulationEmbeddings, deleteRegulationDocument, listRegulationDocuments, previewRegulationDocument, uploadRegulationDocument, type RegulationDocument } from '../lib/api.ts'

export function RegulationDocuments() {
  const [documents, setDocuments] = useState<RegulationDocument[]>([])
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const [preview, setPreview] = useState<(RegulationDocument & { chunks: { id: string; ordinal: number; content: string; embedding_model: string | null }[]; content_sha256: string }) | null>(null)
  const [category, setCategory] = useState('')
  const [effectiveFrom, setEffectiveFrom] = useState('')
  const [effectiveTo, setEffectiveTo] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)
  const refresh = async () => {
    try { setDocuments((await listRegulationDocuments()).items); setError('') }
    catch (cause) { setError(cause instanceof Error ? cause.message : '문서 목록을 불러오지 못했습니다.') }
  }
  useEffect(() => { void refresh() }, [])

  const upload = async (event: FormEvent) => {
    event.preventDefault()
    if (!file || busy) return
    if (!category.trim()) { setError('상품 카테고리를 입력하세요. 공통 규정이면 "공통"을 입력하세요.'); return }
    setBusy(true)
    setNotice('')
    try {
      const result = await uploadRegulationDocument({ category: category.trim() === '공통' ? '' : category.trim(), effective_from: effectiveFrom, effective_to: effectiveTo, file })
      setFile(null)
      if (fileInput.current) fileInput.current.value = ''
      setEffectiveFrom('')
      setEffectiveTo('')
      setPreview(null)
      await refresh()
      setNotice(result.unchanged ? '동일한 내용의 문서가 이미 등록되어 있어 중복 등록하지 않았습니다.' : '새 초안을 등록했습니다. 본문을 확인한 뒤 승인하세요.')
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
  return <details className="regulation-documents"><summary>사내 규정 문서 관리 · 관리자</summary>
    <p>상품 카테고리와 파일을 등록하면 제목·식별자·버전이 자동 생성됩니다. 같은 파일명의 내용이 바뀌면 새 초안으로 교체되며, 승인 후 최신본이 검색에 사용됩니다.</p>
    <form className="regulation-document-form" onSubmit={upload}>
      <label>상품 카테고리<input required value={category} onChange={e => setCategory(e.target.value)} placeholder="예: 화장품 또는 공통" /></label>
      <label>문서 파일<input ref={fileInput} required type="file" accept=".txt,.md,.docx,.pdf" onChange={e => setFile(e.target.files?.[0] ?? null)} /></label>
      <button type="submit" disabled={busy || !file}>초안 등록</button>
      <details className="regulation-document-dates"><summary>적용 기간 설정 · 선택</summary>
        <label>시행일<input type="date" value={effectiveFrom} onChange={e => setEffectiveFrom(e.target.value)} /></label>
        <label>종료일<input type="date" value={effectiveTo} min={effectiveFrom || undefined} onChange={e => setEffectiveTo(e.target.value)} /></label>
        <span className="caption">시행일을 비우면 등록일을 적용합니다. 기존 승인본의 시행일이 미래라면 그 날짜를 사용합니다. 종료일을 비우면 기한 없이 검색됩니다.</span>
      </details>
    </form>
    <p className="caption regulation-document-help">의미 검색 색인은 관리자 기능입니다. 문서의 <strong>본문 확인</strong>을 누르면 해당 문서의 색인 버튼이 활성화됩니다. 생성하려면 API 서버에 <code>REGULATION_EMBEDDINGS_ENABLED=true</code>와 <code>OPENAI_API_KEY</code>가 설정되어 있어야 합니다. 승인된 문서의 색인은 질문과 의미가 비슷한 문단도 찾아줍니다.</p>
    <p className="caption">한 번에 파일 1개를 등록합니다. 파일당 최대 2MB이며, PDF는 200페이지 이하, 추출 본문은 250,000자, 검색 조각은 300개까지 가능합니다. 등록 문서 수 자체에는 앱 제한이 없지만 목록은 최신 200건까지 표시합니다.</p>
    {error && <div role="alert" className="chat-warning">{error}</div>}
    {notice && <div role="status" className="caption">{notice}</div>}
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
  </details>
}
