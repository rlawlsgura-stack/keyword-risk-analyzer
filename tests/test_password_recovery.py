from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit
import os

from streamlit.testing.v1 import AppTest
from repository import StorageError, SupabaseRepository


class PasswordRecoveryTests(TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            'SUPABASE_URL': 'https://project.example.supabase.co',
            'SUPABASE_SECRET_KEY': 'server-only-test-key',
        })
        self.env.start()
        self.addCleanup(self.env.stop)

    @staticmethod
    def response():
        result = Mock(status_code=200, content=b'{}')
        result.json.return_value = {}
        return result

    def test_reset_request_uses_supabase_recovery_endpoint(self):
        with patch('repository.requests.request', return_value=self.response()) as request:
            SupabaseRepository().request_password_reset(
                ' member@example.test ', 'https://app.example.test/')

        method, url = request.call_args.args[:2]
        self.assertEqual(method, 'POST')
        self.assertEqual(urlsplit(url).path, '/auth/v1/recover')
        self.assertEqual(parse_qs(urlsplit(url).query), {
            'redirect_to': ['https://app.example.test/']})
        self.assertEqual(request.call_args.kwargs['json'], {
            'email': 'member@example.test'})

    def test_signup_uses_supabase_auth_and_redirect_without_assigning_role(self):
        with patch.dict(os.environ, {'SUPABASE_SECRET_KEY': 'sb_secret_test'}), \
             patch('repository.requests.request', return_value=self.response()) as request:
            SupabaseRepository().sign_up(
                ' member@example.test ', 'safe-test-password', 'https://app.example.test/')

        method, url = request.call_args.args[:2]
        self.assertEqual(method, 'POST')
        self.assertEqual(urlsplit(url).path, '/auth/v1/signup')
        self.assertEqual(parse_qs(urlsplit(url).query), {
            'redirect_to': ['https://app.example.test/']})
        self.assertEqual(request.call_args.kwargs['json'], {
            'email': 'member@example.test', 'password': 'safe-test-password'})
        self.assertEqual(request.call_args.kwargs['headers']['apikey'], 'sb_secret_test')
        self.assertNotIn('Authorization', request.call_args.kwargs['headers'])

    def test_signup_surfaces_safe_auth_error_code_and_message(self):
        response = Mock(status_code=400, content=b'json')
        response.json.return_value = {
            'code': 'weak_password', 'message': 'Password does not meet requirements.'}
        with patch('repository.requests.request', return_value=response):
            with self.assertRaises(StorageError) as error:
                SupabaseRepository().sign_up(
                    'member@example.test', 'short', 'https://app.example.test/')

        self.assertEqual(str(error.exception),
                         'Supabase request failed (400): weak_password: Password does not meet requirements.')

    def test_signup_screen_requires_matching_passwords_and_leaves_role_unassigned(self):
        root = Path(__file__).resolve().parents[1]
        with patch.dict(os.environ, {'STORAGE_BACKEND': 'supabase',
                                    'APP_PUBLIC_URL': 'http://localhost:8504/'}), \
             patch('repository.SupabaseRepository.sign_up') as sign_up:
            app = AppTest.from_file(str(root / 'keyword_app2_fixed272.py'))
            app.run(timeout=30)
            app.button(key='cloud_signup_open').click().run(timeout=30)
            app.text_input(key='cloud_signup_email').set_value('member@example.test')
            app.text_input(key='cloud_signup_password').set_value('Safe-test-password-123!')
            app.text_input(key='cloud_signup_password_confirm').set_value('different-password')
            app.button(key='cloud_signup_submit').click().run(timeout=30)
            self.assertEqual(len(app.exception), 0)
            sign_up.assert_not_called()
            self.assertEqual(len(app.error), 1)

            app.text_input(key='cloud_signup_password_confirm').set_value('Safe-test-password-123!')
            app.button(key='cloud_signup_submit').click().run(timeout=30)

        self.assertEqual(len(app.exception), 0)
        sign_up.assert_called_once()
        self.assertEqual(sign_up.call_args.args[:2], (
            'member@example.test', 'Safe-test-password-123!'))
        self.assertNotIn('auth_session', app.session_state)
        self.assertEqual(app.session_state['auth_view'], 'login')
        self.assertEqual(len(app.success), 1)

    def test_password_update_uses_recovery_token_as_user_bearer(self):
        with patch('repository.requests.request', return_value=self.response()) as request:
            SupabaseRepository().update_password('recovery-token', 'new-test-password')

        method, url = request.call_args.args[:2]
        headers = request.call_args.kwargs['headers']
        self.assertEqual((method, url), ('PUT',
                         'https://project.example.supabase.co/auth/v1/user'))
        self.assertEqual(headers['Authorization'], 'Bearer recovery-token')
        self.assertEqual(headers['apikey'], 'server-only-test-key')
        self.assertEqual(request.call_args.kwargs['json'], {
            'password': 'new-test-password'})

    def test_recovery_screen_saves_password_from_link_token(self):
        root = Path(__file__).resolve().parents[1]
        with patch.dict(os.environ, {'STORAGE_BACKEND': 'supabase'}), \
             patch('repository.SupabaseRepository.update_password') as update:
            app = AppTest.from_file(str(root / 'keyword_app2_fixed272.py'))
            app.session_state['cloud_password_recovery'] = {
                'hash': '#access_token=recovery-test&token_type=bearer&type=recovery'}
            app.run(timeout=30)
            self.assertEqual(app.subheader[0].value, '\uc0c8 \ube44\ubc00\ubc88\ud638 \uc124\uc815')
            app.text_input[0].input('New-test-password-123!')
            app.text_input[1].input('New-test-password-123!')
            app.button[0].click().run(timeout=30)

        update.assert_called_once_with('recovery-test', 'New-test-password-123!')
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.success), 1)
