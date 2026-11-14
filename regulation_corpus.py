"""Versioned private guidance corpus and evidence retrieval."""
from __future__ import annotations

import base64
import hashlib
import io
import os
import re
from datetime import date
from urllib.parse import urlencode
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

import requests

from kiwi_runtime import get_kiwi, tokenization_lock
from openai_usage import record_usage, usage_event


MAX_DOCUMENT_BYTES = 2 * 1024 * 1024
MAX_DOCUMENT_CHARS = 250_000
EMBEDDING_MODEL = 'text-embedding-3-small'


def extract_text(filename: str, payload: bytes) -> str:
    if not payload or len(payload) > MAX_DOCUMENT_BYTES:
        raise ValueError('문서는 1바이트 이상 2MB 이하로 등록해 주세요.')
    ext = filename.lower().rsplit('.', 1)[-1]
    if ext in {'txt', 'md'}:
        try:
            text = payload.decode('utf-8-sig')
        except UnicodeDecodeError as exc:
            raise ValueError('텍스트 파일은 UTF-8로 저장해 주세요.') from exc
    elif ext == 'docx':
        try:
            with ZipFile(io.BytesIO(payload)) as archive:
                if archive.getinfo('word/document.xml').file_size > 2 * MAX_DOCUMENT_BYTES:
                    raise ValueError('DOCX 본문이 너무 큽니다.')
                xml = archive.read('word/document.xml')
            root = ElementTree.fromstring(xml)
            namespace = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
            paragraphs = []
            for paragraph in root.iter(namespace + 'p'):
                paragraphs.append(''.join(node.text or '' for node in paragraph.iter(namespace + 't')))
            text = '\n'.join(paragraphs)
        except (BadZipFile, KeyError, ElementTree.ParseError) as exc:
            raise ValueError('DOCX 본문을 읽을 수 없습니다.') from exc
    elif ext == 'pdf':
        from pypdf import PdfReader
        try:
            pages = PdfReader(io.BytesIO(payload)).pages
            if len(pages) > 200:
                raise ValueError('PDF는 200페이지 이하로 등록해 주세요.')
            text = '\n\n'.join(page.extract_text() or '' for page in pages)
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError('PDF 본문을 읽을 수 없습니다.') from exc
    else:
        raise ValueError('TXT, MD, DOCX, PDF 파일만 등록할 수 있습니다.')
    text = text.replace('\x00', '').strip()
    if len(text) < 20 or len(text) > MAX_DOCUMENT_CHARS:
        raise ValueError('검색 가능한 본문은 20~250,000자여야 합니다. 이미지 PDF는 텍스트 변환 후 등록해 주세요.')
    return text


def split_chunks(text: str) -> list[str]:
    """Keep paragraphs together and retain headings next to the following provision."""
    parts = [part.strip() for part in re.split(r'\n\s*\n|(?=제\s*\d+(?:의\d+)?\s*조)', text) if part.strip()]
    chunks: list[str] = []
    current = ''
    for part in parts:
        for segment in (part[i:i + 1500] for i in range(0, len(part), 1500)):
            if current and len(current) + len(segment) + 2 > 1500:
                chunks.append(current)
                current = ''
            current = f'{current}\n\n{segment}'.strip() if current else segment
    if current:
        chunks.append(current)
    if len(chunks) > 300:
        raise ValueError('문서가 너무 길어 300개 이상의 검색 단위가 생성됩니다.')
    return chunks


def search_tokens(text: str) -> str:
    words = re.findall(r'[가-힣A-Za-z0-9]{2,}', text)[:160]
    try:
        with tokenization_lock:
            morphemes = get_kiwi().tokenize(text)
        words.extend([token.form for token in morphemes
                      if token.tag.startswith(('N', 'V', 'M', 'SL', 'SN'))
                      and len(token.form) >= 2][:160])
    except (ImportError, RuntimeError):
        pass
    return ' '.join(dict.fromkeys(word.casefold() for word in words))


def _embed(texts: list[str], repository=None) -> list[list[float]] | None:
    if os.getenv('REGULATION_EMBEDDINGS_ENABLED', 'false').lower() != 'true':
        return None
    key = os.getenv('OPENAI_API_KEY', '').strip()
    if not key:
        raise RuntimeError('임베딩 사용 설정에는 OPENAI_API_KEY가 필요합니다.')
    vectors = []
    for start in range(0, len(texts), 50):
        response = requests.post('https://api.openai.com/v1/embeddings',
                                 headers={'Authorization': f'Bearer {key}'},
                                 json={'model': EMBEDDING_MODEL, 'input': texts[start:start + 50]},
                                 timeout=60)
        response.raise_for_status()
        result = response.json()
        record_usage(repository, usage_event(EMBEDDING_MODEL, result.get('usage') or {}, embedding=True))
        batch = sorted(result['data'], key=lambda item: item['index'])
        if len(batch) != len(texts[start:start + 50]):
            raise RuntimeError('임베딩 응답 개수가 일치하지 않습니다.')
        vectors.extend(item['embedding'] for item in batch)
    return vectors


def create_document(repository, *, source_key: str, version: str, title: str,
                    category: str, effective_from: date, effective_to: date | None,
                    filename: str, payload: bytes, actor_id: str) -> dict:
    text = extract_text(filename, payload)
    chunks = split_chunks(text)
    vectors = _embed(chunks, repository)
    mime = {'txt': 'text/plain', 'md': 'text/markdown',
            'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'pdf': 'application/pdf'}[filename.lower().rsplit('.', 1)[-1]]
    return repository.rpc('create_regulation_document',
        p_source_key=source_key, p_version=version, p_title=title, p_category=category,
        p_effective_from=effective_from.isoformat(),
        p_effective_to=effective_to.isoformat() if effective_to else None,
        p_content_sha256=hashlib.sha256(payload).hexdigest(),
        p_original_name=filename[:200], p_original_base64=base64.b64encode(payload).decode('ascii'),
        p_mime_type=mime, p_created_by=actor_id,
        p_chunks=[{'ordinal': i + 1, 'content': chunk,
                   'search_tokens': search_tokens(chunk),
                   'embedding': vectors[i] if vectors else None,
                   'embedding_model': EMBEDDING_MODEL if vectors else None}
                  for i, chunk in enumerate(chunks)])


def existing_document_versions(repository, source_key: str, filename: str) -> tuple[str, list[dict]]:
    """Match uploads by stable filename, including documents registered before auto metadata."""
    fields = 'id,source_key,version,category,status,content_sha256,effective_from,effective_to,original_name'
    def find(column: str, value: str) -> list[dict]:
        return repository.request('GET', '/rest/v1/kra_regulation_documents?' + urlencode({
            'select': fields, column: f'eq.{value}', 'order': 'created_at.desc', 'limit': '200',
        })) or []

    versions = list({row['id']: row for row in
                     find('source_key', source_key) + find('original_name', filename)}.values())
    keys = {row['source_key'] for row in versions}
    if len(keys) > 1:
        raise ValueError('같은 파일명으로 여러 문서가 등록되어 있습니다. 파일명을 구분해 다시 업로드하세요.')
    return (next(iter(keys)) if keys else source_key), versions


def list_documents(repository) -> list[dict]:
    return repository.request('GET', '/rest/v1/kra_regulation_documents?'
        'select=id,source_key,version,title,category,effective_from,effective_to,status,'
        'content_sha256,original_name,created_at,approved_at,created_by,approved_by'
        '&order=created_at.desc&limit=200') or []


def load_document_preview(repository, document_id: str) -> dict | None:
    doc_path = '/rest/v1/kra_regulation_documents?' + urlencode({
        'select': 'id,source_key,version,title,category,effective_from,effective_to,status,content_sha256,original_name',
        'id': f'eq.{document_id}', 'limit': '1'})
    documents = repository.request('GET', doc_path) or []
    if not documents:
        return None
    chunk_path = '/rest/v1/kra_regulation_chunks?' + urlencode({
        'select': 'id,ordinal,content,embedding_model', 'document_id': f'eq.{document_id}',
        'order': 'ordinal.asc', 'limit': '300'})
    return {**documents[0], 'chunks': repository.request('GET', chunk_path) or []}


def reindex_embeddings(repository, document_id: str) -> int:
    document = load_document_preview(repository, document_id)
    if document is None:
        raise ValueError('문서를 찾을 수 없습니다.')
    vectors = _embed([chunk['content'] for chunk in document['chunks']], repository)
    if vectors is None:
        raise RuntimeError('임베딩을 사용하려면 서버에서 REGULATION_EMBEDDINGS_ENABLED=true를 설정하세요.')
    return repository.rpc('set_regulation_embeddings', p_document_id=document_id,
                          p_model=EMBEDDING_MODEL,
                          p_vectors=[{'ordinal': chunk['ordinal'], 'embedding': vectors[index]}
                                     for index, chunk in enumerate(document['chunks'])])


def search_documents(repository, query: str, category: str, as_of: date,
                     strategy: str = 'hybrid') -> tuple[list[dict], str]:
    tokens = query if strategy == 'raw' else search_tokens(query)
    if not tokens:
        return [], 'none'
    embedding_unavailable = False
    try:
        vectors = _embed([query], repository) if strategy in {'hybrid', 'semantic'} else None
    except (requests.RequestException, RuntimeError, ValueError, KeyError):
        if strategy != 'hybrid':
            raise
        vectors = None
        embedding_unavailable = True
    rows = repository.rpc('search_regulation_chunks',
        p_tokens=tokens, p_embedding=str(vectors[0]) if vectors else None,
        p_category=category, p_as_of=as_of.isoformat(), p_limit=5,
        p_strategy=strategy) or []
    method = ('lexical_fuzzy_embedding_unavailable' if embedding_unavailable else
              'hybrid' if vectors and any(row.get('semantic_rank') is not None for row in rows)
              else 'lexical_fuzzy') if strategy == 'hybrid' else strategy
    return rows, method


def save_turn(repository, thread_id: str | None, owner_id: str, mode: str,
              question: str, answer: str, sources: list[dict]) -> str:
    evidence = [{'id': source.get('id'), 'document_id': source.get('document_id'),
                 'chunk_id': source.get('chunk_id'),
                 'version': source.get('version'), 'content_sha256': source.get('content_sha256'),
                 'label': source.get('label'), 'text': str(source.get('text') or '')[:3000],
                 'url': source.get('url')}
                for source in sources[:10]]
    return repository.rpc('save_regulation_turn', p_thread_id=thread_id,
                          p_owner_id=owner_id, p_mode=mode, p_question=question,
                          p_answer=answer, p_evidence=evidence)


def list_threads(repository, owner_id: str) -> list[dict]:
    path = '/rest/v1/kra_regulation_threads?' + urlencode({
        'select': 'id,mode,created_at,updated_at', 'owner_id': f'eq.{owner_id}',
        'order': 'updated_at.desc', 'limit': '50'})
    return repository.request('GET', path) or []


def load_thread(repository, owner_id: str, thread_id: str) -> list[dict] | None:
    path = '/rest/v1/kra_regulation_threads?' + urlencode({
        'select': 'id', 'owner_id': f'eq.{owner_id}', 'id': f'eq.{thread_id}', 'limit': '1'})
    if not repository.request('GET', path):
        return None
    messages_path = '/rest/v1/kra_regulation_messages?' + urlencode({
        'select': 'id,role,content,evidence,created_at', 'thread_id': f'eq.{thread_id}',
        'order': 'id.asc', 'limit': '200'})
    return repository.request('GET', messages_path) or []


def delete_thread(repository, owner_id: str, thread_id: str) -> bool:
    path = '/rest/v1/kra_regulation_threads?' + urlencode({
        'id': f'eq.{thread_id}', 'owner_id': f'eq.{owner_id}', 'select': 'id'})
    return bool(repository.request('DELETE', path, prefer='return=representation'))
