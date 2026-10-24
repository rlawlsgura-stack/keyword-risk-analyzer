import os
import unittest
from unittest.mock import Mock, patch

from repository import SupabaseRepository


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
