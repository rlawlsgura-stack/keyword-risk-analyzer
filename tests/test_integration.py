from dataclasses import asdict
from itertools import product
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

import pandas as pd
from fastapi.testclient import TestClient

import api
from matching_engine import DB_COLS, MatchingConfig, find_matches_nlp
from repository import ConflictError, SupabaseRepository
from service import MODES, analyze, match_text

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

    def test_service_preserves_all_engine_modes_and_pre_filters(self):
        for mode, label in MODES.items():
            request = {'text': '필러와 필러', 'mode': mode, 'exact_relaxed': True}
            result = analyze(self.repository, request, 'user-1')
            expected = find_matches_nlp(request['text'], self.repository.df,
                                       match_mode=label, exact_relaxed=True,
                                       config=MatchingConfig())
            expected_matches = [asdict(match) for match in expected]
            self.assertEqual(len(result['matches']), len(expected_matches))
            actual_matches = [
                {key: match[key] for key in expected_match}
                for match, expected_match in zip(result['matches'], expected_matches)
            ]
            self.assertEqual(actual_matches, expected_matches)
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

    def test_api_independent_options_override_legacy_and_keep_record_fingerprints(self):
        self.repository.df.loc[0, '키워드명'] = 'Anti Aging(note)'
        api.app.dependency_overrides[api.get_repository] = lambda: self.repository
        api.app.dependency_overrides[api.current_actor] = lambda: 'user-1'
        try:
            with TestClient(api.app) as client:
                for bracket, whitespace, case, symbols in product((False, True), repeat=4):
                    response = client.post('/api/v1/analyses', json={
                        'text': 'anti&\naging', 'mode': 'exact', 'exact_relaxed': True,
                        'strip_bracket_notes': bracket, 'normalize_whitespace': whitespace,
                        'ignore_case': case, 'normalize_symbols': symbols})
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertEqual(bool(response.json()['matches']), all((bracket, whitespace, case, symbols)))
                self.assertEqual(client.post('/api/v1/analyses', json={
                    'text': 'x', 'ignore_case': 'false'}).status_code, 422)
                for minimum, expected in ((5, True), (6, False)):
                    response = client.post('/api/v1/analyses', json={
                        'text': 'aging care', 'mode': 'partial', 'partial_min_len': minimum,
                        'strip_bracket_notes': True, 'normalize_whitespace': True,
                        'ignore_case': True, 'normalize_symbols': True})
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertEqual(bool(response.json()['matches']), expected)
                    if expected:
                        self.assertEqual([(m['start'], m['end']) for m in response.json()['matches']], [(0, 5)])

                # Existing saved requests must remain replayable after nullable fields are added.
                body = {'text': 'Anti Aging(note)', 'mode': 'exact', 'record': True,
                        'analysis_id': str(uuid4())}
                legacy = api.AnalysisRequest(**body).model_dump(mode='json')
                for name in ('strip_bracket_notes', 'normalize_whitespace', 'ignore_case', 'normalize_symbols'):
                    legacy.pop(name)
                old_result = analyze(self.repository, legacy, 'user-1')
                replay = client.post('/api/v1/analyses', json=body)
                self.assertEqual(replay.status_code, 200, replay.text)
                self.assertEqual(replay.json(), old_result)
                self.assertEqual(self.repository.records, 1)
                body['ignore_case'] = False
                self.assertEqual(client.post('/api/v1/analyses', json=body).status_code, 409)
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

    def test_user_management_rechecks_admin_and_prevents_self_demotion(self):
        admin_id, target_id = str(uuid4()), str(uuid4())
        with patch.dict(os.environ, {'SUPABASE_URL': 'https://example.supabase.co',
                                    'SUPABASE_SECRET_KEY': 'sb_secret_test'}):
            repository = SupabaseRepository()
            with patch.object(repository, 'user', return_value={
                    'id': admin_id, 'app_metadata': {'role': 'member'}}), \
                 patch.object(repository, 'request') as request:
                with self.assertRaises(PermissionError):
                    repository.list_users('revoked-admin-token')
                with self.assertRaises(PermissionError):
                    repository.set_user_role('revoked-admin-token', target_id, 'admin', 'member')
                request.assert_not_called()
            with patch.object(repository, 'user', return_value={
                    'id': admin_id, 'app_metadata': {'role': 'admin'}}), \
                 patch.object(repository, 'request') as request:
                with self.assertRaises(ValueError):
                    repository.set_user_role('admin-token', admin_id, 'member', 'admin')
                with self.assertRaises(ValueError):
                    repository.set_user_role('admin-token', target_id, 'service_role', 'member')
                with self.assertRaises(ValueError):
                    repository.set_user_role('admin-token', '../users', 'member', None)
                request.assert_not_called()
                request.return_value = {'id': target_id, 'app_metadata': {'role': 'admin'}}
                with self.assertRaises(ConflictError):
                    repository.set_user_role('admin-token', target_id, 'member', None)
                self.assertEqual(request.call_count, 1)  # stale snapshot never writes

    def test_user_management_rest_uses_server_key_and_updates_only_app_role(self):
        admin_id, target_id = str(uuid4()), str(uuid4())
        actor = {'id': admin_id, 'app_metadata': {'role': 'admin'}}
        target = {'id': target_id, 'email': 'member@example.test',
                  'app_metadata': {'provider': 'email', 'role': 'member', 'team': 'keep'}}
        bodies = [actor, {'users': [target]}, actor, target,
                  {**target, 'app_metadata': {**target['app_metadata'], 'role': 'admin'}}]
        responses = [Mock(status_code=200, content=b'json', json=Mock(return_value=body))
                     for body in bodies]
        with patch.dict(os.environ, {'SUPABASE_URL': 'https://example.supabase.co',
                                    'SUPABASE_SECRET_KEY': 'sb_secret_test'}), \
             patch('repository.requests.request', side_effect=responses) as request:
            repository = SupabaseRepository()
            users = repository.list_users('verified-admin-token', page=2)
            self.assertEqual(users[0]['role'], 'member')
            self.assertNotIn('app_metadata', users[0])
            updated = repository.set_user_role('verified-admin-token', target_id, 'admin', 'member')
        self.assertEqual(updated['role'], 'admin')
        calls = request.call_args_list
        self.assertEqual(calls[0].kwargs['headers']['Authorization'], 'Bearer verified-admin-token')
        self.assertTrue(calls[1].args[1].endswith('/admin/users?page=2&per_page=1000'))
        for call in (calls[1], calls[3], calls[4]):
            self.assertEqual(call.kwargs['headers']['apikey'], 'sb_secret_test')
            self.assertNotIn('Authorization', call.kwargs['headers'])
        self.assertEqual(calls[4].args[0], 'PUT')
        self.assertEqual(calls[4].kwargs['json'], {'app_metadata': {'role': 'admin'}})

if __name__ == '__main__':
    unittest.main()
