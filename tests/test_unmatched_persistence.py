import os
from uuid import uuid4
import unittest
from unittest.mock import patch

from repository import SupabaseRepository
from unmatched_collection import ocr_collection_text


class UnmatchedPersistenceTests(unittest.TestCase):
    def setUp(self):
        with patch.dict(os.environ, {'SUPABASE_URL': 'https://example.supabase.co',
                                     'SUPABASE_SECRET_KEY': 'test-only'}):
            self.repository = SupabaseRepository()

    def test_collection_sends_only_expressions_counts_and_anonymous_id(self):
        event = str(uuid4())
        with patch.object(self.repository, 'rpc', return_value=1) as rpc:
            self.repository.collect_unmatched_terms(event, [
                {'surface_key': '보습', 'surface': '보습', 'occurrences': 3,
                 'account': 'must-not-be-sent', 'text': 'must-not-be-sent'},
            ])
        rpc.assert_called_once_with('collect_unmatched_terms', p_id=event, p_terms=[
            {'term_norm': '보습', 'display_term': '보습', 'occurrences': 3}])

    def test_delete_checks_live_administrator_role_before_writing(self):
        with patch.object(self.repository, 'user', return_value={
                'app_metadata': {'role': 'member'}}), patch.object(self.repository, 'rpc') as rpc:
            with self.assertRaises(PermissionError):
                self.repository.delete_unmatched_terms(['보습'], 'member-token')
            rpc.assert_not_called()
        with patch.object(self.repository, 'user', return_value={
                'app_metadata': {'role': 'admin'}}) as user, \
                patch.object(self.repository, 'rpc', return_value=1) as rpc:
            self.assertEqual(self.repository.delete_unmatched_terms(['보습'], 'admin-token'), 1)
            user.assert_called_once_with('admin-token')
            rpc.assert_called_once_with('delete_unmatched_terms', p_terms=['보습'])

    def test_registration_requests_are_submitted_to_the_separate_queue(self):
        with patch.object(self.repository, 'user', return_value={'id': str(uuid4())}) as user, \
                patch.object(self.repository, 'request', return_value=[{'id': 'queued'}]) as request:
            result = self.repository.submit_unmatched_registration_requests([
                {'term': 'candidate', 'source_terms': 'source', 'occurrences': 3,
                 'category': 'Food', 'risk': '2', 'criteria': 'review',
                 'evidence_type': 'document', 'alternative': '-'},
            ], 'member-token')
        self.assertEqual(result, [{'id': 'queued'}])
        user.assert_called_once_with('member-token')
        request.assert_called_once_with(
            'POST', '/rest/v1/kra_unmatched_registration_requests',
            [{'term': 'candidate', 'term_norm': 'candidate', 'source_terms': 'source', 'occurrences': 3,
              'category': 'Food', 'risk': '2', 'criteria': 'review',
              'evidence_type': 'document', 'alternative': '-'}],
            prefer='return=representation')

    def test_sidebar_registration_requests_are_deduplicated_without_statistics(self):
        with patch.object(self.repository, 'user', return_value={'id': str(uuid4())}) as user, \
                patch.object(self.repository, 'rpc', return_value=2) as rpc:
            count = self.repository.submit_new_keyword_registration_requests(
                ['Alpha', 'ＡＬＰＨＡ', '키워드'], 'member-token')
        self.assertEqual(count, 2)
        user.assert_called_once_with('member-token')
        rpc.assert_called_once_with('submit_new_keyword_registration_requests', p_terms=[
            {'term': 'Alpha', 'term_norm': 'alpha'},
            {'term': '키워드', 'term_norm': '키워드'},
        ])

    def test_registration_queue_read_and_delete_require_admin(self):
        with patch.object(self.repository, 'user', return_value={
                'app_metadata': {'role': 'member'}}), patch.object(self.repository, 'request') as request:
            with self.assertRaises(PermissionError):
                self.repository.load_unmatched_registration_requests('member-token')
            with self.assertRaises(PermissionError):
                self.repository.delete_unmatched_registration_requests([str(uuid4())], 'member-token')
            request.assert_not_called()
        request_id = str(uuid4())
        with patch.object(self.repository, 'user', return_value={
                'app_metadata': {'role': 'admin'}}), \
                patch.object(self.repository, 'request', return_value=[{'id': request_id}]) as request:
            self.assertEqual(self.repository.load_unmatched_registration_requests('admin-token'), [{'id': request_id}])
            self.assertEqual(self.repository.delete_unmatched_registration_requests(
                [request_id], 'admin-token'), 1)
        self.assertEqual(request.call_count, 2)
        self.assertEqual(request.call_args.args[0], 'DELETE')
        self.assertIn('/rest/v1/kra_unmatched_registration_requests?', request.call_args.args[1])

    def test_ocr_threshold_is_inclusive_and_keeps_repeated_lines(self):
        text = ocr_collection_text([{'lines': [
            {'text': '보습', 'confidence': 0.60},
            {'text': '보습', 'confidence': 0.99},
            {'text': '제외', 'confidence': 0.5999},
            {'text': '제외', 'confidence': float('nan')},
            {'text': '제외', 'confidence': 'invalid'},
        ]}, {'error': 'failed', 'lines': [{'text': '제외', 'confidence': 1}]}])
        self.assertEqual(text, '보습\n보습')


if __name__ == '__main__':
    unittest.main()
