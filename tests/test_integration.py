from dataclasses import asdict
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

import pandas as pd
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest

import api
from matching_engine import DB_COLS, MatchingConfig, find_matches_nlp
from repository import ConflictError, SupabaseRepository
from service import MODES, analyze

ROOT = Path(__file__).resolve().parents[1]


class MemoryRepository:
    def __init__(self):
        self.df = pd.DataFrame([dict(zip(DB_COLS, [
            'A001', '필러', '화장품', '1등급(사용금지)', '-', '-', '-', '0', ''
        ]))])
        self.df.attrs['revision'] = 1
        self.runs = {}
        self.records = 0

    def load_keywords(self):
        return self.df.copy()

    def load_setting(self, name, default):
        return default

    def previous_analysis(self, analysis_id, actor, fingerprint=None):
        item = self.runs.get(analysis_id)
        if item and (item[0] != actor or (fingerprint and item[1] != fingerprint)):
            raise ConflictError('conflict')
        return item[2] if item else None

    def record_analysis(self, analysis_id, fingerprint, actor, revision, result):
        previous = self.previous_analysis(analysis_id, actor, fingerprint)
        if previous:
            return previous
        self.records += 1
        self.runs[analysis_id] = (actor, fingerprint, result)
        return result

    def load_hits(self):
        return pd.DataFrame(columns=['ts', 'kwd_no'])

    def user(self, token):
        if token != 'valid-user-token':
            raise PermissionError('invalid')
        return {'id': 'user-1', 'email': 'member@example.test',
                'app_metadata': {'role': 'member'}}


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.repository = MemoryRepository()

    def test_service_preserves_all_engine_modes_and_post_filters(self):
        for mode, label in MODES.items():
            request = {'text': '필러와 필러', 'mode': mode, 'exact_relaxed': True}
            result = analyze(self.repository, request, 'user-1')
            expected = find_matches_nlp(request['text'], self.repository.df,
                                       match_mode=label, exact_relaxed=True,
                                       config=MatchingConfig())
            self.assertEqual(result['matches'], [asdict(m) for m in expected])
        result = analyze(self.repository, {**request, 'categories': ['식품']}, 'user-1')
        self.assertEqual(result['matches'], [])

    def test_recording_is_opt_in_and_same_id_is_idempotent(self):
        request = {'text': '필러 필러', 'mode': 'exact',
                   'analysis_id': str(uuid4())}
        analyze(self.repository, request, 'user-1')
        self.assertEqual(self.repository.records, 0)
        first = analyze(self.repository, {**request, 'record': True}, 'user-1')
        second = analyze(self.repository, {**request, 'record': True}, 'user-1')
        self.assertEqual(first, second)
        self.assertEqual(first['unique_keywords'], ['A001'])
        self.assertEqual(self.repository.records, 1)
        with self.assertRaises(ConflictError):
            analyze(self.repository, {**request, 'record': True, 'text': 'changed'}, 'user-1')

    def test_api_auth_validation_and_private_results(self):
        api.app.dependency_overrides[api.get_repository] = lambda: self.repository
        try:
            with patch.dict(os.environ, {'API_ACCESS_TOKEN': 'test-integration-key'}), \
                 patch('api.SupabaseRepository', return_value=self.repository), \
                 TestClient(api.app) as client:
                self.assertEqual(client.get('/healthz').status_code, 200)
                self.assertEqual(client.get('/api/v1/keywords').status_code, 401)
                self.assertEqual(client.get('/api/v1/keywords',
                    headers={'Authorization': 'Bearer invalid'}).status_code, 401)
                headers = {'Authorization': 'Bearer valid-user-token'}
                self.assertEqual(client.post('/api/v1/analyses', headers=headers,
                    json={'text': 'x' * 20001}).status_code, 422)
                self.assertEqual(client.post('/api/v1/analyses', headers=headers,
                    json={'text': '필러', 'mode': 'invalid'}).status_code, 422)
                response = client.post('/api/v1/analyses', headers=headers,
                    json={'text': '필러 필러', 'mode': 'exact', 'record': True})
                self.assertEqual(response.status_code, 200, response.text)
                body = response.json()
                self.assertEqual(len(body['matches']), 2)
                path = '/api/v1/analyses/' + body['analysis_id']
                self.assertEqual(client.get(path, headers=headers).status_code, 200)
                self.assertEqual(client.get(path, headers={
                    'Authorization': 'Bearer test-integration-key'}).status_code, 409)
                self.assertEqual(client.get('/api/v1/keywords?limit=501',
                    headers=headers).status_code, 422)
        finally:
            api.app.dependency_overrides.clear()

    def test_snapshot_keeps_more_than_1000_rows_and_extra_columns(self):
        rows = [{'kwd_no': f'A{i:04}', '키워드명': '필러', '비고': '보존'}
                for i in range(1431)]
        with patch.dict(os.environ, {'SUPABASE_URL': 'https://example.supabase.co',
                                     'SUPABASE_SECRET_KEY': 'sb_secret_test'}):
            repository = SupabaseRepository()
            with patch.object(repository, 'rpc', return_value={
                'columns': ['kwd_no', '키워드명', '비고'], 'rows': rows, 'revision': 5}):
                df = repository.load_keywords()
        self.assertEqual(len(df), 1431)
        self.assertEqual(df.iloc[-1]['비고'], '보존')
        self.assertEqual(df.attrs['revision'], 5)

    def test_secret_keys_are_not_sent_as_bearer_tokens(self):
        with patch.dict(os.environ, {'SUPABASE_URL': 'https://example.supabase.co',
                                     'SUPABASE_SECRET_KEY': 'sb_secret_test'}), \
             patch('repository.requests.request') as request:
            request.return_value.status_code = 200
            request.return_value.content = b'{}'
            request.return_value.json.return_value = {}
            SupabaseRepository().rpc('snapshot')
            headers = request.call_args.kwargs['headers']
            self.assertEqual(headers['apikey'], 'sb_secret_test')
            self.assertNotIn('Authorization', headers)

    def test_existing_streamlit_csv_screen_and_member_analysis(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            for name in ('keyword_app2_fixed270.py', 'matching_engine.py',
                         'app_config.py', 'repository.py', 'service.py'):
                shutil.copy2(ROOT / name, target / name)
            self.repository.df.to_csv(target / 'keywords_db.csv', index=False, encoding='utf-8-sig')
            with patch.dict(os.environ, {'STORAGE_BACKEND': 'csv'}):
                app = AppTest.from_file(str(target / 'keyword_app2_fixed270.py')).run(timeout=30)
                self.assertEqual(len(app.exception), 0)
                app.button(key='btn_analyze').click().run(timeout=30)
                self.assertEqual(len(app.exception), 0)
                self.assertEqual(app.session_state['analysis_count'], 1)
                self.assertTrue(app.button(key='report_reset_btn').disabled)
            self.assertEqual(pd.read_csv(target / 'keywords_hits_log.csv').shape[0], 1)

    def test_cloud_requires_login_before_data_access(self):
        with patch.dict(os.environ, {'STORAGE_BACKEND': 'supabase',
                                    'SUPABASE_URL': 'https://example.supabase.co',
                                    'SUPABASE_SECRET_KEY': 'sb_secret_test'}), \
             patch('repository.SupabaseRepository.load_keywords') as load:
            app = AppTest.from_file(str(ROOT / 'keyword_app2_fixed270.py')).run(timeout=30)
            self.assertEqual(len(app.exception), 0)
            load.assert_not_called()
            self.assertFalse(any(b.key == 'btn_analyze' for b in app.button))

    def test_cloud_member_uses_transaction_and_cannot_reset(self):
        with patch.dict(os.environ, {'STORAGE_BACKEND': 'supabase',
                                    'SUPABASE_URL': 'https://example.supabase.co',
                                    'SUPABASE_SECRET_KEY': 'sb_secret_test'}), \
             patch('repository.SupabaseRepository.user', return_value=self.repository.user('valid-user-token')), \
             patch('repository.SupabaseRepository.load_keywords', side_effect=self.repository.load_keywords), \
             patch('repository.SupabaseRepository.load_setting', side_effect=self.repository.load_setting), \
             patch('repository.SupabaseRepository.load_hits', side_effect=self.repository.load_hits), \
             patch('repository.SupabaseRepository.record_analysis') as record:
            app = AppTest.from_file(str(ROOT / 'keyword_app2_fixed270.py'))
            app.session_state['auth_session'] = {'access_token': 'valid-user-token',
                                                'expires_at': 9999999999}
            app.run(timeout=30)
            self.assertEqual(len(app.exception), 0)
            app.button(key='btn_analyze').click().run(timeout=30)
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(app.session_state['analysis_count'], 1)
            record.assert_called_once()
            self.assertEqual(record.call_args.args[2], 'user-1')
            self.assertTrue(app.button(key='report_reset_btn').disabled)


if __name__ == '__main__':
    unittest.main()
