from pathlib import Path
import unittest
from unittest import TestCase
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit
import os

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
