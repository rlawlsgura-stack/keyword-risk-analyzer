import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from repository import StorageError, SupabaseRepository


class KeywordRequestRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            'SUPABASE_URL': 'https://project.example.supabase.co',
            'SUPABASE_SECRET_KEY': 'server-only-test-key',
        })
        self.env.start()
        self.addCleanup(self.env.stop)

    @staticmethod
    def response(data):
        result = Mock(status_code=200, content=b'json')
        result.json.return_value = data
        return result

    def test_insert_uses_signed_in_user_jwt_for_rls(self):
        row = {'id': 'request-1', 'kwd_no': 'B101'}
        with patch('repository.requests.request', return_value=self.response([row])) as request:
            saved = SupabaseRepository().submit_keyword_request(
                {'requester_id': 'user-1'}, 'user-access-token')

        self.assertEqual(saved, row)
        kwargs = request.call_args.kwargs
        self.assertEqual(kwargs['headers']['Authorization'], 'Bearer user-access-token')
        self.assertEqual(kwargs['headers']['apikey'], 'server-only-test-key')
        self.assertEqual(request.call_args.args[:2], (
            'POST', 'https://project.example.supabase.co/rest/v1/kra_keyword_requests'))

    def test_refresh_rotates_the_supabase_session_with_refresh_grant(self):
        refreshed = {'access_token': 'new-access', 'refresh_token': 'new-refresh'}
        with patch('repository.requests.request', return_value=self.response(refreshed)) as request:
            result = SupabaseRepository().refresh('old-refresh')

        self.assertEqual(result, refreshed)
        self.assertEqual(request.call_args.args[:2], (
            'POST', 'https://project.example.supabase.co/auth/v1/token?grant_type=refresh_token'))
        self.assertEqual(request.call_args.kwargs['json'], {'refresh_token': 'old-refresh'})

    def test_unmatched_page_rejects_unknown_sort_and_passes_registered_sort(self):
        repo = SupabaseRepository()
        with patch.object(repo, 'rpc', return_value={'rows': [], 'total': 0}) as rpc:
            repo.load_unmatched_terms(100, 100, '보습', 'registered')
        rpc.assert_called_once_with(
            'unmatched_term_page', p_offset=100, p_limit=100,
            p_search='보습', p_sort='registered')
        with self.assertRaises(ValueError):
            repo.load_unmatched_terms(sort='invalid')

    def test_request_list_and_notification_settings_use_user_jwt(self):
        with patch('repository.requests.request', side_effect=[
            self.response([]), self.response([{'email_notifications_enabled': True}]),
        ]) as request:
            repo = SupabaseRepository()
            self.assertEqual(repo.load_keyword_requests('user-access-token'), [])
            self.assertTrue(repo.load_request_email_notifications('user-access-token'))

        self.assertEqual(request.call_count, 2)
        for call in request.call_args_list:
            self.assertEqual(call.kwargs['headers']['Authorization'], 'Bearer user-access-token')

    def test_request_list_selects_workflow_fields(self):
        with patch('repository.requests.request', return_value=self.response([])) as request:
            SupabaseRepository().load_keyword_requests('user-access-token')

        self.assertIn('status,admin_reply,created_at', request.call_args.args[1])

    def test_admin_request_update_uses_user_jwt_and_only_workflow_fields(self):
        row = {'id': 'request-1', 'status': '검토중', 'admin_reply': '확인 중입니다.'}
        with patch('repository.requests.request', return_value=self.response([row])) as request:
            saved = SupabaseRepository().update_keyword_request(
                'request-1', '검토중', '확인 중입니다.', 'admin-access-token')

        self.assertEqual(saved, row)
        self.assertEqual(request.call_args.args[:2], (
            'PATCH',
            'https://project.example.supabase.co/rest/v1/kra_keyword_requests'
            '?id=eq.request-1&select=id,status,admin_reply',
        ))
        self.assertEqual(request.call_args.kwargs['json'], {
            'status': '검토중', 'admin_reply': '확인 중입니다.',
        })
        self.assertEqual(request.call_args.kwargs['headers']['Authorization'],
                         'Bearer admin-access-token')

    def test_admin_request_delete_uses_user_jwt_and_delete_method(self):
        request_id = '00000000-0000-0000-0000-000000000001'
        row = {'id': request_id}
        with patch('repository.requests.request', return_value=self.response([row])) as request:
            deleted = SupabaseRepository().delete_keyword_request(
                request_id, 'admin-access-token')

        self.assertEqual(deleted, row)
        self.assertEqual(request.call_args.args[:2], (
            'DELETE',
            'https://project.example.supabase.co/rest/v1/kra_keyword_requests?id=eq.' + request_id,
        ))
        self.assertEqual(request.call_args.kwargs['headers']['Authorization'],
                         'Bearer admin-access-token')

    def test_owner_edit_uses_user_token_and_only_content_fields(self):
        request_id = '00000000-0000-0000-0000-000000000001'
        row = {'id': request_id, 'request_detail': 'edited'}
        with patch('repository.requests.request', return_value=self.response(row)) as request:
            saved = SupabaseRepository().edit_own_keyword_request(
                request_id, 'review_criteria_change', '  edited  ', 'owner-token')
        self.assertEqual(saved, row)
        self.assertEqual(request.call_args.args[:2], (
            'POST', 'https://project.example.supabase.co/rest/v1/rpc/kra_edit_own_keyword_request',
        ))
        self.assertEqual(request.call_args.kwargs['json'], {
            'p_request_id': request_id, 'p_request_type': 'review_criteria_change',
            'p_request_detail': 'edited',
        })
        self.assertEqual(request.call_args.kwargs['headers']['Authorization'], 'Bearer owner-token')

    def test_owner_mutations_require_a_token_valid_id_and_valid_content(self):
        repo = SupabaseRepository()
        request_id = '00000000-0000-0000-0000-000000000001'
        with patch('repository.requests.request') as request:
            with self.assertRaises(PermissionError):
                repo.edit_own_keyword_request(request_id, 'review_criteria_change', '', '')
            with self.assertRaises(PermissionError):
                repo.delete_keyword_request(request_id, '')
            with self.assertRaises(ValueError):
                repo.delete_keyword_request(request_id + '&id=neq.other', 'owner-token')
            for request_type, detail in [('invalid', ''), ('review_criteria_change', 'x' * 4001)]:
                with self.assertRaises(ValueError):
                    repo.edit_own_keyword_request(request_id, request_type, detail, 'owner-token')
            request.assert_not_called()

    def test_request_message_history_uses_user_jwt_and_ascending_order(self):
        request_id = '00000000-0000-0000-0000-000000000001'
        with patch('repository.requests.request', return_value=self.response([])) as request:
            messages = SupabaseRepository().load_keyword_request_messages(
                request_id, 'user-access-token')

        self.assertEqual(messages, [])
        self.assertEqual(request.call_args.args[:2], (
            'GET',
            'https://project.example.supabase.co/rest/v1/kra_keyword_request_messages'
            '?select=id,request_id,author_id,author_email,author_role,is_initial,is_legacy,reply_to_id,body,status,created_at'
            f'&request_id=eq.{request_id}&order=created_at.asc,id.asc&limit=1000',
        ))
        self.assertEqual(request.call_args.kwargs['headers']['Authorization'],
                         'Bearer user-access-token')

    def test_each_inquiry_mutation_uses_its_own_id_and_user_token(self):
        request_id = '00000000-0000-0000-0000-000000000001'
        inquiry_id = '00000000-0000-0000-0000-000000000002'
        for action in ('edit', 'delete'):
            with self.subTest(action=action), patch('repository.requests.request',
                    return_value=self.response({'id': inquiry_id})) as request:
                result = SupabaseRepository().mutate_own_keyword_inquiry(
                    request_id, inquiry_id, action, 'owner-token',
                    body='  edited  ' if action == 'edit' else None,
                )
                self.assertEqual(result, {'id': inquiry_id})
                self.assertEqual(request.call_args.args[:2], (
                    'POST', 'https://project.example.supabase.co/rest/v1/rpc/kra_mutate_own_keyword_inquiry',
                ))
                self.assertEqual(request.call_args.kwargs['json'], {
                    'p_request_id': request_id, 'p_inquiry_id': inquiry_id,
                    'p_action': action, 'p_body': 'edited' if action == 'edit' else None,
                    'p_request_type': None,
                })
                self.assertEqual(request.call_args.kwargs['headers']['Authorization'], 'Bearer owner-token')

    def test_each_inquiry_mutation_rejects_missing_auth_invalid_ids_and_actions(self):
        request_id = '00000000-0000-0000-0000-000000000001'
        with patch('repository.requests.request') as request:
            repo = SupabaseRepository()
            with self.assertRaises(PermissionError):
                repo.mutate_own_keyword_inquiry(request_id, request_id, 'delete', '')
            for inquiry_id, action, body in [
                ('invalid', 'edit', 'body'), (request_id, 'invalid', 'body'),
                (request_id, 'edit', 'x' * 4001),
            ]:
                with self.assertRaises(ValueError):
                    repo.mutate_own_keyword_inquiry(request_id, inquiry_id, action, 'token', body)
            request.assert_not_called()

    def test_request_message_insert_uses_signed_in_user_token(self):
        request_id = '00000000-0000-0000-0000-000000000001'
        author_id = '00000000-0000-0000-0000-000000000002'
        row = {'id': 'message-1', 'body': '추가 문의입니다.'}
        with patch('repository.requests.request', return_value=self.response([row])) as request:
            saved = SupabaseRepository().add_keyword_request_message(
                request_id, author_id, 'member@example.test',
                '  추가 문의입니다.  ', 'user-access-token')

        self.assertEqual(saved, row)
        self.assertEqual(request.call_args.args[:2], (
            'POST',
            'https://project.example.supabase.co/rest/v1/kra_keyword_request_messages',
        ))
        self.assertEqual(request.call_args.kwargs['json'], {
            'request_id': request_id, 'author_id': author_id,
            'author_email': 'member@example.test', 'author_role': 'user',
            'reply_to_id': None, 'body': '추가 문의입니다.',
        })
        self.assertEqual(request.call_args.kwargs['headers']['Authorization'],
                         'Bearer user-access-token')

    def test_request_message_rejects_empty_or_oversized_content(self):
        request_id = '00000000-0000-0000-0000-000000000001'
        author_id = '00000000-0000-0000-0000-000000000002'
        repo = SupabaseRepository()
        with self.assertRaises(ValueError):
            repo.add_keyword_request_message(request_id, author_id, 'member@example.test',
                                             '  ', 'user-access-token')
        with self.assertRaises(ValueError):
            repo.add_keyword_request_message(request_id, author_id, 'member@example.test',
                                             'x' * 4001, 'user-access-token')

    def test_admin_reply_is_bound_to_selected_user_inquiry(self):
        request_id = '00000000-0000-0000-0000-000000000001'
        author_id = '00000000-0000-0000-0000-000000000002'
        inquiry_id = '00000000-0000-0000-0000-000000000003'
        row = {'id': 'reply-1', 'reply_to_id': inquiry_id}
        with patch('repository.requests.request', return_value=self.response([row])) as request:
            saved = SupabaseRepository().add_keyword_request_message(
                request_id, author_id, 'admin@example.test', '답변입니다.',
                'admin-access-token', author_role='admin', reply_to_id=inquiry_id)

        self.assertEqual(saved, row)
        self.assertEqual(request.call_args.kwargs['json'], {
            'request_id': request_id, 'author_id': author_id,
            'author_email': 'admin@example.test', 'author_role': 'admin',
            'reply_to_id': inquiry_id, 'body': '답변입니다.',
        })
        self.assertEqual(request.call_args.kwargs['headers']['Authorization'],
                         'Bearer admin-access-token')
        with self.assertRaises(ValueError):
            SupabaseRepository().add_keyword_request_message(
                request_id, author_id, 'admin@example.test', '답변입니다.',
                'admin-access-token', author_role='admin')

    def test_user_followup_is_bound_to_an_admin_reply(self):
        request_id = '00000000-0000-0000-0000-000000000001'
        author_id = '00000000-0000-0000-0000-000000000002'
        admin_reply_id = '00000000-0000-0000-0000-000000000003'
        row = {'id': 'followup-1', 'reply_to_id': admin_reply_id}
        with patch('repository.requests.request', return_value=self.response([row])) as request:
            saved = SupabaseRepository().add_keyword_request_message(
                request_id, author_id, 'member@example.test', '추가 문의입니다.',
                'user-access-token', author_role='user', reply_to_id=admin_reply_id)

        self.assertEqual(saved, row)
        self.assertEqual(request.call_args.kwargs['json'], {
            'request_id': request_id, 'author_id': author_id,
            'author_email': 'member@example.test', 'author_role': 'user',
            'reply_to_id': admin_reply_id, 'body': '추가 문의입니다.',
        })
        self.assertEqual(request.call_args.kwargs['headers']['Authorization'],
                         'Bearer user-access-token')

    def test_admin_feedback_and_status_use_one_authenticated_rpc(self):
        request_id = '00000000-0000-0000-0000-000000000001'
        inquiry_id = '00000000-0000-0000-0000-000000000002'
        with patch('repository.requests.request', return_value=self.response('reply-id')) as request:
            result = SupabaseRepository().respond_to_keyword_inquiry(
                request_id, inquiry_id, '  feedback  ', '\ucc98\ub9ac\uc644\ub8cc',
                'admin-access-token')

        self.assertEqual(result, 'reply-id')
        self.assertEqual(request.call_args.args[:2], (
            'POST',
            'https://project.example.supabase.co/rest/v1/rpc/kra_admin_respond_to_keyword_inquiry',
        ))
        self.assertEqual(request.call_args.kwargs['json'], {
            'p_request_id': request_id, 'p_inquiry_id': inquiry_id,
            'p_body': 'feedback', 'p_status': '\ucc98\ub9ac\uc644\ub8cc',
        })
        self.assertEqual(request.call_args.kwargs['headers']['Authorization'],
                         'Bearer admin-access-token')

        with self.assertRaises(ValueError):
            SupabaseRepository().respond_to_keyword_inquiry(
                request_id, inquiry_id, 'feedback', 'invalid', 'admin-access-token')

    def test_request_message_sql_is_append_only_and_owner_scoped(self):
        sql = (Path(__file__).resolve().parents[1]
               / 'supabase' / 'keyword_request_messages_setup.sql').read_text(encoding='utf-8')
        self.assertIn('enable row level security', sql.lower())
        self.assertIn('grant select, insert', sql.lower())
        self.assertNotIn('grant update', sql.lower())
        self.assertNotIn('grant delete', sql.lower())
        self.assertIn('r.requester_id = (select auth.uid())', sql)
        self.assertIn("(select auth.jwt() -> 'app_metadata' ->> 'role') = 'admin'", sql)
        self.assertIn('author_id = (select auth.uid())', sql)
        pairing_sql = (Path(__file__).resolve().parents[1]
                       / 'supabase' / 'keyword_request_reply_pairing_setup.sql').read_text(encoding='utf-8')
        self.assertIn('one_reply_per_inquiry_idx', pairing_sql)
        self.assertIn('kra_keyword_request_messages.reply_to_id', pairing_sql)
        self.assertIn("author_role = 'admin'", pairing_sql)
        followup_sql = (Path(__file__).resolve().parents[1]
                        / 'supabase' / 'keyword_request_user_followup_setup.sql').read_text(encoding='utf-8')
        self.assertIn("parent.author_role = 'admin'", followup_sql)
        self.assertIn("parent.author_role = 'user'", followup_sql)
        self.assertIn('is_legacy', followup_sql)
        feedback_sql = (Path(__file__).resolve().parents[1]
                        / 'supabase' / 'keyword_request_feedback_status_setup.sql').read_text(encoding='utf-8')
        self.assertIn('security invoker', feedback_sql.lower())
        self.assertIn('kra_keyword_request_messages_update_admin_status', feedback_sql)
        self.assertIn('kra_admin_respond_to_keyword_inquiry', feedback_sql)
        self.assertIn('set status = p_status', feedback_sql)

    def test_login_reports_safe_supabase_auth_diagnostic(self):
        response = self.response({'code': 'invalid_credentials',
                                  'msg': 'Invalid login credentials'})
        response.status_code = 400
        with patch('repository.requests.request', return_value=response):
            with self.assertRaisesRegex(StorageError, 'invalid_credentials'):
                SupabaseRepository().login('user@example.com', 'never-log-this')

    def test_notification_toggle_update_uses_user_jwt(self):
        response = self.response([{'email_notifications_enabled': False}])
        with patch('repository.requests.request', return_value=response) as request:
            enabled = SupabaseRepository().save_request_email_notifications(
                False, 'admin-access-token')

        self.assertFalse(enabled)
        self.assertEqual(request.call_args.kwargs['headers']['Authorization'],
                         'Bearer admin-access-token')
        self.assertEqual(request.call_args.kwargs['json'],
                         {'email_notifications_enabled': False})


if __name__ == '__main__':
    unittest.main()
