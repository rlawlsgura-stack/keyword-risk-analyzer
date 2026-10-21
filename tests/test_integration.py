from dataclasses import asdict
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

import pandas as pd
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest

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
                self.assertFalse(any(b.key in {'report_reset_btn', 'report_reset7_btn'} for b in app.button))
                self.assertFalse(any(c.key in {'report_reset_ck', 'report_reset7_ck'} for c in app.checkbox))
                self.assertEqual([tab.label for tab in app.tabs], ['분석하기', '리포트(주간 Top N)'])
                app.session_state['is_admin'] = True
                app.run(timeout=30)
                self.assertEqual(len(app.exception), 0)
                self.assertEqual([tab.label for tab in app.tabs],
                                 ['분석하기', '리포트(주간 Top N)', '키워드 관리'])
                self.assertTrue(app.button(key='report_reset_btn').disabled)
                self.assertTrue(app.button(key='report_reset7_btn').disabled)
                app.session_state['is_admin'] = False
                app.run(timeout=30)
                self.assertEqual(len(app.exception), 0)
                self.assertEqual([tab.label for tab in app.tabs], ['분석하기', '리포트(주간 Top N)'])
                self.assertFalse(any(b.key in {'report_reset_btn', 'report_reset7_btn'} for b in app.button))
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
            self.assertFalse(any(b.key in {'report_reset_btn', 'report_reset7_btn'} for b in app.button))
            self.assertFalse(any(c.key in {'report_reset_ck', 'report_reset7_ck'} for c in app.checkbox))
            self.assertFalse(any('조회 수 초기화' in m.value for m in app.markdown))
            self.assertEqual([tab.label for tab in app.tabs], ['분석하기', '리포트(주간 Top N)'])
            self.assertEqual(len(app.file_uploader), 0)
            self.assertFalse(any(b.key == 'user_admin_load' for b in app.button))
            self.assertFalse(any(b.key in {'btn_save_suffix_extra', 'btn_save_ignored_syms',
                                          'btn_reset_suffix_extra', 'btn_reset_ignored_syms'} for b in app.button))
            self.assertFalse(any((area.key or '').startswith(('ui_suffix_extra_editor', 'ui_ignored_syms_editor'))
                                 for area in app.text_area))
            self.assertIn('적용 중인 규칙 요약', [expander.label for expander in app.expander])

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
        self.assertTrue(calls[1].args[1].endswith('/admin/users?page=2&per_page=50'))
        for call in (calls[1], calls[3], calls[4]):
            self.assertEqual(call.kwargs['headers']['apikey'], 'sb_secret_test')
            self.assertNotIn('Authorization', call.kwargs['headers'])
        self.assertEqual(calls[4].args[0], 'PUT')
        self.assertEqual(calls[4].kwargs['json'], {'app_metadata': {'role': 'admin'}})

    def test_admin_can_assign_missing_role_from_screen(self):
        admin_id, target_id = str(uuid4()), str(uuid4())
        actor = {'id': admin_id, 'email': 'admin@example.test', 'app_metadata': {'role': 'admin'}}
        users = [{'id': admin_id, 'email': actor['email'], 'role': 'admin', 'email_confirmed': True},
                 {'id': target_id, 'email': 'new@example.test', 'role': None, 'email_confirmed': True}]
        with patch.dict(os.environ, {'STORAGE_BACKEND': 'supabase',
                                    'SUPABASE_URL': 'https://example.supabase.co',
                                    'SUPABASE_SECRET_KEY': 'sb_secret_test'}), \
             patch('repository.SupabaseRepository.user', return_value=actor), \
             patch('repository.SupabaseRepository.load_keywords', side_effect=self.repository.load_keywords), \
             patch('repository.SupabaseRepository.load_setting', side_effect=self.repository.load_setting), \
             patch('repository.SupabaseRepository.load_hits', side_effect=self.repository.load_hits), \
             patch('repository.SupabaseRepository.list_users', return_value=users) as load, \
             patch('repository.SupabaseRepository.set_user_role', return_value={
                 **users[1], 'role': 'member'}) as save:
            app = AppTest.from_file(str(ROOT / 'keyword_app2_fixed270.py'))
            app.session_state['auth_session'] = {'access_token': 'admin-token', 'expires_at': 9999999999}
            app.run(timeout=30)
            self.assertEqual(len(app.exception), 0)
            self.assertEqual([tab.label for tab in app.tabs],
                             ['분석하기', '리포트(주간 Top N)', '키워드 관리', '사용자 관리'])
            self.assertTrue(app.button(key='report_reset_btn').disabled)
            self.assertTrue(app.button(key='report_reset7_btn').disabled)
            app.checkbox(key='report_reset_ck').check().run(timeout=30)
            self.assertFalse(app.button(key='report_reset_btn').disabled)
            app.checkbox(key='report_reset7_ck').check().run(timeout=30)
            self.assertFalse(app.button(key='report_reset7_btn').disabled)
            load.assert_not_called()  # hidden tab does not fetch accounts
            app.button(key='user_admin_load').click().run(timeout=30)
            load.assert_called_once_with('admin-token', page=1)
            self.assertTrue(app.button(key='FormSubmitter:user_admin_role_form-역할 저장').disabled)
            app.selectbox(key='user_admin_target').select(target_id).run(timeout=30)
            app.button(key='FormSubmitter:user_admin_role_form-역할 저장').click().run(timeout=30)
            save.assert_not_called()  # explicit confirmation is required
            app.checkbox(key='user_admin_confirm_' + target_id).check()
            app.button(key='FormSubmitter:user_admin_role_form-역할 저장').click().run(timeout=30)
            self.assertEqual(len(app.exception), 0)
            save.assert_called_once_with('admin-token', target_id, 'member', None)
            self.assertTrue(any('역할을 저장했습니다' in message.value for message in app.success))
            self.assertEqual(app.session_state['managed_users'][1]['role'], 'member')

    def test_admin_common_rules_save_and_apply_on_next_analysis(self):
        settings = {}
        actor = {'id': str(uuid4()), 'email': 'admin@example.test',
                 'app_metadata': {'role': 'admin'}}
        with patch.dict(os.environ, {'STORAGE_BACKEND': 'supabase',
                                    'SUPABASE_URL': 'https://example.supabase.co',
                                    'SUPABASE_SECRET_KEY': 'sb_secret_test'}), \
             patch('repository.SupabaseRepository.user', return_value=actor), \
             patch('repository.SupabaseRepository.load_keywords', side_effect=self.repository.load_keywords), \
             patch('repository.SupabaseRepository.load_setting', side_effect=lambda name, default: settings.get(name, default)), \
             patch('repository.SupabaseRepository.save_setting', side_effect=settings.__setitem__) as save, \
             patch('repository.SupabaseRepository.load_hits', side_effect=self.repository.load_hits), \
             patch('repository.SupabaseRepository.record_analysis'), \
             patch('service.match_text', wraps=match_text) as match:
            app = AppTest.from_file(str(ROOT / 'keyword_app2_fixed270.py'))
            app.session_state['auth_session'] = {'access_token': 'admin-token', 'expires_at': 9999999999}
            app.run(timeout=30)
            self.assertEqual(len(app.exception), 0)
            self.assertFalse(any((area.key or '').startswith('ui_ignored_syms_editor')
                                 for area in app.tabs[0].text_area))
            self.assertTrue(any((area.key or '').startswith('ui_ignored_syms_editor')
                                for area in app.tabs[2].text_area))
            app.text_area(key='ui_ignored_syms_editor_0').input('/\n&\n,\n*')
            app.button(key='btn_save_ignored_syms').click().run(timeout=30)
            self.assertEqual(len(app.exception), 0)
            save.assert_called_once_with('ignored_special_symbols', {'symbols': ['/', '&', ',', '*']})
            app.text_area(key='ui_ignored_syms_editor_1').input('//')
            app.button(key='btn_save_ignored_syms').click().run(timeout=30)
            self.assertEqual(save.call_count, 1)
            self.assertTrue(any('문자 하나' in error.value for error in app.error))
            app.text_area(key='ui_suffix_extra_editor_1').input('테스트말\n에는')
            app.button(key='btn_save_suffix_extra').click().run(timeout=30)
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(settings['ko_suffix_whitelist'], {'extra_suffixes': ['테스트말']})
            app.button(key='btn_analyze').click().run(timeout=30)
            self.assertEqual(len(app.exception), 0)
            config = match.call_args.kwargs['config']
            self.assertEqual(config.mode, 'exact')
            self.assertTrue(config.exact_relaxed)
            self.assertIn('테스트말', config.ko_suffixes)
            self.assertIn(',', config.ignored_symbols)


if __name__ == '__main__':
    unittest.main()
