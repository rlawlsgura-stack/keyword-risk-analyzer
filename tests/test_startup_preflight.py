import unittest
from unittest.mock import Mock

import requests

from scripts.check_supabase_connectivity import PreflightError, check_supabase_connection


class SupabaseStartupPreflightTests(unittest.TestCase):
    def test_csv_mode_does_not_make_network_request(self):
        get = Mock()
        result = check_supabase_connection('csv', '', '', get=get)
        self.assertIn('skipped', result)
        get.assert_not_called()

    def test_supabase_mode_checks_auth_health_without_logging_key(self):
        get = Mock(return_value=Mock(status_code=200))
        result = check_supabase_connection(
            'supabase', 'https://project.example.supabase.co', 'secret-test-key', get=get)
        self.assertIn('HTTP 200', result)
        get.assert_called_once_with(
            'https://project.example.supabase.co/auth/v1/health',
            headers={'apikey': 'secret-test-key'}, timeout=(5, 8))

    def test_network_error_stops_startup_with_actionable_message(self):
        get = Mock(side_effect=requests.ConnectionError('blocked'))
        with self.assertRaisesRegex(PreflightError, 'DNS, firewall, VPN'):
            check_supabase_connection(
                'supabase', 'https://project.example.supabase.co', 'secret-test-key', get=get)


if __name__ == '__main__':
    unittest.main()
