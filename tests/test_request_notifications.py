import unittest
from unittest.mock import Mock

from request_notifications import (
    NotificationConfigurationError,
    NotificationDeliveryError,
    send_keyword_request_email,
)


class RequestNotificationTests(unittest.TestCase):
    def setUp(self):
        self.env = {
            'RESEND_API_KEY': 'test-key',
            'KEYWORD_REQUEST_ADMIN_EMAIL': 'admin@example.com',
            'KEYWORD_REQUEST_FROM_EMAIL': 'Keyword Desk <notify@example.com>',
        }
        self.row = {
            'id': 'request-123',
            'kwd_no': 'B101',
            'keyword_name': '<피부>',
            'request_type': 'risk_grade_adjustment',
            'requester_email': 'member@example.com',
            'request_detail': '<script>alert(1)</script>',
            'created_at': '2026-10-25T01:00:00Z',
        }

    def test_sends_html_escaped_email_with_idempotency_key(self):
        response = Mock(status_code=200)
        post = Mock(return_value=response)

        self.assertTrue(send_keyword_request_email(self.row, env=self.env, post=post))
        args, kwargs = post.call_args
        self.assertEqual(args[0], 'https://api.resend.com/emails')
        self.assertEqual(kwargs['headers']['Idempotency-Key'], 'keyword-request/request-123')
        self.assertIn('&lt;script&gt;', kwargs['json']['html'])
        self.assertNotIn('<script>', kwargs['json']['html'])
        self.assertEqual(kwargs['json']['to'], ['admin@example.com'])

    def test_missing_configuration_fails_before_network_request(self):
        post = Mock()
        with self.assertRaises(NotificationConfigurationError):
            send_keyword_request_email(self.row, env={}, post=post)
        post.assert_not_called()

    def test_provider_error_is_reported_without_response_body(self):
        post = Mock(return_value=Mock(status_code=429, text='secret provider details'))
        with self.assertRaisesRegex(NotificationDeliveryError, 'HTTP 429') as error:
            send_keyword_request_email(self.row, env=self.env, post=post)
        self.assertNotIn('secret provider details', str(error.exception))


if __name__ == '__main__':
    unittest.main()
