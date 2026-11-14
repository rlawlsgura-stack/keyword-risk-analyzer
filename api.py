"""Run: python -m uvicorn api:app --host 0.0.0.0 --port 8000"""
import os
import hashlib
import secrets
import logging
import re
import unicodedata
from threading import Lock
from typing import Literal
from uuid import UUID

import requests
from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.concurrency import run_in_threadpool

from app_config import configure, cloud_enabled
from repository import COUNT_COL, LAST_COL, ConflictError, StorageError, SupabaseRepository
from service import analyze, analyze_current, load_matching_config
from matching_engine import DB_COLS, MatchingConfig, _KO_SUFFIX_WHITELIST
from regulation_assistant import RegulationSearchError, answer_regulation_question
from openai_usage import current_month_start, monthly_budget, record_usage
from keyword_suggestion import SuggestionProviderError, suggest_keyword
from regulation_corpus import (MAX_DOCUMENT_BYTES, create_document, list_documents,
                               document_by_id, document_versions, documents_with_hash,
                               extract_text, similar_document_candidates, load_document_preview,
                               list_threads, load_thread, delete_thread,
                               reindex_embeddings, save_turn)

configure()
app = FastAPI(title='Keyword Risk Analyzer API', version='1.1.1',
              docs_url='/docs' if os.getenv('API_DOCS_ENABLED') == 'true' else None,
              redoc_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in os.getenv(
        'API_CORS_ORIGINS',
        'http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174'
    ).split(',') if origin.strip()],
    allow_methods=['GET', 'POST', 'PUT', 'DELETE'],
    allow_headers=['Authorization', 'Content-Type'],
)
bearer = HTTPBearer(auto_error=False)
logger = logging.getLogger(__name__)
REGISTRATION_DATE_COL = '키워드 등록일자'
_ocr_request_lock = Lock()


def get_repository():
    if not cloud_enabled():
        raise HTTPException(503, 'API requires STORAGE_BACKEND=supabase')
    return SupabaseRepository()


def current_actor(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
    if not credentials or credentials.scheme.lower() != 'bearer':
        raise HTTPException(401, 'Bearer token required', headers={'WWW-Authenticate': 'Bearer'})
    integration_key = os.getenv('API_ACCESS_TOKEN', '')
    if integration_key and secrets.compare_digest(credentials.credentials.encode(), integration_key.encode()):
        # Dedicated integration token grants analysis/read access, never admin writes.
        return 'integration'
    try:
        user = SupabaseRepository().user(credentials.credentials)
        if user.get('app_metadata', {}).get('role') not in {'admin', 'member'}:
            raise PermissionError('No application access')
        return user['id']
    except PermissionError:
        raise HTTPException(401, 'Invalid or expired token') from None


class AnalysisRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    text: str = Field(min_length=1, max_length=20000)
    mode: Literal['exact', 'similar', 'partial'] = Field(default='similar',
        description='exact: full expression; partial: consecutive keyword fragments; similar: legacy token/variant rules. Use exact or partial with explicit normalization options for the current UI behavior.')
    exact_relaxed: bool = Field(default=False, deprecated=True,
                                description='Legacy bundled option. Independent options take precedence when provided.')
    strip_bracket_notes: bool | None = Field(default=None, strict=True,
        description='Exclude parenthetical notes from the keyword used for exact/partial comparison.')
    normalize_whitespace: bool | None = Field(default=None, strict=True,
        description='Ignore spaces, line breaks and invisible whitespace while comparing.')
    ignore_case: bool | None = Field(default=None, strict=True,
        description='Ignore English letter case.')
    normalize_symbols: bool | None = Field(default=None, strict=True,
        description='Replace configured symbols with spaces independently of whitespace normalization.')
    partial_min_len: int = Field(default=2, ge=2, le=30,
        description='Minimum consecutive fragment length for partial mode, after selected normalization.')
    similar_reverse_single: bool = Field(default=True, deprecated=True, description='Legacy similar mode only.')
    similar_reverse_any: bool = Field(default=False, deprecated=True, description='Legacy similar mode only.')
    categories: list[str] = Field(default_factory=list, max_length=100)
    risks: list[str] = Field(default_factory=list, max_length=20)
    record: bool = False
    analysis_id: UUID | None = None


class RegulationConversationMessage(BaseModel):
    model_config = ConfigDict(extra='forbid')
    role: Literal['user', 'assistant']
    content: str = Field(min_length=1, max_length=4000)


class RegulationQuestionRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    direction: Literal['keyword_to_law', 'law_to_keywords']
    query: str = Field(min_length=2, max_length=500)
    context_text: str = Field(default='', max_length=20000)
    category: str = Field(default='', max_length=100)
    conversation_history: list[RegulationConversationMessage] = Field(default_factory=list, max_length=12)
    scope: Literal['legacy', 'law', 'internal', 'keyword', 'all'] = 'legacy'
    use_llm: bool = False
    include_keyword_candidates: bool = False
    thread_id: UUID | None = None
    as_of: date = Field(default_factory=date.today)

    @field_validator('conversation_history')
    @classmethod
    def validate_conversation_size(cls, messages):
        if sum(len(message.content) for message in messages) > 20000:
            raise ValueError('conversation history must not exceed 20000 characters')
        return messages


class CurrentAnalysisRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    analysis_id: UUID
    text: str = Field(min_length=1, max_length=20000)
    mode: Literal['exact', 'similar', 'partial'] = 'similar'
    strip_bracket_notes: bool = Field(default=True, strict=True)
    normalize_whitespace: bool = Field(default=True, strict=True)
    ignore_case: bool = Field(default=True, strict=True)
    normalize_symbols: bool = Field(default=True, strict=True)
    partial_min_len: int = Field(default=2, ge=2, le=20)
    categories: list[str] = Field(default_factory=list, max_length=100)
    risks: list[str] = Field(default_factory=list, max_length=20)


class AnalysisMatchResponse(BaseModel):
    term: str
    start: int
    end: int
    category: str = ''
    risk: str = ''
    detail: str = ''
    kwd_no: str | None = None
    alternative: str = ''
    evidence_type: str = ''
    hit_count: str = ''
    last_search_date: str = ''


class CurrentAnalysisResponse(BaseModel):
    analysis_id: str
    matches: list[AnalysisMatchResponse]
    unique_keywords: list[str]
    unique_keyword_rows: list[dict[str, str]]
    keyword_revision: int | None = None
    catalog_revision: int | None = None
    unmatched_collection_pending: bool = False
    offset_unit: Literal['unicode_codepoint']
    end_exclusive: bool
    recorded: bool


class TopKeywordResponse(BaseModel):
    kwd_no: str
    hit_count: int
    term: str | None = None
    search_rank: int
    keyword_data: dict[str, str]


class TopKeywordsResponse(BaseModel):
    items: list[TopKeywordResponse]
    keyword_revision: int | None = None


class UnmatchedRegistrationCandidate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    term: str = Field(min_length=1, max_length=150)
    source_terms: str = Field(default='', max_length=500)
    occurrences: int = Field(default=0, ge=0, le=1_000_000_000)
    category: str = Field(default='', max_length=500)
    risk: str = Field(default='', max_length=500)
    criteria: str = Field(default='', max_length=500)
    evidence_type: str = Field(default='', max_length=500)
    alternative: str = Field(default='-', max_length=500)


class UnmatchedRegistrationRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    candidates: list[UnmatchedRegistrationCandidate] = Field(min_length=1, max_length=1000)


class KeywordRequestSubmission(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kwd_no: str = Field(min_length=1, max_length=100)
    request_type: Literal['risk_grade_adjustment', 'review_criteria_change']
    # Optional in the Streamlit form ('요청 상세 내용 (선택)').
    request_detail: str = Field(default='', max_length=4000)


class NewKeywordRegistrationSubmission(BaseModel):
    model_config = ConfigDict(extra='forbid')
    terms: list[str] = Field(min_length=1, max_length=1000)


class AdminCatalogRegistrationRow(BaseModel):
    model_config = ConfigDict(extra='forbid')
    term: str = Field(min_length=1, max_length=500)
    source_terms: str = Field(default='', max_length=2000)
    term_norm: str = Field(default='', max_length=100)
    request_id: UUID | None = None
    category: str = Field(max_length=500)
    risk: str = Field(max_length=500)
    criteria: str = Field(max_length=5000)
    evidence_type: str = Field(max_length=500)
    alternative: str = Field(default='-', max_length=2000)


class AdminCatalogRegistration(BaseModel):
    model_config = ConfigDict(extra='forbid')
    rows: list[AdminCatalogRegistrationRow] = Field(min_length=1, max_length=1000)


class KeywordSuggestionRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    term: str = Field(min_length=1, max_length=150)
    category: str = Field(default='', max_length=100)
    context: str = Field(default='', max_length=500)
    as_of: date = Field(default_factory=date.today)


class AdminRequestDelete(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_ids: list[UUID] = Field(min_length=1, max_length=1000)


class KeywordRequestUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    status: Literal['대기', '검토중', '처리완료']
    admin_reply: str = Field(default='', max_length=4000)


class KeywordRequestMessageCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    body: str = Field(min_length=1, max_length=4000)
    reply_to_id: UUID | None = None
    status: str = Field(default='', max_length=20)



class KeywordRequestMessageEdit(BaseModel):
    model_config = ConfigDict(extra='forbid')
    body: str = Field(max_length=4000)
    request_type: Literal['risk_grade_adjustment', 'review_criteria_change', 'new_keyword_registration'] | None = None


class AdminRequestNotificationsUpdate(BaseModel):
    enabled: bool


class AdminUserRoleUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    role: Literal['admin', 'member']
    expected_role: Literal['admin', 'member'] | None = None


class AdminKeywordRow(BaseModel):
    # Extra string fields carry stored catalog columns beyond DB_COLS
    # (for example '키워드 등록일자'); unknown names are ignored on save.
    model_config = ConfigDict(extra='allow', populate_by_name=True)
    kwd_no: str = Field(min_length=1, max_length=100)
    keyword_name: str = Field(alias='키워드명', max_length=500)
    category: str = Field(alias='상품카테고리', max_length=500)
    risk_grade: str = Field(alias='리스크 등급', max_length=500)
    alternative: str = Field(alias='대체키워드', max_length=2000)
    criteria: str = Field(alias='리스크 등급별 세부 심의기준', max_length=5000)
    evidence_type: str = Field(alias='증빙자료유형', max_length=500)
    hit_count: str = Field(default='0', alias=COUNT_COL, max_length=32)
    last_hit: str = Field(default='', alias=LAST_COL, max_length=100)


class AdminKeywordSave(BaseModel):
    model_config = ConfigDict(extra='forbid')
    revision: int = Field(ge=0)
    rows: list[AdminKeywordRow] = Field(min_length=1, max_length=10000)


class AdminKeywordDelete(BaseModel):
    model_config = ConfigDict(extra='forbid')
    revision: int = Field(ge=0)
    kwd_nos: list[str] = Field(min_length=1, max_length=1000)


class UnmatchedRegistrationUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: UUID
    category: str = Field(max_length=500)
    risk: str = Field(max_length=500)
    criteria: str = Field(max_length=500)
    evidence_type: str = Field(max_length=500)
    alternative: str = Field(default='-', max_length=500)


class UnmatchedRegistrationReview(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_ids: list[UUID] = Field(min_length=1, max_length=1000)
    updates: list[UnmatchedRegistrationUpdate] = Field(default_factory=list, max_length=1000)


class AdminUnmatchedDelete(BaseModel):
    model_config = ConfigDict(extra='forbid')
    terms: list[str] = Field(min_length=1, max_length=1000)


class AdminNormalizationSettings(BaseModel):
    model_config = ConfigDict(extra='forbid')
    ignored_symbols: list[str] = Field(min_length=1, max_length=100)
    extra_suffixes: list[str] = Field(max_length=1000)


class AdminDropdownSettings(BaseModel):
    model_config = ConfigDict(extra='forbid')
    opt_categories: list[str] = Field(min_length=1, max_length=500)
    opt_risks: list[str] = Field(min_length=1, max_length=200)
    opt_details: list[str] = Field(max_length=1000)
    opt_evidences: list[str] = Field(max_length=1000)
    opt_alt_terms: list[str] = Field(max_length=1000)


class UnmatchedSurface(BaseModel):
    model_config = ConfigDict(extra='forbid')
    surface: str = Field(min_length=1, max_length=150)
    occurrences: int = Field(default=0, ge=0, le=1_000_000_000)


class UnmatchedNormalizationRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    candidates: list[UnmatchedSurface] = Field(min_length=1, max_length=1000)


class UnmatchedRecommendationDraft(BaseModel):
    model_config = ConfigDict(extra='forbid')
    payload: dict


class OCRKeywordCandidate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    term: str = Field(min_length=1, max_length=500)
    category: str = Field(min_length=1, max_length=500)
    risk: str = Field(min_length=1, max_length=500)
    detail: str = Field(min_length=1, max_length=5000)
    evidence: str = Field(min_length=1, max_length=500)
    alternative: str = Field(default='-', max_length=2000)


class OCRKeywordSave(BaseModel):
    model_config = ConfigDict(extra='forbid')
    revision: int = Field(ge=0)
    candidates: list[OCRKeywordCandidate] = Field(min_length=1, max_length=1000)


class AdminApprovedPartialUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kwd_no: str = Field(min_length=1, max_length=100)
    term: str = Field(min_length=1, max_length=500)
    expected_expressions: list[str] = Field(max_length=500)
    expressions: list[str] = Field(max_length=500)


def _catalog_columns(current) -> list[str]:
    """Every stored catalog column, in snapshot order (never just DB_COLS).

    The catalog can carry extra columns such as '키워드 등록일자'. Rebuilding a
    save frame from DB_COLS alone would drop those columns from every row.
    """
    columns = [str(column) for column in current.columns]
    return columns + [column for column in DB_COLS if column not in columns]


def _catalog_frame(rows: list[dict], columns: list[str]):
    import pandas as pd
    return pd.DataFrame(rows, columns=columns).fillna('').astype(str)


def _next_keyword_code(category: str, rows: list[dict]) -> str:
    category_rows = [row for row in rows if str(row.get(DB_COLS[2], '')).strip() == category]
    pattern = re.compile(r'^([A-Z]+)(\d{3,})$')
    prefixes = [match.group(1) for row in category_rows
                if (match := pattern.match(str(row.get('kwd_no', '')).strip()))]
    if prefixes:
        prefix = max(set(prefixes), key=prefixes.count)
    else:
        prefix = {'공통(전체)': 'A', '식품': 'F', '건강기능식품': 'G',
                  '화장품': 'B', '공산품': 'I'}.get(category, '')
        if not prefix:
            first = category[:1].upper()
            prefix = first if re.fullmatch(r'[A-Z]', first) else 'U'
    same_category = [match for row in category_rows
                     if (match := pattern.match(str(row.get('kwd_no', '')).strip()))
                     and match.group(1) == prefix]
    same_prefix = [match for row in rows
                   if (match := pattern.match(str(row.get('kwd_no', '')).strip()))
                   and match.group(1) == prefix]
    source = same_category or same_prefix
    width = max([3, *(len(match.group(2)) for match in same_category)])
    number = max((int(match.group(2)) for match in source), default=0) + 1
    existing = {str(row.get('kwd_no', '')).strip() for row in rows}
    while f'{prefix}{number:0{width}d}' in existing:
        number += 1
    return f'{prefix}{number:0{width}d}'


@app.exception_handler(StorageError)
def storage_error(request: Request, exc: StorageError):
    return JSONResponse(status_code=409 if isinstance(exc, ConflictError) else 503,
                        content={'detail': str(exc)})


@app.exception_handler(PermissionError)
def permission_error(request: Request, exc: PermissionError):
    return JSONResponse(status_code=503, content={'detail': 'Backend permissions are not configured'})


@app.get('/healthz')
def health():
    return {'status': 'ok'}


@app.get('/readyz', dependencies=[Depends(current_actor)])
def ready(repository=Depends(get_repository)):
    repository.load_keywords()
    return {'status': 'ready'}


def _process_ocr_images(images):
    from ocr_keyword_import import extract_text_lines, load_korean_ocr, make_image_preview_data

    os.environ['PADDLE_PDX_EAGER_INIT'] = 'False'
    os.environ['PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT'] = 'False'
    try:
        engine = load_korean_ocr()
    except ImportError as exc:
        logger.exception('PaddleOCR dependencies could not be imported')
        raise HTTPException(503,
            '한국어 OCR 의존성을 불러오지 못했습니다. API 실행 환경의 Python 3.13, requirements-ocr.txt 설치 상태와 서버 로그를 확인하세요.') from exc
    except (OSError, RuntimeError) as exc:
        logger.exception('PaddleOCR engine initialization failed')
        raise HTTPException(503,
            'PaddleOCR engine initialization failed. Check API service logs for details.') from exc
    file_results, unique = [], {}
    for index, (name, image_bytes) in enumerate(images):
        try:
            with _ocr_request_lock:
                lines = extract_text_lines(image_bytes, engine)
            try:
                preview, width, height = make_image_preview_data(image_bytes)
                preview_error = ''
            except Exception:
                preview, width, height = None, 1, 1
                preview_error = '미리보기 이미지를 만들지 못했습니다.'
            file_results.append({
                'index': index, 'name': name, 'count': len(lines), 'error': '',
                'lines': lines[:2000], 'truncated': len(lines) > 2000,
                'preview_data': preview, 'image_width': width, 'image_height': height,
                'preview_error': preview_error,
            })
            for line in lines:
                term = unicodedata.normalize('NFKC', str(line['text'])).strip()
                normalized = ' '.join(term.split()).casefold()
                if not normalized:
                    continue
                confidence = float(line.get('confidence', 0))
                candidate = unique.setdefault(normalized, {
                    'term': term, 'confidence': confidence, 'occurrences': 0, 'source_files': [],
                })
                if confidence >= 0.60:
                    candidate['occurrences'] += 1
                if confidence > candidate['confidence']:
                    candidate.update(term=term, confidence=confidence)
                if name not in candidate['source_files']:
                    candidate['source_files'].append(name)
        except Exception as exc:
            logger.exception('OCR failed for uploaded image %s', name)
            file_results.append({'index': index, 'name': name, 'count': 0,
                                 'error': str(exc)[:300], 'lines': []})
    candidates = [{**row, 'category': '', 'risk': '', 'detail': '', 'evidence': '',
                   'alternative': '-', 'approved': row['confidence'] >= 0.60}
                  for row in unique.values()]
    return {'files': file_results, 'candidates': candidates}


@app.post('/api/v1/ocr/extract')
async def extract_ocr_candidates(
        files: list[UploadFile] = File(...), actor=Depends(current_actor)):
    if actor == 'integration':
        raise HTTPException(403, 'A user session is required to run OCR')
    if not 1 <= len(files) <= 5:
        raise HTTPException(422, 'Upload between 1 and 5 images.')
    images, total_bytes = [], 0
    for upload in files:
        image_bytes = await upload.read(20 * 1024 * 1024 + 1)
        if len(image_bytes) > 20 * 1024 * 1024:
            raise HTTPException(413, f'{upload.filename or "Image"} exceeds 20 MB.')
        total_bytes += len(image_bytes)
        if total_bytes > 50 * 1024 * 1024:
            raise HTTPException(413, 'Combined image size exceeds 50 MB.')
        images.append((str(upload.filename or f'image-{len(images) + 1}')[:255], image_bytes))
    try:
        return await run_in_threadpool(_process_ocr_images, images)
    except HTTPException:
        raise
    except ImportError as exc:
        logger.exception('OCR dependency import failed while processing the request')
        raise HTTPException(503,
            'OCR dependencies could not be imported. Check the API build logs for requirements-ocr.txt.') from exc


@app.post('/api/v1/ocr/keywords')
def save_ocr_keywords(body: OCRKeywordSave, actor=Depends(current_actor),
                      credentials: HTTPAuthorizationCredentials = Depends(bearer),
                      repository=Depends(get_repository)):
    if actor == 'integration':
        raise HTTPException(403, 'A user session is required to register OCR keywords')
    if (repository.user(credentials.credentials).get('app_metadata') or {}).get('role') != 'admin':
        raise HTTPException(403, 'Only administrators can register OCR keywords')
    current = repository.load_keywords()
    if current.attrs.get('revision') != body.revision:
        raise HTTPException(409, 'Keyword data changed. Reload it before saving OCR candidates.')
    current_rows = current.to_dict('records')
    existing = {(unicodedata.normalize('NFKC', str(row[DB_COLS[1]])).casefold().strip(),
                 unicodedata.normalize('NFKC', str(row[DB_COLS[2]])).casefold().strip())
                for row in current_rows}
    candidates = [item.model_dump() for item in body.candidates]
    pairs = [(unicodedata.normalize('NFKC', item['term']).casefold().strip(),
              unicodedata.normalize('NFKC', item['category']).casefold().strip())
             for item in candidates]
    if len(set(pairs)) != len(pairs) or any(pair in existing for pair in pairs):
        raise HTTPException(422, 'OCR candidates contain duplicate keywords. Review and remove duplicates first.')
    rows = list(current_rows)
    codes = []
    for item in candidates:
        code = _next_keyword_code(item['category'].strip(), rows)
        codes.append(code)
        rows.append({
            DB_COLS[0]: code, DB_COLS[1]: item['term'].strip(), DB_COLS[2]: item['category'].strip(),
            DB_COLS[3]: item['risk'].strip(), DB_COLS[4]: item['alternative'].strip() or '-',
            DB_COLS[5]: item['detail'].strip(), DB_COLS[6]: item['evidence'].strip(),
            COUNT_COL: '0', LAST_COL: '',
        })
    frame = _catalog_frame(rows, _catalog_columns(current))
    try:
        revision = repository.save_keywords(frame, body.revision)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {'added': codes, 'revision': revision}


@app.post('/api/v1/analyses')
def create_analysis(body: AnalysisRequest, actor=Depends(current_actor),
                    repository=Depends(get_repository)):
    return analyze(repository, body.model_dump(mode='json'), actor)


@app.get('/api/v2/analysis-filters')
def analysis_filters(actor=Depends(current_actor), repository=Depends(get_repository)):
    df = repository.load_keywords()
    return {
        'categories': sorted({value for value in df[DB_COLS[2]].fillna('').astype(str).str.strip() if value}),
        'risks': sorted({value for value in df[DB_COLS[3]].fillna('').astype(str).str.strip() if value}),
        'evidence_types': sorted({value for value in df[DB_COLS[6]].fillna('').astype(str).str.strip() if value}),
    }


@app.post('/api/v2/analyses', response_model=CurrentAnalysisResponse)
def create_current_analysis(body: CurrentAnalysisRequest, actor=Depends(current_actor),
                            repository=Depends(get_repository)):
    if actor == 'integration':
        raise HTTPException(403, 'A user session is required to record an analysis')
    return analyze_current(repository, body.model_dump(mode='json'), actor)


@app.get('/api/v1/unmatched-terms')
def unmatched_terms(offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=1000),
                    search: str = Query('', max_length=200),
                    sort: Literal['occurrences', 'registered'] = 'occurrences',
                    actor=Depends(current_actor), repository=Depends(get_repository)):
    return repository.load_unmatched_terms(offset, limit, search, sort)


@app.get('/api/v1/unmatched-terms/export')
def export_unmatched_terms(actor=Depends(current_actor), repository=Depends(get_repository)):
    return {'items': repository.export_unmatched_terms()}


@app.post('/api/v1/admin/unmatched-terms/delete')
def delete_admin_unmatched_terms(
        body: AdminUnmatchedDelete, actor=Depends(current_actor),
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
        repository=Depends(get_repository)):
    if actor == 'integration' or not credentials:
        raise HTTPException(403, 'Administrator session required')
    terms = [term.strip() for term in body.terms]
    if any(not term or len(term) > 100 for term in terms) or len(set(terms)) != len(terms):
        raise HTTPException(422, 'Candidate terms must be unique and between 1 and 100 characters')
    try:
        deleted = repository.delete_unmatched_terms(terms, credentials.credentials)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except StorageError as exc:
        raise HTTPException(502, 'Could not delete unmatched candidates from storage') from exc
    return {'deleted': deleted}


@app.post('/api/v1/unmatched-terms/registration-requests')
def submit_unmatched_registration_requests(
        body: UnmatchedRegistrationRequest, actor=Depends(current_actor),
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
        repository=Depends(get_repository)):
    if actor == 'integration':
        raise HTTPException(403, 'A user session is required to submit registration requests')
    if not credentials:
        raise HTTPException(401, 'Bearer token required', headers={'WWW-Authenticate': 'Bearer'})
    candidates = [candidate.model_dump() for candidate in body.candidates]
    try:
        items = repository.submit_unmatched_registration_requests(candidates, credentials.credentials)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {'items': items or []}


@app.post('/api/v1/keyword-suggestions')
def keyword_suggestion(body: KeywordSuggestionRequest, actor=Depends(current_actor),
                       repository=Depends(get_repository)):
    if actor == 'integration':
        raise HTTPException(403, 'A user account is required for AI suggestions')
    if not body.term.strip():
        raise HTTPException(422, '추천할 키워드를 입력하세요.')
    try:
        return suggest_keyword(repository, body.term.strip(), body.category.strip(),
                               body.context.strip(), body.as_of)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    except SuggestionProviderError as exc:
        status = exc.status_code
        if status == 429:
            raise HTTPException(429, 'OpenAI 요청 한도에 도달했습니다. 잠시 후 다시 시도하거나 프로젝트 사용 한도와 크레딧을 확인하세요.') from exc
        if status == 401:
            raise HTTPException(502, 'OpenAI API 키가 유효하지 않습니다. 서버 설정을 확인하세요.') from exc
        if status == 403:
            raise HTTPException(502, 'OpenAI 프로젝트에 이 모델의 사용 권한이 없습니다. 서버 설정을 확인하세요.') from exc
        if status == 400:
            raise HTTPException(502, 'OpenAI 요청이 거부되었습니다 (HTTP 400). 모델 설정 또는 요청 형식을 확인하세요.') from exc
        if status is not None:
            raise HTTPException(502, f'OpenAI 추천 요청이 실패했습니다 (HTTP {status}).') from exc
        raise HTTPException(502, 'OpenAI API에 연결하지 못했습니다. 잠시 후 다시 시도하세요.') from exc
    except requests.RequestException as exc:
        logger.warning('Keyword suggestion evidence lookup failed', exc_info=True)
        raise HTTPException(502, '추천 근거를 불러오지 못했습니다. 잠시 후 다시 시도하세요.') from exc
    except (ValueError, KeyError, TypeError) as exc:
        logger.warning('Keyword suggestion response could not be processed', exc_info=True)
        raise HTTPException(502, 'AI 추천 응답을 해석하지 못했습니다. 잠시 후 다시 시도하세요.') from exc


@app.post('/api/v1/unmatched-terms/normalize')
def normalize_unmatched_terms(body: UnmatchedNormalizationRequest, actor=Depends(current_actor)):
    from auxiliary_analysis import AuxiliaryUnavailable, normalize_unmatched_term_candidates
    try:
        candidates = normalize_unmatched_term_candidates(
            [row.model_dump() for row in body.candidates])
    except AuxiliaryUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    return {'items': candidates}


@app.get('/api/v1/unmatched-terms/recommendation-draft')
def unmatched_recommendation_draft(
        actor=Depends(current_actor),
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
        repository=Depends(get_repository)):
    if actor == 'integration' or not credentials:
        raise HTTPException(403, 'A user session is required to access drafts')
    try:
        return {'payload': repository.load_unmatched_recommendation_draft(credentials.credentials)}
    except PermissionError as exc:
        raise HTTPException(401, str(exc)) from exc


@app.put('/api/v1/unmatched-terms/recommendation-draft')
def save_unmatched_recommendation_draft(
        body: UnmatchedRecommendationDraft, actor=Depends(current_actor),
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
        repository=Depends(get_repository)):
    if actor == 'integration' or not credentials:
        raise HTTPException(403, 'A user session is required to access drafts')
    try:
        repository.save_unmatched_recommendation_draft(body.payload, credentials.credentials)
    except (PermissionError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc
    return {'saved': True}


@app.get('/api/v1/admin/unmatched-registration-requests')
def admin_unmatched_registration_requests(
        actor=Depends(current_actor),
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
        repository=Depends(get_repository)):
    if actor == 'integration' or not credentials:
        raise HTTPException(403, 'Administrator session required')
    user = repository.user(credentials.credentials)
    if (user.get('app_metadata') or {}).get('role') != 'admin':
        raise HTTPException(403, 'Administrator role required')
    try:
        return {'items': repository.load_unmatched_registration_requests(credentials.credentials)}
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc


@app.post('/api/v1/admin/unmatched-registration-requests/reject')
def reject_admin_unmatched_registration_requests(
        body: UnmatchedRegistrationReview, actor=Depends(current_actor),
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
        repository=Depends(get_repository)):
    if actor == 'integration' or not credentials:
        raise HTTPException(403, 'Administrator session required')
    user = repository.user(credentials.credentials)
    if (user.get('app_metadata') or {}).get('role') != 'admin':
        raise HTTPException(403, 'Administrator role required')
    try:
        rejected = repository.reject_unmatched_registration_requests(
            [str(request_id) for request_id in body.request_ids], credentials.credentials)
    except (PermissionError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc
    return {'rejected': rejected}


@app.post('/api/v1/admin/unmatched-registration-requests/approve')
def approve_admin_unmatched_registration_requests(
        body: UnmatchedRegistrationReview, actor=Depends(current_actor),
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
        repository=Depends(get_repository)):
    if actor == 'integration' or not credentials:
        raise HTTPException(403, 'Administrator session required')
    user = repository.user(credentials.credentials)
    if (user.get('app_metadata') or {}).get('role') != 'admin':
        raise HTTPException(403, 'Administrator role required')
    requests_by_id = {row['id']: row for row in repository.load_unmatched_registration_requests(
        credentials.credentials)}
    selected = [requests_by_id.get(str(request_id)) for request_id in body.request_ids]
    if any(row is None for row in selected):
        raise HTTPException(409, 'One or more requests are no longer in the review queue.')
    updates = {str(update.request_id): update.model_dump(exclude={'request_id'}) for update in body.updates}
    if len(updates) != len(body.updates) or not set(updates).issubset({str(value) for value in body.request_ids}):
        raise HTTPException(422, 'Registration updates must match selected request IDs.')
    selected = [{**row, **updates.get(row['id'], {})} for row in selected]
    required = ('term', 'category', 'risk', 'criteria', 'evidence_type')
    if any(not str(row.get(field) or '').strip() for row in selected for field in required):
        raise HTTPException(422, 'Every selected request needs a term, category, risk, criteria, and evidence type.')

    current = repository.load_keywords()
    rows = current.to_dict('records')
    existing = {(unicodedata.normalize('NFKC', str(row[DB_COLS[1]])).casefold().strip(),
                 str(row[DB_COLS[2]]).strip()) for row in rows}
    additions = []
    for item in selected:
        term = str(item['term']).strip()
        category = str(item['category']).strip()
        key = (unicodedata.normalize('NFKC', term).casefold(), category)
        if key in existing:
            continue
        existing.add(key)
        additions.append({
            DB_COLS[0]: _next_keyword_code(category, rows + additions),
            DB_COLS[1]: term, DB_COLS[2]: category, DB_COLS[3]: str(item['risk']).strip(),
            DB_COLS[4]: str(item.get('alternative') or '-').strip() or '-',
            DB_COLS[5]: str(item['criteria']).strip(), DB_COLS[6]: str(item['evidence_type']).strip(),
            COUNT_COL: '0', LAST_COL: '',
        })
    if additions:
        frame = _catalog_frame(rows + additions, _catalog_columns(current))
        try:
            repository.save_keywords(frame, current.attrs.get('revision'))
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    source_keys = set()
    for item in selected:
        raw_key = str(item.get('term_norm') or '').strip()
        if raw_key:
            source_keys.add(raw_key)
        else:
            sources = str(item.get('source_terms') or '').strip().split(' | ')
            for source in (sources if sources != [''] else [str(item.get('term') or '')]):
                normalized = unicodedata.normalize('NFKC', source).casefold().strip()
                if 1 <= len(normalized) <= 100:
                    source_keys.add(normalized)
    if source_keys:
        repository.delete_unmatched_terms(sorted(source_keys), credentials.credentials)
    cleared = repository.delete_unmatched_registration_requests(
        [str(request_id) for request_id in body.request_ids], credentials.credentials)
    return {'approved': len(selected), 'added': [row[DB_COLS[0]] for row in additions], 'cleared_requests': cleared}


def _require_admin_session(actor, credentials, repository):
    if actor == 'integration' or not credentials:
        raise HTTPException(403, 'Administrator session required')
    user = repository.user(credentials.credentials)
    if (user.get('app_metadata') or {}).get('role') != 'admin':
        raise HTTPException(403, 'Administrator role required')


def _registration_source_keys(rows: list[dict]) -> list[str]:
    """unmatched_registration_source_keys (Streamlit FIXED329)."""
    keys = set()
    for item in rows:
        request_key = str(item.get('term_norm') or '').strip()
        if request_key:
            keys.add(request_key)
            continue
        source_terms = str(item.get('source_terms') or '').strip()
        sources = source_terms.split(' | ') if source_terms else [str(item.get('term') or '')]
        keys.update(unicodedata.normalize('NFKC', source).casefold().strip()
                    for source in sources if str(source).strip())
    return sorted(key for key in keys if 1 <= len(key) <= 100)


@app.post('/api/v1/admin/unmatched-terms/register')
def register_unmatched_rows(body: AdminCatalogRegistration, actor=Depends(current_actor),
                            credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
                            repository=Depends(get_repository)):
    """'선택 후보 승인 및 DB 등록' for queued requests, normalized and manual rows alike."""
    _require_admin_session(actor, credentials, repository)
    selected = [row.model_dump(mode='json') for row in body.rows]
    required = ('term', 'category', 'risk', 'criteria', 'evidence_type')
    if any(not str(row.get(field) or '').strip() for row in selected for field in required):
        raise HTTPException(422, '선택한 후보의 키워드명, 카테고리, 리스크 등급, 심의기준, 증빙자료유형을 모두 입력하세요.')
    current = repository.load_keywords()
    rows = current.to_dict('records')
    existing = {(str(row[DB_COLS[1]]).strip().casefold(), str(row[DB_COLS[2]]).strip()) for row in rows}
    additions = []
    for item in selected:
        term, category = item['term'].strip(), item['category'].strip()
        key = (term.casefold(), category)
        if key in existing:
            continue
        existing.add(key)
        additions.append({
            DB_COLS[0]: _next_keyword_code(category, rows + additions), DB_COLS[1]: term,
            DB_COLS[2]: category, DB_COLS[3]: item['risk'].strip(),
            DB_COLS[4]: item['alternative'].strip() or '-', DB_COLS[5]: item['criteria'].strip(),
            DB_COLS[6]: item['evidence_type'].strip(), COUNT_COL: '0', LAST_COL: '',
        })
    if additions:
        try:
            repository.save_keywords(_catalog_frame(rows + additions, _catalog_columns(current)),
                                     current.attrs.get('revision'))
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
    try:
        keys = _registration_source_keys(selected)
        if keys:
            repository.delete_unmatched_terms(keys, credentials.credentials)
        request_ids = [str(row['request_id']) for row in selected if row.get('request_id')]
        cleared = (repository.delete_unmatched_registration_requests(request_ids, credentials.credentials)
                   if request_ids else 0)
    except (StorageError, PermissionError, ValueError) as exc:
        return {'added': [row[DB_COLS[0]] for row in additions], 'cleared_requests': 0,
                'cleaned_terms': 0, 'cleanup_error': str(exc)[:300]}
    return {'added': [row[DB_COLS[0]] for row in additions], 'cleared_requests': cleared,
            'cleaned_terms': len(keys), 'cleanup_error': ''}


@app.post('/api/v1/admin/unmatched-registration-requests/delete')
def delete_admin_registration_requests(body: AdminRequestDelete, actor=Depends(current_actor),
                                       credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
                                       repository=Depends(get_repository)):
    """'선택 항목 삭제' on queued requests: remove the requests without marking candidates ignored."""
    _require_admin_session(actor, credentials, repository)
    try:
        deleted = repository.delete_unmatched_registration_requests(
            [str(value) for value in body.request_ids], credentials.credentials)
    except (PermissionError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc
    return {'deleted': deleted}


@app.get('/api/v1/keyword-requests')
def keyword_requests(limit: int = Query(100, ge=1, le=1000), actor=Depends(current_actor),
                     credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
                     repository=Depends(get_repository)):
    if actor == 'integration':
        raise HTTPException(403, 'A user session is required to view keyword requests')
    if not credentials:
        raise HTTPException(401, 'Bearer token required', headers={'WWW-Authenticate': 'Bearer'})
    return {'items': repository.load_keyword_requests(credentials.credentials, limit=limit)}


@app.post('/api/v1/keyword-requests/new-keywords')
def submit_new_keyword_requests(body: NewKeywordRegistrationSubmission, actor=Depends(current_actor),
                                credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
                                repository=Depends(get_repository)):
    """Sidebar '신규키워드 등록요청': adds the terms to the unmatched list as requests."""
    if actor == 'integration' or not credentials:
        raise HTTPException(403, 'A user session is required to submit keyword requests')
    terms, seen = [], set()
    for value in body.terms:
        term = str(value or '').strip()
        key = unicodedata.normalize('NFKC', term).casefold()
        if term and key not in seen:
            seen.add(key)
            terms.append(term)
    if not terms:
        raise HTTPException(422, '등록 요청할 키워드를 쉼표로 구분해 입력하세요.')
    try:
        result = repository.submit_new_keyword_registration_requests(terms, credentials.credentials)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {'submitted': len(terms), 'result': result}


@app.post('/api/v1/keyword-requests')
def submit_keyword_request(body: KeywordRequestSubmission, actor=Depends(current_actor),
                           credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
                           repository=Depends(get_repository)):
    if actor == 'integration':
        raise HTTPException(403, 'A user session is required to submit keyword requests')
    if not credentials:
        raise HTTPException(401, 'Bearer token required', headers={'WWW-Authenticate': 'Bearer'})
    detail = body.request_detail.strip()
    user = repository.user(credentials.credentials)
    keywords = repository.load_keywords()
    matches = keywords[keywords['kwd_no'].astype(str).str.strip().str.casefold()
                       == body.kwd_no.strip().casefold()]
    if matches.empty:
        raise HTTPException(404, 'Keyword number not found')
    row = matches.iloc[0]
    payload = {
        'requester_id': user['id'], 'requester_email': user.get('email', ''),
        'kwd_no': str(row['kwd_no']).strip(), 'keyword_name': str(row['키워드명']).strip(),
        'request_type': body.request_type, 'request_detail': detail,
    }
    try:
        row = repository.submit_keyword_request(payload, credentials.credentials)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    # Same follow-up as the Streamlit sidebar form: notify the administrator when enabled.
    from request_notifications import (NotificationConfigurationError, NotificationDeliveryError,
                                       send_keyword_request_email)
    notification, notification_error = 'disabled', ''
    try:
        if repository.load_request_email_notifications():
            send_keyword_request_email(row)
            notification = 'sent'
    except (NotificationConfigurationError, NotificationDeliveryError, StorageError) as exc:
        notification, notification_error = 'failed', str(exc)[:300]
    result = dict(row) if isinstance(row, dict) else {'row': row}
    result.update(notification=notification, notification_error=notification_error)
    return result


@app.put('/api/v1/keyword-requests/{request_id}')
def update_keyword_request(request_id: UUID, body: KeywordRequestUpdate,
                          actor=Depends(current_actor),
                          credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
                          repository=Depends(get_repository)):
    if actor == 'integration':
        raise HTTPException(403, 'A user session is required to update keyword requests')
    if not credentials:
        raise HTTPException(401, 'Bearer token required', headers={'WWW-Authenticate': 'Bearer'})
    user = repository.user(credentials.credentials)
    if (user.get('app_metadata') or {}).get('role') != 'admin':
        raise HTTPException(403, 'Administrator role required')
    return repository.update_keyword_request(str(request_id), body.status,
                                            body.admin_reply.strip(), credentials.credentials)


@app.get('/api/v1/keyword-requests/{request_id}/messages')
def keyword_request_messages(request_id: UUID, actor=Depends(current_actor),
                             credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
                             repository=Depends(get_repository)):
    if actor == 'integration' or not credentials:
        raise HTTPException(403, 'A user session is required to view inquiry messages')
    return {'items': repository.load_keyword_request_messages(str(request_id), credentials.credentials)}


@app.post('/api/v1/keyword-requests/{request_id}/messages')
def add_keyword_request_message(request_id: UUID, body: KeywordRequestMessageCreate,
                                actor=Depends(current_actor),
                                credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
                                repository=Depends(get_repository)):
    if actor == 'integration' or not credentials:
        raise HTTPException(403, 'A user session is required to post inquiry messages')
    content = body.body.strip()
    if not content:
        raise HTTPException(422, 'Message body must contain text')
    user = repository.user(credentials.credentials)
    role = (user.get('app_metadata') or {}).get('role')
    try:
        if role == 'admin':
            if body.reply_to_id is None:
                raise HTTPException(422, 'Select the inquiry this reply belongs to')
            result = repository.respond_to_keyword_inquiry(
                str(request_id), str(body.reply_to_id), content, body.status,
                credentials.credentials)
            return {'id': str(result), 'author_role': 'admin'}
        result = repository.add_keyword_request_message(
            str(request_id), user['id'], user.get('email', ''), content,
            credentials.credentials, author_role='user',
            reply_to_id=str(body.reply_to_id) if body.reply_to_id else None)
        return result
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc


@app.put('/api/v1/keyword-requests/{request_id}/messages/{message_id}')
def edit_own_keyword_request_message(request_id: UUID, message_id: UUID,
                                     body: KeywordRequestMessageEdit, actor=Depends(current_actor),
                                     credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
                                     repository=Depends(get_repository)):
    if actor == 'integration' or not credentials:
        raise HTTPException(403, 'A user session is required to edit inquiry messages')
    user = repository.user(credentials.credentials)
    if (user.get('app_metadata') or {}).get('role') == 'admin':
        raise HTTPException(403, 'Only the inquiry owner can edit a message')
    try:
        return repository.mutate_own_keyword_inquiry(
            str(request_id), str(message_id), 'edit', credentials.credentials,
            body=body.body, request_type=body.request_type)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc


@app.delete('/api/v1/keyword-requests/{request_id}/messages/{message_id}')
def delete_own_keyword_request_message(request_id: UUID, message_id: UUID,
                                       actor=Depends(current_actor),
                                       credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
                                       repository=Depends(get_repository)):
    if actor == 'integration' or not credentials:
        raise HTTPException(403, 'A user session is required to delete inquiry messages')
    user = repository.user(credentials.credentials)
    if (user.get('app_metadata') or {}).get('role') == 'admin':
        raise HTTPException(403, 'Only the inquiry owner can delete a message')
    try:
        return repository.mutate_own_keyword_inquiry(
            str(request_id), str(message_id), 'delete', credentials.credentials)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc


@app.delete('/api/v1/keyword-requests/{request_id}')
def delete_keyword_request(request_id: UUID, actor=Depends(current_actor),
                           credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
                           repository=Depends(get_repository)):
    if actor == 'integration' or not credentials:
        raise HTTPException(403, 'A user session is required to delete an inquiry')
    try:
        return repository.delete_keyword_request(str(request_id), credentials.credentials)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except StorageError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.get('/api/v1/admin/keyword-request-notifications')
def get_admin_request_notifications(actor=Depends(current_actor),
                                    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
                                    repository=Depends(get_repository)):
    if actor == 'integration' or not credentials:
        raise HTTPException(403, 'Administrator session required')
    user = repository.user(credentials.credentials)
    if (user.get('app_metadata') or {}).get('role') != 'admin':
        raise HTTPException(403, 'Administrator role required')
    from request_notifications import is_notification_configured
    return {'enabled': repository.load_request_email_notifications(credentials.credentials),
            'configured': is_notification_configured()}


@app.put('/api/v1/admin/keyword-request-notifications')
def save_admin_request_notifications(body: AdminRequestNotificationsUpdate,
                                     actor=Depends(current_actor),
                                     credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
                                     repository=Depends(get_repository)):
    if actor == 'integration' or not credentials:
        raise HTTPException(403, 'Administrator session required')
    user = repository.user(credentials.credentials)
    if (user.get('app_metadata') or {}).get('role') != 'admin':
        raise HTTPException(403, 'Administrator role required')
    from request_notifications import is_notification_configured
    configured = is_notification_configured()
    if body.enabled and not configured:
        raise HTTPException(503, 'Email notification delivery is not configured.')
    enabled = repository.save_request_email_notifications(body.enabled, credentials.credentials)
    return {'enabled': enabled, 'configured': configured}


@app.get('/api/v1/admin/users')
def admin_users(page: int = Query(1, ge=1), per_page: int = Query(100, ge=1, le=1000),
                actor=Depends(current_actor),
                credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
                repository=Depends(get_repository)):
    if actor == 'integration':
        raise HTTPException(403, 'A user session is required to manage accounts')
    if not credentials:
        raise HTTPException(401, 'Bearer token required', headers={'WWW-Authenticate': 'Bearer'})
    user = repository.user(credentials.credentials)
    if (user.get('app_metadata') or {}).get('role') != 'admin':
        raise HTTPException(403, 'Administrator role required')
    return {'items': repository.list_users(credentials.credentials, page, per_page),
            'has_more': repository.has_users_page(credentials.credentials, page + 1)}


@app.put('/api/v1/admin/users/{user_id}/role')
def update_admin_user_role(user_id: UUID, body: AdminUserRoleUpdate,
                           actor=Depends(current_actor),
                           credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
                           repository=Depends(get_repository)):
    if actor == 'integration':
        raise HTTPException(403, 'A user session is required to manage accounts')
    if not credentials:
        raise HTTPException(401, 'Bearer token required', headers={'WWW-Authenticate': 'Bearer'})
    user = repository.user(credentials.credentials)
    if (user.get('app_metadata') or {}).get('role') != 'admin':
        raise HTTPException(403, 'Administrator role required')
    try:
        return repository.set_user_role(credentials.credentials, str(user_id), body.role, body.expected_role)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.put('/api/v1/admin/keywords')
def save_admin_keywords(body: AdminKeywordSave, actor=Depends(current_actor),
                        credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
                        repository=Depends(get_repository)):
    if actor == 'integration':
        raise HTTPException(403, 'A user session is required to edit keywords')
    if not credentials:
        raise HTTPException(401, 'Bearer token required', headers={'WWW-Authenticate': 'Bearer'})
    user = repository.user(credentials.credentials)
    if (user.get('app_metadata') or {}).get('role') != 'admin':
        raise HTTPException(403, 'Administrator role required')

    current = repository.load_keywords()
    if current.attrs.get('revision') != body.revision:
        raise HTTPException(409, 'Keyword data changed. Reload it before saving.')
    rows = [row.model_dump(by_alias=True) for row in body.rows]
    codes = [row['kwd_no'].strip() for row in rows]
    if len(set(codes)) != len(codes):
        raise HTTPException(422, 'Keyword numbers must be unique.')
    current_codes = set(current['kwd_no'].astype(str).str.strip())
    submitted_codes = set(codes)
    if not current_codes.issubset(submitted_codes):
        raise HTTPException(422, 'This editor does not delete existing keyword rows.')
    new_codes = submitted_codes - current_codes
    if len(new_codes) > 1000:
        raise HTTPException(422, 'At most 1,000 new keyword rows can be saved at once.')
    columns = _catalog_columns(current)
    if REGISTRATION_DATE_COL not in columns and any(row.get(REGISTRATION_DATE_COL) for row in rows):
        columns.append(REGISTRATION_DATE_COL)
    current_by_code = {str(row['kwd_no']).strip(): row for row in current.to_dict('records')}
    for row, code in zip(rows, codes):
        row['kwd_no'] = code
        old = current_by_code.get(code)
        for column in columns:
            if column in DB_COLS:
                continue
            value = row.get(column)
            if not isinstance(value, str) or len(value) > 5000:
                row[column] = str(old.get(column, '')) if old else ''
        for column in list(row):
            if column not in columns:
                row.pop(column)
        if old:
            row[COUNT_COL] = str(old[COUNT_COL])
            row[LAST_COL] = str(old[LAST_COL])
        else:
            row[COUNT_COL] = '0'
            row[LAST_COL] = ''
    frame = _catalog_frame(rows, columns)
    try:
        revision = repository.save_keywords(frame, body.revision)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {'revision': revision}


@app.post('/api/v1/admin/keywords/delete')
def delete_admin_keywords(body: AdminKeywordDelete, actor=Depends(current_actor),
                          credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
                          repository=Depends(get_repository)):
    if actor == 'integration' or not credentials:
        raise HTTPException(403, 'Administrator session required')
    user = repository.user(credentials.credentials)
    if (user.get('app_metadata') or {}).get('role') != 'admin':
        raise HTTPException(403, 'Administrator role required')
    codes = [value.strip() for value in body.kwd_nos]
    if any(not value for value in codes) or len(set(codes)) != len(codes):
        raise HTTPException(422, 'Keyword numbers must be unique and non-empty.')
    current = repository.load_keywords()
    if current.attrs.get('revision') != body.revision:
        raise HTTPException(409, 'Keyword data changed. Reload it before deleting.')
    current_codes = set(current['kwd_no'].astype(str).str.strip())
    if not set(codes).issubset(current_codes):
        raise HTTPException(409, 'One or more selected keyword rows no longer exist.')
    if len(codes) >= len(current_codes):
        raise HTTPException(422, 'At least one keyword row must remain in the catalog.')
    frame = current.loc[~current['kwd_no'].astype(str).str.strip().isin(codes), _catalog_columns(current)]
    try:
        revision = repository.save_keywords(frame.fillna('').astype(str), body.revision)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {'deleted': len(codes), 'revision': revision}


@app.get('/api/v1/admin/normalization-settings')
def admin_normalization_settings(
        actor=Depends(current_actor),
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
        repository=Depends(get_repository)):
    if actor == 'integration' or not credentials:
        raise HTTPException(403, 'Administrator session required')
    user = repository.user(credentials.credentials)
    if (user.get('app_metadata') or {}).get('role') != 'admin':
        raise HTTPException(403, 'Administrator role required')
    symbols = repository.load_setting('ignored_special_symbols', None) or {}
    suffixes = repository.load_setting('ko_suffix_whitelist', {'extra_suffixes': []})
    return {
        'ignored_symbols': symbols.get('symbols') or list(MatchingConfig().ignored_symbols),
        'extra_suffixes': suffixes.get('extra_suffixes', []),
        'default_suffix_count': len(_KO_SUFFIX_WHITELIST),
    }


@app.put('/api/v1/admin/normalization-settings')
def save_admin_normalization_settings(
        body: AdminNormalizationSettings, actor=Depends(current_actor),
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
        repository=Depends(get_repository)):
    if actor == 'integration' or not credentials:
        raise HTTPException(403, 'Administrator session required')
    user = repository.user(credentials.credentials)
    if (user.get('app_metadata') or {}).get('role') != 'admin':
        raise HTTPException(403, 'Administrator role required')
    symbols = list(dict.fromkeys(body.ignored_symbols))
    if any(len(symbol) != 1 or symbol.isspace() for symbol in symbols):
        raise HTTPException(422, 'Ignored symbols must each be one non-whitespace character.')
    suffixes = list(dict.fromkeys(value.strip() for value in body.extra_suffixes if value.strip()))
    if any(len(value) > 30 for value in suffixes):
        raise HTTPException(422, 'Each suffix must be at most 30 characters.')
    repository.save_setting('ignored_special_symbols', {'symbols': symbols})
    repository.save_setting('ko_suffix_whitelist', {'extra_suffixes': suffixes})
    return {'ignored_symbols': symbols, 'extra_suffixes': suffixes}


@app.get('/api/v1/admin/approved-partials')
def admin_approved_partials(actor=Depends(current_actor),
                            credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
                            repository=Depends(get_repository)):
    if actor == 'integration' or not credentials:
        raise HTTPException(403, 'Administrator session required')
    user = repository.user(credentials.credentials)
    if (user.get('app_metadata') or {}).get('role') != 'admin':
        raise HTTPException(403, 'Administrator role required')
    rows = repository.load_keywords()[['kwd_no', DB_COLS[1]]].to_dict('records')
    rules = repository.load_setting('approved_partial_expressions_v272', {})
    return {'keywords': [{'kwd_no': row['kwd_no'], 'term': row[DB_COLS[1]]} for row in rows],
            'rules': rules}


@app.put('/api/v1/admin/approved-partials')
def save_admin_approved_partials(body: AdminApprovedPartialUpdate,
                                 actor=Depends(current_actor),
                                 credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
                                 repository=Depends(get_repository)):
    if actor == 'integration' or not credentials:
        raise HTTPException(403, 'Administrator session required')
    user = repository.user(credentials.credentials)
    if (user.get('app_metadata') or {}).get('role') != 'admin':
        raise HTTPException(403, 'Administrator role required')
    current = repository.load_keywords()
    matched = current.loc[current['kwd_no'].astype(str).str.strip() == body.kwd_no.strip()]
    if matched.empty or str(matched.iloc[0][DB_COLS[1]]) != body.term:
        raise HTTPException(409, 'Keyword changed or no longer exists. Reload the editor.')
    rules = repository.load_setting('approved_partial_expressions_v272', {})
    existing = rules.get(body.kwd_no, {})
    if existing.get('term') != body.term:
        existing_expressions = []
    else:
        existing_expressions = existing.get('expressions', [])
    if existing_expressions != body.expected_expressions:
        raise HTTPException(409, 'Approved expressions changed. Reload before saving.')
    from approved_matching import validate_expressions
    try:
        expressions = validate_expressions(body.term, body.expressions,
            load_matching_config(repository, MatchingConfig(mode='exact')))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    updated = dict(rules)
    if expressions:
        updated[body.kwd_no] = {'term': body.term, 'expressions': expressions}
    else:
        updated.pop(body.kwd_no, None)
    repository.save_setting('approved_partial_expressions_v272', updated)
    return {'kwd_no': body.kwd_no, 'term': body.term, 'expressions': expressions}


_DEFAULT_DROPDOWN_CONFIG = {
    'opt_categories': ['공통(전체)', '식품', '건강기능식품', '화장품', '공산품'],
    'opt_risks': ['1등급(사용금지)', '2등급(대체키워드사용)', '3등급(조건부사용)',
                  '4등급(사용가능)', '5등급(테스트 등급)'],
    'opt_details': ['-', '실증자료제출', '시험성적서제출', '기능입증자료제출', '표시기준준수', '전문의견서', '문헌자료제출'],
    'opt_evidences': ['-', '인체적용시험결과서', '기능성평가보고서', '임상시험결과보고서', '실험데이터요약서', '제품성분분석표', '문헌자료', '시험성적서'],
    'opt_alt_terms': ['-', '탄력', '보습', '진정', '미백', '주름개선', '자외선차단', '영양공급'],
}


@app.get('/api/v1/admin/dropdown-settings')
def admin_dropdown_settings(actor=Depends(current_actor),
                            credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
                            repository=Depends(get_repository)):
    if actor == 'integration' or not credentials:
        raise HTTPException(403, 'Administrator session required')
    user = repository.user(credentials.credentials)
    if (user.get('app_metadata') or {}).get('role') != 'admin':
        raise HTTPException(403, 'Administrator role required')
    saved = repository.load_setting('dropdown_config', None) or {}
    return {key: saved.get(key, values) for key, values in _DEFAULT_DROPDOWN_CONFIG.items()}


@app.get('/api/v1/dropdown-settings')
def dropdown_settings(actor=Depends(current_actor), repository=Depends(get_repository)):
    saved = repository.load_setting('dropdown_config', None) or {}
    return {key: saved.get(key, values) for key, values in _DEFAULT_DROPDOWN_CONFIG.items()}


@app.put('/api/v1/admin/dropdown-settings')
def save_admin_dropdown_settings(body: AdminDropdownSettings, actor=Depends(current_actor),
                                 credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
                                 repository=Depends(get_repository)):
    if actor == 'integration' or not credentials:
        raise HTTPException(403, 'Administrator session required')
    user = repository.user(credentials.credentials)
    if (user.get('app_metadata') or {}).get('role') != 'admin':
        raise HTTPException(403, 'Administrator role required')
    config = {}
    for key, values in body.model_dump().items():
        cleaned = list(dict.fromkeys(value.strip() for value in values if value.strip()))
        if key in {'opt_categories', 'opt_risks'} and not cleaned:
            raise HTTPException(422, 'Category and risk dropdowns must each contain at least one value.')
        if any(len(value) > 200 for value in cleaned):
            raise HTTPException(422, 'Dropdown values must be at most 200 characters.')
        if key in {'opt_details', 'opt_evidences', 'opt_alt_terms'} and '-' not in cleaned:
            cleaned.append('-')
        config[key] = cleaned
    repository.save_setting('dropdown_config', config)
    return config


@app.post('/api/v1/admin/keywords/upload')
async def upload_admin_keywords(
        file: UploadFile = File(...), mode: Literal['merge', 'overwrite'] = Form(...),
        revision: int = Form(..., ge=0), actor=Depends(current_actor),
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
        repository=Depends(get_repository)):
    if actor == 'integration' or not credentials:
        raise HTTPException(403, 'Administrator session required')
    user = repository.user(credentials.credentials)
    if (user.get('app_metadata') or {}).get('role') != 'admin':
        raise HTTPException(403, 'Administrator role required')
    name = str(file.filename or '').lower()
    content = await file.read(20 * 1024 * 1024 + 1)
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(413, 'Keyword upload must be 20 MB or smaller.')
    import io
    import pandas as pd
    if name.endswith('.csv'):
        incoming = None
        for encoding in ('utf-8-sig', 'utf-8', 'cp949', 'euc-kr', 'latin1'):
            try:
                incoming = pd.read_csv(io.BytesIO(content), dtype=str, encoding=encoding).fillna('')
                break
            except Exception:
                continue
        if incoming is None:
            raise HTTPException(422, 'Could not read the CSV file. Check its encoding and headers.')
    elif name.endswith('.xlsx'):
        try:
            incoming = pd.read_excel(io.BytesIO(content), dtype=str).fillna('')
        except Exception as exc:
            raise HTTPException(422, 'Could not read the XLSX file. Check its worksheet and headers.') from exc
    else:
        raise HTTPException(422, 'Upload a CSV or XLSX file.')

    aliases = {
        'kwd_no': DB_COLS[0], 'keyword_no': DB_COLS[0], '키워드no': DB_COLS[0], '키워드 no': DB_COLS[0],
        '키워드명': DB_COLS[1], 'term': DB_COLS[1], '상품카테고리': DB_COLS[2], 'category': DB_COLS[2],
        '리스크 등급': DB_COLS[3], 'risk': DB_COLS[3], '대체키워드': DB_COLS[4],
        '대체키워드명': DB_COLS[4], 'alternative': DB_COLS[4],
        '리스크 등급별 세부 심의기준': DB_COLS[5], '세부 심의기준': DB_COLS[5], 'criteria': DB_COLS[5],
        '증빙자료유형': DB_COLS[6], '증빙자료': DB_COLS[6], 'evidence_type': DB_COLS[6], 'evidence': DB_COLS[6],
        COUNT_COL.lower(): COUNT_COL, 'hit_count': COUNT_COL,
        LAST_COL.lower(): LAST_COL, '마지막 검색일자': LAST_COL, 'last_hit': LAST_COL,
    }
    source = incoming.copy()
    source.columns = [str(column).strip().lower() for column in source.columns]
    source = source.rename(columns={column: aliases[column] for column in source.columns if column in aliases})
    if source.columns.duplicated().any():
        raise HTTPException(422, 'Upload has multiple columns for the same keyword field.')
    for column in DB_COLS:
        if column not in source:
            source[column] = '0' if column == COUNT_COL else ''
    source = source[DB_COLS].fillna('').astype(str).apply(lambda col: col.str.strip())
    source = source.loc[~source[DB_COLS].apply(lambda row: all(not value for value in row), axis=1)]
    if source.empty:
        raise HTTPException(422, 'The upload contains no keyword rows.')
    missing = source.loc[(source[DB_COLS[1]] == '') | (source[DB_COLS[2]] == '')]
    if not missing.empty:
        raise HTTPException(422, 'Every uploaded row needs a keyword name and category.')

    current = repository.load_keywords()
    if current.attrs.get('revision') != revision:
        raise HTTPException(409, 'Keyword data changed. Reload it before importing.')
    rows = current.to_dict('records')
    assigned = []
    for item in source.to_dict('records'):
        if not item[DB_COLS[0]]:
            item[DB_COLS[0]] = _next_keyword_code(item[DB_COLS[2]], rows + assigned)
        assigned.append(item)
    before = len(assigned)
    deduplicated = {item[DB_COLS[0]]: item for item in assigned}
    upload_rows = list(deduplicated.values())
    removed_duplicates = before - len(upload_rows)
    if mode == 'overwrite' and not upload_rows:
        raise HTTPException(422, 'The upload contains no keyword rows.')
    current_by_code = {str(row[DB_COLS[0]]).strip(): row for row in rows}
    columns = _catalog_columns(current)
    for item in upload_rows:
        old = current_by_code.get(item[DB_COLS[0]])
        if old:
            item[COUNT_COL] = str(old[COUNT_COL])
            item[LAST_COL] = str(old[LAST_COL])
            for column in columns:
                if column not in DB_COLS:
                    item[column] = str(old.get(column, ''))
        else:
            item[COUNT_COL] = item[COUNT_COL] or '0'
    if mode == 'merge':
        replaced = {item[DB_COLS[0]] for item in upload_rows}
        rows = [row for row in rows if str(row[DB_COLS[0]]).strip() not in replaced]
        result_rows = rows + upload_rows
    else:
        result_rows = upload_rows
    frame = _catalog_frame(result_rows, columns)
    try:
        new_revision = repository.save_keywords(frame, revision)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {'added_count': len(upload_rows), 'dedup_removed': removed_duplicates,
            'revision': new_revision, 'total': len(result_rows)}


@app.get('/api/v1/admin/keywords/template.xlsx')
def download_admin_keyword_template(actor=Depends(current_actor),
                                    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
                                    repository=Depends(get_repository)):
    if actor == 'integration' or not credentials:
        raise HTTPException(403, 'Administrator session required')
    user = repository.user(credentials.credentials)
    if (user.get('app_metadata') or {}).get('role') != 'admin':
        raise HTTPException(403, 'Administrator role required')
    import io
    import pandas as pd
    buffer = io.BytesIO()
    try:
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            pd.DataFrame(columns=DB_COLS).to_excel(writer, sheet_name='keywords_template', index=False)
    except ImportError as exc:
        raise HTTPException(503, 'XLSX template export is unavailable in this API environment.') from exc
    return Response(content=buffer.getvalue(),
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': 'attachment; filename="keyword_template.xlsx"'})


@app.get('/api/v1/analyses/{analysis_id}')
def get_analysis(analysis_id: UUID, actor=Depends(current_actor),
                 repository=Depends(get_repository)):
    result = repository.previous_analysis(str(analysis_id), actor)
    if result is None:
        raise HTTPException(404, 'Analysis not found')
    return result


@app.get('/api/v1/keywords', dependencies=[Depends(current_actor)])
def keywords(offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500),
             q: str = Query('', max_length=200), category: str = Query('', max_length=100),
             risk: str = Query('', max_length=100), evidence_type: str = Query('', max_length=100),
             repository=Depends(get_repository)):
    df = repository.load_keywords().sort_values('kwd_no', kind='stable')
    if q and not df.empty:
        searchable = df[['kwd_no', '키워드명', '대체키워드']].fillna('').astype(str).agg('\n'.join, axis=1)
        df = df[searchable.str.contains(q, regex=False, case=False)]
    if category:
        df = df[df['상품카테고리'].astype(str).str.strip() == category]
    if risk:
        df = df[df['리스크 등급'].astype(str).str.strip() == risk]
    if evidence_type:
        df = df[df['증빙자료유형'].astype(str).str.strip() == evidence_type]
    return {'total': len(df), 'revision': df.attrs.get('revision'),
            'columns': [str(column) for column in df.columns],
            'items': df.iloc[offset:offset + limit].to_dict('records')}


@app.get('/api/v2/matching-rules')
def matching_rules(actor=Depends(current_actor), repository=Depends(get_repository)):
    """Read-only common matching rules for the analysis screen's summary and evidence text."""
    config = load_matching_config(repository, MatchingConfig())
    return {'ignored_symbols': list(config.ignored_symbols),
            'approved_partials': repository.load_setting('approved_partial_expressions_v272', {})}


@app.get('/api/v1/reports/top-keywords', dependencies=[Depends(current_actor)],
         response_model=TopKeywordsResponse)
def top_keywords(days: int = Query(7, ge=1, le=366),
                 limit: int = Query(10, ge=1, le=100),
                 start_date: date | None = None, end_date: date | None = None,
                 repository=Depends(get_repository)):
    if (start_date is None) != (end_date is None):
        raise HTTPException(422, 'Both start_date and end_date are required.')
    if start_date is not None and end_date is not None:
        if end_date < start_date:
            raise HTTPException(422, 'end_date must be on or after start_date.')
        items = repository.report_range(start_date.isoformat(), end_date.isoformat(), limit)
    else:
        items = repository.report(days, limit)

    # The Streamlit report joins each ranked hit count to the complete keyword
    # row. Keep the summary fields for existing clients and add that row from
    # one catalog snapshot so the React table and CSV use the same data.
    snapshot = repository.load_keywords()
    by_code = {str(row.get('kwd_no') or '').strip(): row
               for row in snapshot.to_dict('records')}
    enriched = []
    for rank, item in enumerate(items, start=1):
        row = by_code.get(str(item.get('kwd_no') or '').strip(), {})
        enriched.append({**item, 'search_rank': rank,
                         'keyword_data': {str(key): str(value or '').strip()
                                          for key, value in row.items()}})
    return {'items': enriched, 'keyword_revision': snapshot.attrs.get('revision')}


@app.post('/api/v1/admin/reports/reset/{scope}')
def reset_report_data(scope: Literal['all', 'last-7-days'], actor=Depends(current_actor),
                      credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
                      repository=Depends(get_repository)):
    if actor == 'integration' or not credentials:
        raise HTTPException(403, 'Administrator session required')
    user = repository.user(credentials.credentials)
    if (user.get('app_metadata') or {}).get('role') != 'admin':
        raise HTTPException(403, 'Administrator role required')
    if scope == 'all':
        repository.reset_counts()
        return {'scope': scope, 'reset': True}
    return {'scope': scope, 'removed': repository.reset_week()}


@app.post('/api/v1/regulation/questions')
def regulation_question(body: RegulationQuestionRequest, actor=Depends(current_actor),
                        repository=Depends(get_repository)):
    try:
        if actor == 'integration' and body.thread_id:
            raise HTTPException(403, 'A user session is required for conversations')
        request_data = body.model_dump()
        result = answer_regulation_question(request_data, repository)
        record_usage(repository, result.pop('openai_usage', None))
        if actor != 'integration':
            result['thread_id'] = save_turn(repository, str(body.thread_id) if body.thread_id else None,
                                            actor, body.scope, body.query, result['answer'],
                                            result.get('sources', []))
        try:
            result['usage_summary'] = _openai_usage_summary(repository)
        except Exception:
            logger.exception('OpenAI usage summary unavailable')
            result['usage_summary'] = {'available': False}
        return result
    except HTTPException:
        raise
    except RegulationSearchError as exc:
        raise HTTPException(502, str(exc)) from exc
    except requests.RequestException as exc:
        raise HTTPException(502, 'Regulation evidence lookup is temporarily unavailable') from exc
    except Exception as exc:
        logger.exception('Regulation question failed')
        raise HTTPException(502, 'Regulation search failed') from exc


def _openai_usage_summary(repository):
    from decimal import Decimal

    month_start = current_month_start()
    row = repository.load_openai_usage(month_start)
    budget = monthly_budget()
    cost_complete = bool(row.get('cost_complete', True))
    estimated_cost = Decimal(str(row.get('estimated_cost_usd') or 0)) if cost_complete else None
    remaining = max(Decimal(0), budget - estimated_cost) if budget is not None and estimated_cost is not None else None
    return {
        'available': True,
        'month_start': month_start,
        'request_count': int(row.get('request_count') or 0),
        'input_tokens': int(row.get('input_tokens') or 0),
        'output_tokens': int(row.get('output_tokens') or 0),
        'total_tokens': int(row.get('input_tokens') or 0) + int(row.get('output_tokens') or 0),
        'estimated_cost_usd': float(estimated_cost) if estimated_cost is not None else None,
        'budget_usd': float(budget) if budget is not None else None,
        'remaining_budget_usd': float(remaining) if remaining is not None else None,
        'cost_complete': cost_complete,
    }


@app.get('/api/v1/regulation/usage')
def regulation_usage(actor=Depends(current_actor), repository=Depends(get_repository)):
    try:
        return _openai_usage_summary(repository)
    except Exception as exc:
        logger.exception('OpenAI usage summary unavailable')
        return {'available': False}


def regulation_admin(actor, credentials, repository):
    if actor == 'integration' or not credentials:
        raise HTTPException(403, 'Administrator session required')
    user = repository.user(credentials.credentials)
    if (user.get('app_metadata') or {}).get('role') != 'admin':
        raise HTTPException(403, 'Administrator role required')
    return user['id']


@app.get('/api/v1/admin/regulation/documents')
def regulation_documents(actor=Depends(current_actor),
                         credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
                         repository=Depends(get_repository)):
    regulation_admin(actor, credentials, repository)
    return {'items': list_documents(repository)}


@app.post('/api/v1/admin/regulation/documents')
async def upload_regulation_document(
        category: str = Form('', max_length=100),
        effective_from: date | None = Form(None), effective_to: date | None = Form(None),
        replace_document_id: UUID | None = Form(None),
        new_document: bool = Form(False),
        file: UploadFile = File(...), actor=Depends(current_actor),
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
        repository=Depends(get_repository)):
    admin_id = regulation_admin(actor, credentials, repository)
    filename = os.path.basename(file.filename or '')
    if not filename.strip():
        raise HTTPException(422, '문서 파일명을 확인하세요.')
    payload = await file.read(MAX_DOCUMENT_BYTES + 1)
    try:
        text = extract_text(filename, payload)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    content_hash = hashlib.sha256(payload).hexdigest()
    if new_document and replace_document_id:
        raise HTTPException(422, '새 문서 등록과 기존 문서 교체를 동시에 선택할 수 없습니다.')
    if new_document:
        source_key = 'doc-' + secrets.token_hex(12)
    elif replace_document_id:
        replacement = document_by_id(repository, str(replace_document_id))
        if replacement is None:
            raise HTTPException(404, '교체할 기존 문서를 찾을 수 없습니다.')
        source_key = replacement['source_key']
    else:
        exact = documents_with_hash(repository, content_hash)
        keys = {row['source_key'] for row in exact}
        if len(keys) > 1:
            raise HTTPException(409, '같은 내용의 문서가 여러 개 있습니다. 교체할 문서를 선택하세요.')
        source_key = next(iter(keys)) if keys else 'doc-' + content_hash[:24]
    now = datetime.now(ZoneInfo('Asia/Seoul'))
    version = now.strftime('%Y%m%d-%H%M%S-%f')
    title = os.path.splitext(filename)[0].strip()[:200] or '문서'
    previous = document_versions(repository, source_key)
    dates_supplied = effective_from is not None or effective_to is not None
    approved_starts = [date.fromisoformat(row['effective_from']) for row in previous
                       if row['status'] == 'approved']
    latest_approved_start = max(approved_starts, default=None)
    if effective_from is None:
        effective_from = max(now.date(), latest_approved_start or now.date())
    elif latest_approved_start and effective_from < latest_approved_start:
        raise HTTPException(422, '새 문서의 시행일은 현재 승인본의 시행일보다 빠를 수 없습니다.')
    if effective_to and effective_to < effective_from:
        raise HTTPException(422, '종료일은 시행일보다 빠를 수 없습니다.')
    same = next((row for row in previous if row['content_sha256'] == content_hash
                 and row['category'] == category.strip()
                 and (not dates_supplied or (row['effective_from'] == effective_from.isoformat()
                      and row['effective_to'] == (effective_to.isoformat() if effective_to else None)))
                 and row['status'] in {'draft', 'approved'}), None)
    if same:
        return {'id': same['id'], 'status': same['status'], 'unchanged': True}
    try:
        document_id = create_document(repository, source_key=source_key,
            version=version, title=title, category=category.strip(),
            effective_from=effective_from, effective_to=effective_to,
            filename=filename, payload=payload, actor_id=admin_id, text=text)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {'id': document_id, 'status': 'draft'}


@app.post('/api/v1/admin/regulation/documents/matches')
async def match_regulation_document(file: UploadFile = File(...), actor=Depends(current_actor),
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
        repository=Depends(get_repository)):
    regulation_admin(actor, credentials, repository)
    payload = await file.read(MAX_DOCUMENT_BYTES + 1)
    try:
        text = extract_text(file.filename or '', payload)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    exact = documents_with_hash(repository, hashlib.sha256(payload).hexdigest())
    try:
        candidates = [] if exact else similar_document_candidates(repository, text)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except (requests.RequestException, RuntimeError, KeyError) as exc:
        logger.warning('Regulation document similarity lookup failed', exc_info=True)
        raise HTTPException(503, '기존 문서 비교에 실패했습니다. 잠시 후 다시 시도하세요.') from exc
    return {'exact': exact, 'candidates': candidates}


@app.post('/api/v1/admin/regulation/documents/{document_id}/approve')
def approve_regulation_document(document_id: UUID, actor=Depends(current_actor),
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
        repository=Depends(get_repository)):
    admin_id = regulation_admin(actor, credentials, repository)
    approved_id = repository.rpc('approve_regulation_document',
                                 p_id=str(document_id), p_approver=admin_id)
    return {'id': approved_id, 'status': 'approved'}


@app.get('/api/v1/admin/regulation/documents/{document_id}')
def preview_regulation_document(document_id: UUID, actor=Depends(current_actor),
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
        repository=Depends(get_repository)):
    regulation_admin(actor, credentials, repository)
    document = load_document_preview(repository, str(document_id))
    if document is None:
        raise HTTPException(404, 'Document not found')
    return document


@app.post('/api/v1/admin/regulation/documents/{document_id}/embeddings')
def build_regulation_embeddings(document_id: UUID, actor=Depends(current_actor),
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
        repository=Depends(get_repository)):
    regulation_admin(actor, credentials, repository)
    try:
        count = reindex_embeddings(repository, str(document_id))
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    except requests.HTTPError as exc:
        upstream_status = exc.response.status_code if exc.response is not None else 502
        if upstream_status == 429:
            raise HTTPException(
                429,
                'OpenAI 임베딩 요청 한도에 도달했습니다. 잠시 후 다시 시도하거나 '
                'OpenAI 프로젝트의 사용 한도와 크레딧을 확인하세요.',
            ) from exc
        raise HTTPException(
            502, f'OpenAI 임베딩 요청이 실패했습니다 (HTTP {upstream_status}).'
        ) from exc
    except requests.RequestException as exc:
        raise HTTPException(502, 'OpenAI 임베딩 API에 연결하지 못했습니다.') from exc
    return {'id': str(document_id), 'embedded_chunks': count}


@app.delete('/api/v1/admin/regulation/documents/{document_id}')
def delete_regulation_document(document_id: UUID, actor=Depends(current_actor),
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
        repository=Depends(get_repository)):
    regulation_admin(actor, credentials, repository)
    if not repository.rpc('delete_regulation_document', p_id=str(document_id)):
        raise HTTPException(404, 'Document not found')
    return {'id': str(document_id), 'deleted': True}


@app.get('/api/v1/regulation/threads')
def regulation_threads(actor=Depends(current_actor), repository=Depends(get_repository)):
    if actor == 'integration':
        raise HTTPException(403, 'A user session is required')
    return {'items': list_threads(repository, actor)}


@app.get('/api/v1/regulation/threads/{thread_id}')
def regulation_thread(thread_id: UUID, actor=Depends(current_actor),
                      repository=Depends(get_repository)):
    if actor == 'integration':
        raise HTTPException(403, 'A user session is required')
    messages = load_thread(repository, actor, str(thread_id))
    if messages is None:
        raise HTTPException(404, 'Conversation not found')
    return {'id': str(thread_id), 'messages': messages}


@app.delete('/api/v1/regulation/threads/{thread_id}')
def delete_regulation_thread(thread_id: UUID, actor=Depends(current_actor),
                             repository=Depends(get_repository)):
    if actor == 'integration':
        raise HTTPException(403, 'A user session is required')
    if not delete_thread(repository, actor, str(thread_id)):
        raise HTTPException(404, 'Conversation not found')
    return {'id': str(thread_id), 'deleted': True}
