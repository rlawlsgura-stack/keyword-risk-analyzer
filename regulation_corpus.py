"""Versioned private guidance corpus and evidence retrieval."""
from __future__ import annotations

import hashlib
import io
import logging
import math
import os
import re
import secrets
import unicodedata
from datetime import date
from urllib.parse import urlencode
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

import requests

from kiwi_runtime import get_kiwi, tokenization_lock
from openai_usage import record_usage, usage_event


MAX_DOCUMENT_BYTES = 50 * 1024 * 1024
MAX_DOCUMENT_CHARS = 250_000
EMBEDDING_MODEL = 'text-embedding-3-small'
logger = logging.getLogger(__name__)


def extract_text(filename: str, payload: bytes) -> str:
    if not payload or len(payload) > MAX_DOCUMENT_BYTES:
        raise ValueError('문서는 1바이트 이상 50MB 이하로 등록해 주세요.')
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
            def paragraph_text(paragraph):
                value = ''.join(node.text or '' for node in paragraph.iter(namespace + 't'))
                style = paragraph.find(f'{namespace}pPr/{namespace}pStyle')
                if style is not None:
                    heading = re.fullmatch(r'Heading([1-6])', style.get(namespace + 'val', ''), re.I)
                    if heading:
                        value = '#' * int(heading[1]) + ' ' + value
                return value

            paragraphs = []
            body = root.find(namespace + 'body')
            if body is None:
                raise ValueError('DOCX 본문을 읽을 수 없습니다.')
            for block in body:
                if block.tag == namespace + 'p':
                    paragraphs.append(paragraph_text(block))
                elif block.tag == namespace + 'tbl':
                    rows = [['\n'.join(paragraph_text(p) for p in cell.iter(namespace + 'p')).strip()
                              for cell in row.findall(namespace + 'tc')]
                            for row in block.findall(namespace + 'tr')]
                    if rows:
                        headers = rows[0]
                        paragraphs.extend('\n'.join(
                            f'{(headers[i] if i < len(headers) else "") or f"열 {i + 1}"}: {cell or "(빈 셀)"}'
                            for i, cell in enumerate(row))
                            for row in rows[1:])
                        if len(rows) == 1:
                            paragraphs.append(' | '.join(headers))
            text = '\n\n'.join(paragraphs)
        except (BadZipFile, KeyError, ElementTree.ParseError) as exc:
            raise ValueError('DOCX 본문을 읽을 수 없습니다.') from exc
    elif ext == 'pdf':
        from pypdf import PdfReader
        try:
            pages = PdfReader(io.BytesIO(payload)).pages
            if len(pages) > 200:
                raise ValueError('PDF는 200페이지 이하로 등록해 주세요.')
            text = '\n\n'.join(f'[원문 {index}쪽]\n{content}'
                               for index, page in enumerate(pages, 1)
                               if (content := (page.extract_text() or '').strip()))
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
    """Prefer whole paragraphs and sentences; never cut a normal clause at 1,500 chars."""
    parts = [part.strip() for part in re.split(
        r'\n\s*\n|(?=제\s*\d+(?:의\d+)?\s*조)|\n(?=#{1,6}\s)', text) if part.strip()]
    chunks: list[str] = []
    current = ''
    for part in parts:
        # A long paragraph remains intact up to 6,000 chars. Above that, prefer
        # sentence boundaries; only an oversized single sentence needs a hard cut.
        segments = [part] if len(part) <= 6000 else re.split(r'(?<=[.!?。])\s+|\n', part)
        for segment in (sentence[i:i + 6000] for sentence in segments
                        for i in range(0, len(sentence), 6000)):
            boundary = re.match(r'^(?:#{1,6}\s|제\s*\d+(?:의\d+)?\s*[장절조])', segment)
            qualification = re.match(r'^(?:다만|단[,，\s]|예외|제외|그러나|단서)', segment)
            heading_only = re.fullmatch(r'(?:#{1,6}\s[^\n]+|제\s*\d+(?:의\d+)?\s*[장절조][^\n]{0,100})', current)
            limit = 6000 if qualification or heading_only else 1500
            if current and (boundary or len(current) + len(segment) + 2 > limit):
                chunks.append(current)
                current = ''
            current = f'{current}\n\n{segment}'.strip() if current else segment
    if current:
        chunks.append(current)
    if len(chunks) > 300:
        raise ValueError('문서가 너무 길어 300개 이상의 검색 단위가 생성됩니다.')
    return chunks


def _neighbor_context(repository, rows: list[dict]) -> list[dict]:
    """Expand only within the already eligible version; keep every original chunk ID."""
    by_document: dict[str, list[dict]] = {}
    for row in rows:
        by_document.setdefault(row['document_id'], []).append(row)
    for document_id, hits in by_document.items():
        ordinals = sorted({i for row in hits for i in range(max(1, row['ordinal'] - 1), row['ordinal'] + 2)})
        try:
            neighbors = repository.request('GET', '/rest/v1/kra_regulation_chunks?' + urlencode({
                'select': 'id,ordinal,content', 'document_id': f'eq.{document_id}',
                'ordinal': 'in.(' + ','.join(map(str, ordinals)) + ')', 'order': 'ordinal.asc'})) or []
        except (requests.RequestException, RuntimeError):
            for row in hits:
                row['context_unavailable'] = True
            continue
        for row in hits:
            context = [item for item in neighbors if abs(item['ordinal'] - row['ordinal']) <= 1]
            if any(item['id'] == row['chunk_id'] for item in context):
                row['context_chunks'] = context
    return rows


def search_tokens(text: str) -> str:
    words = re.findall(r'[가-힣A-Za-z0-9]{2,}', text)
    try:
        with tokenization_lock:
            morphemes = get_kiwi().tokenize(text)
        words.extend([token.form for token in morphemes
                      if token.tag.startswith(('N', 'V', 'M', 'SL', 'SN'))
                      and len(token.form) >= 2])
    except (ImportError, RuntimeError):
        pass
    return ' '.join(dict.fromkeys(word.casefold() for word in words))


def _embed(texts: list[str], repository=None) -> list[list[float]] | None:
    if os.getenv('REGULATION_EMBEDDINGS_ENABLED', 'false').lower() != 'true':
        return None
    key = os.getenv('OPENAI_API_KEY', '').strip()
    if not key:
        raise RuntimeError('임베딩 사용 설정에는 OPENAI_API_KEY가 필요합니다.')
    # 2,000 Unicode characters have at most 8,000 UTF-8 bytes/tokens. Batches
    # of 32 stay below the API's 300,000-token aggregate limit as well.
    parts = [[text[i:i + 2000] for i in range(0, len(text), 2000)] for text in texts]
    if any(not pieces for pieces in parts):
        raise ValueError('임베딩할 본문이 비어 있습니다.')
    inputs = [part for pieces in parts for part in pieces]
    vectors = []
    for start in range(0, len(inputs), 32):
        response = requests.post('https://api.openai.com/v1/embeddings',
                                 headers={'Authorization': f'Bearer {key}'},
                                 json={'model': EMBEDDING_MODEL, 'input': inputs[start:start + 32]},
                                 timeout=60)
        response.raise_for_status()
        result = response.json()
        record_usage(repository, usage_event(EMBEDDING_MODEL, result.get('usage') or {}, embedding=True))
        batch = sorted(result['data'], key=lambda item: item['index'])
        if [item['index'] for item in batch] != list(range(len(inputs[start:start + 32]))):
            raise RuntimeError('임베딩 응답 개수가 일치하지 않습니다.')
        vectors.extend(item['embedding'] for item in batch)
    pooled, offset = [], 0
    for pieces in parts:
        group = vectors[offset:offset + len(pieces)]
        offset += len(pieces)
        if len(group) == 1:
            pooled.append(group[0])
            continue
        # ponytail: length-weighted pooling keeps long clauses intact without
        # a tokenizer dependency; validate semantic quality with reviewed cases.
        average = [sum(value * len(part) for value, part in zip(values, pieces))
                   for values in zip(*group, strict=True)]
        norm = math.sqrt(sum(value * value for value in average))
        if not norm:
            raise RuntimeError('유효한 임베딩 벡터를 생성하지 못했습니다.')
        pooled.append([value / norm for value in average])
    return pooled


def create_document(repository, *, source_key: str, version: str, title: str,
                    category: str, effective_from: date, effective_to: date | None,
                    filename: str, payload: bytes, actor_id: str, text: str | None = None) -> dict:
    text = extract_text(filename, payload) if text is None else text
    chunks = split_chunks(text)
    mime = {'txt': 'text/plain', 'md': 'text/markdown',
            'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'pdf': 'application/pdf'}[filename.lower().rsplit('.', 1)[-1]]
    storage_path = 'originals/' + secrets.token_hex(24)
    repository.upload_regulation_original(storage_path, payload, mime)
    try:
        result = repository.rpc('create_regulation_document_in_storage',
            p_source_key=source_key, p_version=version, p_title=title, p_category=category,
            p_effective_from=effective_from.isoformat(),
            p_effective_to=effective_to.isoformat() if effective_to else None,
            p_content_sha256=hashlib.sha256(payload).hexdigest(),
            p_original_name=filename[:200], p_storage_path=storage_path,
            p_mime_type=mime, p_created_by=actor_id,
            p_chunks=[{'ordinal': i + 1, 'content': chunk,
                       'search_tokens': search_tokens(chunk),
                       'embedding': None, 'embedding_model': None}
                      for i, chunk in enumerate(chunks)])
    except Exception:
        try:
            linked = repository.request('GET', '/rest/v1/kra_regulation_documents?'
                + urlencode({'select': 'id', 'storage_path': 'eq.' + storage_path, 'limit': '1'}))
            if not linked:
                repository.delete_regulation_original(storage_path)
        except Exception:
            logger.warning('Unlinked regulation original cleanup deferred', exc_info=True)
        raise
    try:
        repository.cleanup_regulation_originals()
    except Exception:
        logger.warning('Regulation original cleanup deferred', exc_info=True)
    return result


_DOCUMENT_FIELDS = 'id,source_key,version,title,category,status,content_sha256,effective_from,effective_to,original_name,approved_at'


def _find_documents(repository, column: str, value: str) -> list[dict]:
    return repository.request('GET', '/rest/v1/kra_regulation_documents?' + urlencode({
        'select': _DOCUMENT_FIELDS, column: f'eq.{value}', 'order': 'created_at.desc', 'limit': '200',
    })) or []


def document_versions(repository, source_key: str) -> list[dict]:
    return _find_documents(repository, 'source_key', source_key)


def documents_with_hash(repository, content_sha256: str) -> list[dict]:
    return _find_documents(repository, 'content_sha256', content_sha256)


def document_by_id(repository, document_id: str) -> dict | None:
    rows = _find_documents(repository, 'id', document_id)
    return rows[0] if rows else None


def _shingles(value: str) -> set[str]:
    value = ' '.join(unicodedata.normalize('NFKC', value).casefold().split())
    return {value[i:i + 5] for i in range(max(0, len(value) - 4))}


def _document_shingles(value: str) -> set[tuple[str, ...]]:
    words = re.findall(r'[가-힣a-z0-9]{2,}', unicodedata.normalize('NFKC', value).casefold())
    width = min(2, len(words))
    return {tuple(words[i:i + width]) for i in range(len(words) - width + 1)} if width else set()


def similar_document_candidates(repository, text: str) -> list[dict]:
    """Use existing lexical search to shortlist documents; similarity is advisory only."""
    chunks = split_chunks(text)
    samples = [chunks[i][:1500] for i in dict.fromkeys((0, len(chunks) // 2, len(chunks) - 1))]
    scores: dict[str, float] = {}
    for sample in samples:
        terms = [term for term in re.findall(r'[가-힣A-Za-z0-9]{2,}', sample)
                 if len(term) <= 32]
        if not terms:
            continue
        token = max(terms[:80], key=len).casefold()
        rows = repository.rpc('search_regulation_chunks', p_tokens=token,
            p_embedding=None, p_category='', p_as_of=date.today().isoformat(),
            p_limit=10, p_strategy='lexical') or []
        sample_shingles = _shingles(sample)
        for row in rows:
            other = _shingles(str(row['content'])[:1500])
            union = len(sample_shingles | other)
            score = len(sample_shingles & other) / union if union else 0.0
            key = str(row['document_id'])
            scores[key] = max(scores.get(key, 0.0), score)
    query_shingles = _document_shingles(text)
    candidates = []
    for document_id, _ in sorted(scores.items(), key=lambda item: item[1], reverse=True)[:8]:
        preview = load_document_preview(repository, document_id)
        if not preview:
            continue
        other = _document_shingles('\n'.join(chunk['content'] for chunk in preview['chunks']))
        union = len(query_shingles | other)
        similarity = len(query_shingles & other) / union if union else 0.0
        if similarity >= 0.25:
            document = {key: value for key, value in preview.items() if key != 'chunks'}
            candidates.append({'document': document, 'similarity': round(similarity, 3)})
    return sorted(candidates, key=lambda item: item['similarity'], reverse=True)[:5]


def list_documents(repository) -> list[dict]:
    return repository.request('GET', '/rest/v1/kra_regulation_documents?'
        'select=id,source_key,version,title,category,effective_from,effective_to,status,'
        'content_sha256,original_name,created_at,approved_at,created_by,approved_by'
        '&order=created_at.desc&limit=200') or []


def load_document_preview(repository, document_id: str) -> dict | None:
    doc_path = '/rest/v1/kra_regulation_documents?' + urlencode({
        'select': 'id,source_key,version,title,category,effective_from,effective_to,status,content_sha256,original_name,approved_at',
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
    # Keep the question in every window and cover the entire supplied context.
    queries = ([query] if len(query) <= 2000 else
               [query[:500] + '\n' + query[start:start + 1500]
                for start in range(500, len(query), 1500)])
    token_queries = [item if strategy == 'raw' else search_tokens(item) for item in queries]
    if not any(token_queries):
        return [], 'none'
    embedding_unavailable = False
    try:
        vectors = _embed(queries, repository) if strategy in {'hybrid', 'semantic'} else None
    except (requests.RequestException, RuntimeError, ValueError, KeyError):
        if strategy != 'hybrid':
            raise
        vectors = None
        embedding_unavailable = True
    ranked, scores = {}, {}
    for index, tokens in enumerate(token_queries):
        if not tokens:
            continue
        rows = repository.rpc('search_regulation_chunks',
            p_tokens=tokens, p_embedding=str(vectors[index]) if vectors else None,
            p_category=category, p_as_of=as_of.isoformat(), p_limit=5,
            p_strategy=strategy) or []
        for rank, row in enumerate(rows, 1):
            key = row['chunk_id']
            ranked.setdefault(key, row)
            scores[key] = scores.get(key, 0) + 1 / (60 + rank)
    rows = [ranked[key] for key in sorted(ranked, key=lambda key: -scores[key])[:5]]
    method = ('lexical_fuzzy_embedding_unavailable' if embedding_unavailable else
              'hybrid' if vectors and any(row.get('semantic_rank') is not None for row in rows)
              else 'lexical_fuzzy') if strategy == 'hybrid' else strategy
    return _neighbor_context(repository, rows), method


def save_turn(repository, thread_id: str | None, owner_id: str, mode: str,
              question: str, answer: str, sources: list[dict]) -> str:
    evidence = [{'id': source.get('id'), 'document_id': source.get('document_id'),
                 'chunk_id': source.get('chunk_id'),
                 'version': source.get('version'), 'content_sha256': source.get('content_sha256'),
                 'context_chunks': source.get('context_chunks'),
                 'reviewed_by_llm': source.get('reviewed_by_llm'),
                 'label': source.get('label'), 'text': str(source.get('text') or ''),
                 'url': source.get('url')}
                for source in sources]
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
