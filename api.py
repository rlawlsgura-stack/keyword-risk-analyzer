"""Run: python -m uvicorn api:app --host 0.0.0.0 --port 8000"""
import os
import secrets
from typing import Literal
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field

from app_config import configure, cloud_enabled
from repository import ConflictError, StorageError, SupabaseRepository
from service import analyze

configure()
app = FastAPI(title='Keyword Risk Analyzer API', version='1.0.0',
              docs_url='/docs' if os.getenv('API_DOCS_ENABLED') == 'true' else None,
              redoc_url=None)
bearer = HTTPBearer(auto_error=False)


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


@app.get('/api/v1/analyses/{analysis_id}')
def get_analysis(analysis_id: UUID, actor=Depends(current_actor),
                 repository=Depends(get_repository)):
    result = repository.previous_analysis(str(analysis_id), actor)
    if result is None:
        raise HTTPException(404, 'Analysis not found')
    return result


@app.get('/api/v1/keywords', dependencies=[Depends(current_actor)])
def keywords(offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500),
             q: str = Query('', max_length=200), repository=Depends(get_repository)):
    df = repository.load_keywords().sort_values('kwd_no', kind='stable')
    if q:
        df = df[df['키워드명'].str.contains(q, regex=False, case=False)]
    return {'total': len(df), 'revision': df.attrs.get('revision'),
            'items': df.iloc[offset:offset + limit].to_dict('records')}


@app.get('/api/v1/reports/top-keywords', dependencies=[Depends(current_actor)])
def top_keywords(days: int = Query(7, ge=1, le=366),
                 limit: int = Query(10, ge=1, le=100), repository=Depends(get_repository)):
    return {'items': repository.report(days, limit)}
