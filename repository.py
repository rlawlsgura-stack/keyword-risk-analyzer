"""Server-only Supabase REST access. No mutable user session is shared."""
import os

import pandas as pd
import requests

from matching_engine import DB_COLS

COUNT_COL = '키워드 조회 수(누적카운트)'
LAST_COL = '마지막 출력일자'


class StorageError(RuntimeError):
    pass


class ConflictError(StorageError):
    pass


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

    def refresh(self, refresh_token):
        return self.request('POST', '/auth/v1/token?grant_type=refresh_token',
                            {'refresh_token': refresh_token})

    def user(self, token):
        user = self.request('GET', '/auth/v1/user', token=token)
        if user.get('is_anonymous') or not user.get('id'):
            raise PermissionError('사내 사용자 계정으로 로그인하세요.')
        return user

    def logout(self, token):
        self.request('POST', '/auth/v1/logout', token=token)
