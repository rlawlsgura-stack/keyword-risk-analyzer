"""Server-only Supabase REST access. No mutable user session is shared."""
import os
from uuid import UUID

import pandas as pd
import requests
from urllib.parse import urlencode

from matching_engine import DB_COLS

COUNT_COL = '키워드 조회 수(누적카운트)'
LAST_COL = '마지막 출력일자'


class StorageError(RuntimeError):
    pass


class ConflictError(StorageError):
    pass


def _user_summary(user):
    """Expose only fields used by the application administrator screen."""
    return {'id': user['id'], 'email': user.get('email', ''),
            'role': (user.get('app_metadata') or {}).get('role'),
            'email_confirmed': bool(user.get('email_confirmed_at'))}


class SupabaseRepository:
    def __init__(self):
        self.url = os.getenv('SUPABASE_URL', '').rstrip('/')
        self.key = os.getenv('SUPABASE_SECRET_KEY', '')
        if not self.url.startswith('https://') or not self.key:
            raise StorageError('SUPABASE_URL and SUPABASE_SECRET_KEY are required')

    def request(self, method, path, payload=None, token=None, prefer=None):
        headers = {'apikey': self.key, 'Content-Type': 'application/json'}
        if prefer:
            headers['Prefer'] = prefer
        # Modern secret keys are API keys, not bearer JWTs.
        if token:
            headers['Authorization'] = 'Bearer ' + token
        elif not self.key.startswith('sb_secret_'):
            headers['Authorization'] = 'Bearer ' + self.key
        try:
            response = requests.request(method, self.url + path, headers=headers,
                                        json=payload, timeout=(5, 30))
        except requests.RequestException as exc:
            raise StorageError('Supabase connection failed') from exc
        if response.status_code >= 400:
            try:
                body = response.json()
            except ValueError:
                body = {}
            if path.split('?', 1)[0] == '/auth/v1/signup':
                detail = body.get('msg') or body.get('message') or body.get('error_description')
                code = body.get('code') or body.get('error_code')
                diagnostic = ': '.join(str(value) for value in (code, detail) if value)
                if diagnostic:
                    diagnostic = ' '.join(diagnostic.split())[:240]
                    raise StorageError(
                        f'Supabase request failed ({response.status_code}): {diagnostic}')
            if body.get('code') in {'40001', '23505'}:
                raise ConflictError('데이터가 변경되었습니다. 새로 불러온 후 다시 시도하세요.')
            if response.status_code in {401, 403}:
                raise PermissionError('인증 또는 데이터 접근 권한을 확인하세요.')
            raise StorageError(f'Supabase request failed ({response.status_code})')
        return response.json() if response.content else None

    def rpc(self, name, **params):
        return self.request('POST', '/rest/v1/rpc/kra_' + name, params)

    def load_keywords(self):
        # One JSON snapshot avoids the Data API's default 1,000-row limit and
        # keeps rows, column order and revision from the same DB statement.
        snapshot = self.rpc('snapshot')
        columns = snapshot['columns'] or DB_COLS
        df = pd.DataFrame(snapshot['rows'], columns=columns).fillna('').astype(str)
        for col in DB_COLS:
            if col not in df:
                df[col] = '0' if col == COUNT_COL else ''
        df.attrs['revision'] = snapshot['revision']
        return df

    def save_keywords(self, df, revision):
        if revision is None:
            raise ConflictError('편집 전 데이터를 먼저 불러오세요.')
        ids = df['kwd_no'].astype(str).str.strip()
        if ids.eq('').any() or ids.duplicated().any():
            raise ValueError('kwd_no는 비어 있거나 중복될 수 없습니다.')
        return self.rpc('save_keywords', p_rows=df.fillna('').astype(str).to_dict('records'),
                        p_columns=list(df.columns), p_revision=revision)

    def load_setting(self, name, default):
        value = self.rpc('get_setting', p_name=name)
        return default if value is None else value

    def save_setting(self, name, value):
        return self.rpc('set_setting', p_name=name, p_value=value)

    def record_analysis(self, analysis_id, fingerprint, actor, revision, result):
        return self.rpc('record_analysis', p_id=analysis_id, p_fingerprint=fingerprint,
                        p_actor=actor, p_revision=revision, p_result=result)

    def previous_analysis(self, analysis_id, actor, fingerprint=None):
        return self.rpc('get_analysis', p_id=analysis_id, p_actor=actor,
                        p_fingerprint=fingerprint)

    def load_hits(self):
        # Weekly UI reads only its report window, using indexed server filters.
        rows = self.rpc('recent_hits', p_days=7)
        return pd.DataFrame(rows, columns=['ts', 'kwd_no'])

    def report(self, days=7, limit=10):
        return self.rpc('top_keywords', p_days=days, p_limit=limit)

    def reset_counts(self):
        self.rpc('reset_counts')

    def reset_week(self):
        return self.rpc('reset_week')

    def login(self, email, password):
        return self.request('POST', '/auth/v1/token?grant_type=password',
                            {'email': email, 'password': password})

    def sign_up(self, email, password, redirect_to):
        query = urlencode({'redirect_to': redirect_to})
        return self.request('POST', '/auth/v1/signup?' + query,
                            {'email': email.strip(), 'password': password})

    def request_password_reset(self, email, redirect_to):
        query = urlencode({'redirect_to': redirect_to})
        return self.request('POST', '/auth/v1/recover?' + query,
                            {'email': email.strip()})

    def update_password(self, access_token, password):
        return self.request('PUT', '/auth/v1/user', {'password': password},
                            token=access_token)

    def refresh(self, refresh_token):
        return self.request('POST', '/auth/v1/token?grant_type=refresh_token',
                            {'refresh_token': refresh_token})

    def user(self, token):
        user = self.request('GET', '/auth/v1/user', token=token)
        if user.get('is_anonymous') or not user.get('id'):
            raise PermissionError('사내 사용자 계정으로 로그인하세요.')
        return user

    def _require_app_admin(self, token):
        # Validate against Auth for each operation, never a UI flag or decoded JWT.
        actor = self.user(token)
        if (actor.get('app_metadata') or {}).get('role') != 'admin':
            raise PermissionError('사용자 관리는 관리자만 이용할 수 있습니다.')
        return actor

    def list_users(self, token, page=1):
        self._require_app_admin(token)
        if not isinstance(page, int) or not 1 <= page <= 100000:
            raise ValueError('올바른 페이지 번호를 입력하세요.')
        result = self.request('GET', f'/auth/v1/admin/users?page={page}&per_page=50')
        return [_user_summary(user) for user in result['users']]

    def set_user_role(self, token, user_id, role, expected_role):
        if role not in {'admin', 'member'}:
            raise ValueError('역할은 admin 또는 member만 지정할 수 있습니다.')
        user_id = str(UUID(str(user_id)))
        actor = self._require_app_admin(token)
        if user_id == actor['id'] and role != 'admin':
            raise ValueError('자신의 관리자 권한은 해제할 수 없습니다.')
        path = '/auth/v1/admin/users/' + user_id
        target = self.request('GET', path)
        if target.get('is_anonymous'):
            raise ValueError('익명 계정에는 앱 역할을 부여할 수 없습니다.')
        # ponytail: this preflight check is not atomic; serialize edits if concurrent admins need it.
        if (target.get('app_metadata') or {}).get('role') != expected_role:
            raise ConflictError('이 계정의 역할이 변경되었습니다. 목록을 새로 불러오세요.')
        # Auth Admin merges this metadata patch, preserving provider and other keys.
        # Always use the server key here; the actor's token is only used above.
        updated = self.request('PUT', path, {'app_metadata': {'role': role}})
        if updated.get('id') != user_id or (updated.get('app_metadata') or {}).get('role') != role:
            raise StorageError('역할 변경 결과를 확인할 수 없습니다. 목록을 새로 불러오세요.')
        return _user_summary(updated)

    def logout(self, token):
        self.request('POST', '/auth/v1/logout', token=token)
