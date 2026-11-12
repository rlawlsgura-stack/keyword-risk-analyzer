import { useEffect, useState, type FormEvent } from 'react'
import { approveRegulationDocument, buildRegulationEmbeddings, deleteRegulationDocument, listRegulationDocuments, previewRegulationDocument, uploadRegulationDocument, type RegulationDocument } from '../lib/api.ts'

export function RegulationDocuments() {
  const [documents, setDocuments] = useState<RegulationDocument[]>([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [preview, setPreview] = useState<(RegulationDocument & { chunks: { id: string; ordinal: number; content: string; embedding_model: string | null }[]; content_sha256: string }) | null>(null)
  const [sourceKey, setSourceKey] = useState('')
  const [version, setVersion] = useState('')
  const [title, setTitle] = useState('')
  const [category, setCategory] = useState('')
  const [effectiveFrom, setEffectiveFrom] = useState(new Date().toISOString().slice(0, 10))
  const [effectiveTo, setEffectiveTo] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const refresh = async () => {
    try { setDocuments((await listRegulationDocuments()).items); setError('') }
    catch (cause) { setError(cause instanceof Error ? cause.message : '문서 목록을 불러오지 못했습니다.') }
  }
  useEffect(() => { void refresh() }, [])

  const upload = async (event: FormEvent) => {
    event.preventDefault()
    if (!file || busy) return
    setBusy(true)
    try {
      await uploadRegulationDocument({ source_key: sourceKey, version, title, category, effective_from: effectiveFrom, effective_to: effectiveTo, file })
      setFile(null)
      setPreview(null)
      await refresh()
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
    <p>등록한 문서는 초안으로 저장됩니다. 본문과 시행일을 확인한 뒤 승인하면 검색에 사용됩니다. 같은 식별자의 이전 승인본은 교체됩니다.</p>
    <form className="regulation-document-form" onSubmit={upload}>
      <label>문서 식별자<input required pattern="[a-z0-9_-]{2,80}" value={sourceKey} onChange={e => setSourceKey(e.target.value)} placeholder="예: cosmetics-ad-guideline" /></label>
      <label>버전<input required value={version} onChange={e => setVersion(e.target.value)} placeholder="예: 2026-11" /></label>
      <label>제목<input required value={title} onChange={e => setTitle(e.target.value)} /></label>
      <label>상품 카테고리<input value={category} onChange={e => setCategory(e.target.value)} placeholder="빈칸이면 공통" /></label>
      <label>시행일<input required type="date" value={effectiveFrom} onChange={e => setEffectiveFrom(e.target.value)} /></label>
      <label>종료일<input type="date" value={effectiveTo} min={effectiveFrom} onChange={e => setEffectiveTo(e.target.value)} /></label>
      <label>문서 파일<input required type="file" accept=".txt,.md,.docx,.pdf" onChange={e => setFile(e.target.files?.[0] ?? null)} /></label>
      <button type="submit" disabled={busy || !file}>초안 등록</button>
    </form>
    <p className="caption">한 번에 파일 1개를 등록합니다. 파일당 최대 2MB이며, PDF는 200페이지 이하, 추출 본문은 250,000자, 검색 조각은 300개까지 가능합니다. 등록 문서 수 자체에는 앱 제한이 없지만 목록은 최신 200건까지 표시합니다.</p>
    {error && <div role="alert" className="chat-warning">{error}</div>}
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
