"""Run: python -m uvicorn api:app --host 0.0.0.0 --port 8000"""
import os
import secrets
import logging
from typing import Literal
from uuid import UUID

import requests
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field

from app_config import configure, cloud_enabled
from repository import ConflictError, StorageError, SupabaseRepository
from service import analyze, analyze_current
from matching_engine import DB_COLS
from regulation_assistant import RegulationSearchError, answer_regulation_question

configure()
app = FastAPI(title='Keyword Risk Analyzer API', version='1.0.0',
              docs_url='/docs' if os.getenv('API_DOCS_ENABLED') == 'true' else None,
              redoc_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in os.getenv(
        'API_CORS_ORIGINS', 'http://localhost:5173,http://127.0.0.1:5173'
    ).split(',') if origin.strip()],
    allow_methods=['GET', 'POST', 'PUT'],
    allow_headers=['Authorization', 'Content-Type'],
)
bearer = HTTPBearer(auto_error=False)
logger = logging.getLogger(__name__)


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


class RegulationQuestionRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    direction: Literal['keyword_to_law', 'law_to_keywords']
    query: str = Field(min_length=2, max_length=500)
    context_text: str = Field(default='', max_length=20000)
    category: str = Field(default='', max_length=100)


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
    request_detail: str = Field(min_length=1, max_length=4000)


class KeywordRequestUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    status: Literal['대기', '검토중', '처리완료']
    admin_reply: str = Field(default='', max_length=4000)


class AdminUserRoleUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    role: Literal['admin', 'member']
    expected_role: Literal['admin', 'member'] | None = None


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


@app.post('/api/v2/analyses')
def create_current_analysis(body: CurrentAnalysisRequest, actor=Depends(current_actor),
                            repository=Depends(get_repository)):
    if actor == 'integration':
        raise HTTPException(403, 'A user session is required to record an analysis')
    return analyze_current(repository, body.model_dump(mode='json'), actor)


@app.get('/api/v1/unmatched-terms')
def unmatched_terms(offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=100),
                    search: str = Query('', max_length=200),
                    sort: Literal['occurrences', 'registered'] = 'occurrences',
                    actor=Depends(current_actor), repository=Depends(get_repository)):
    return repository.load_unmatched_terms(offset, limit, search, sort)


@app.get('/api/v1/unmatched-terms/export')
def export_unmatched_terms(actor=Depends(current_actor), repository=Depends(get_repository)):
    return {'items': repository.export_unmatched_terms()}


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


@app.get('/api/v1/keyword-requests')
def keyword_requests(actor=Depends(current_actor),
                     credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
                     repository=Depends(get_repository)):
    if actor == 'integration':
        raise HTTPException(403, 'A user session is required to view keyword requests')
    if not credentials:
        raise HTTPException(401, 'Bearer token required', headers={'WWW-Authenticate': 'Bearer'})
    return {'items': repository.load_keyword_requests(credentials.credentials, limit=100)}


@app.post('/api/v1/keyword-requests')
def submit_keyword_request(body: KeywordRequestSubmission, actor=Depends(current_actor),
                           credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
                           repository=Depends(get_repository)):
    if actor == 'integration':
        raise HTTPException(403, 'A user session is required to submit keyword requests')
    if not credentials:
        raise HTTPException(401, 'Bearer token required', headers={'WWW-Authenticate': 'Bearer'})
    detail = body.request_detail.strip()
    if not detail:
        raise HTTPException(422, 'Request details must contain text')
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
        return repository.submit_keyword_request(payload, credentials.credentials)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


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
    if q:
        searchable = df[['kwd_no', '키워드명', '대체키워드']].fillna('').astype(str).agg('\n'.join, axis=1)
        df = df[searchable.str.contains(q, regex=False, case=False)]
    if category:
        df = df[df['상품카테고리'].astype(str).str.strip() == category]
    if risk:
        df = df[df['리스크 등급'].astype(str).str.strip() == risk]
    if evidence_type:
        df = df[df['증빙자료유형'].astype(str).str.strip() == evidence_type]
    return {'total': len(df), 'revision': df.attrs.get('revision'),
            'items': df.iloc[offset:offset + limit].to_dict('records')}


@app.get('/api/v1/reports/top-keywords', dependencies=[Depends(current_actor)])
def top_keywords(days: int = Query(7, ge=1, le=366),
                 limit: int = Query(10, ge=1, le=100), repository=Depends(get_repository)):
    return {'items': repository.report(days, limit)}


@app.post('/api/v1/regulation/questions')
def regulation_question(body: RegulationQuestionRequest, actor=Depends(current_actor),
                        repository=Depends(get_repository)):
    try:
        return answer_regulation_question(body.model_dump(), repository)
    except RegulationSearchError as exc:
        raise HTTPException(502, str(exc)) from exc
    except requests.RequestException as exc:
        raise HTTPException(502, 'Regulation evidence lookup is temporarily unavailable') from exc
    except Exception as exc:
        logger.exception('Regulation question failed')
        raise HTTPException(502, 'Regulation search failed') from exc
