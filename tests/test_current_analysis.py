"""Focused parity and retry checks for the React analysis path."""
import unittest
from unittest.mock import patch
from uuid import uuid4

import pandas as pd
from fastapi.testclient import TestClient

import api
from matching_engine import DB_COLS
from service import analyze_current


class MemoryRepository:
    def __init__(self):
        self.keywords = pd.DataFrame([dict(zip(DB_COLS, [
            'A001', '필러', '화장품', '1등급', '-', '-', '-', '0', '',
        ]))])
        self.keywords.attrs['revision'] = 1
        self.saved = {}
        self.history_writes = 0
        self.collection_calls = 0
        self.fail_collection = False

    def load_keywords(self):
        return self.keywords.copy()

    def load_setting(self, name, default):
        return default

    def previous_analysis(self, analysis_id, actor, fingerprint=None):
        entry = self.saved.get(analysis_id)
        if entry and entry[0:2] != (actor, fingerprint):
            raise ValueError('Analysis ID conflict')
        return entry[2] if entry else None

    def record_analysis(self, analysis_id, fingerprint, actor, revision, result):
        self.history_writes += 1
        self.saved[analysis_id] = (actor, fingerprint, result)
        return result

    def collect_unmatched_terms(self, analysis_id, candidates):
        self.collection_calls += 1
        if self.fail_collection:
            raise RuntimeError('temporary storage failure')


class CurrentAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.repository = MemoryRepository()
        self.request = {
            'analysis_id': str(uuid4()), 'text': '필러', 'mode': 'exact',
            'partial_min_len': 2, 'strip_bracket_notes': True,
            'normalize_whitespace': True, 'ignore_case': True,
            'normalize_symbols': True, 'categories': [], 'risks': [],
        }

    def test_filtered_match_still_covers_unmatched_collection_and_retry(self):
        self.request['categories'] = ['다른 카테고리']
        covered = []

        def capture(_text, matches, *, limit):
            covered.extend(matches)
            return []

        with patch('auxiliary_analysis.extract_unmatched_term_surfaces', side_effect=capture):
            first = analyze_current(self.repository, self.request, 'user-1')
            second = analyze_current(self.repository, self.request, 'user-1')
        self.assertEqual(first, second)
        self.assertEqual(first['matches'], [])
        self.assertFalse(first['recorded'])
        self.assertFalse(first['unmatched_collection_pending'])
        self.assertEqual([match.kwd_no for match in covered], ['A001', 'A001'])
        self.assertEqual(self.repository.collection_calls, 2)
        self.assertEqual(self.repository.history_writes, 0)

    def test_candidate_collection_failure_does_not_hide_analysis_and_retries(self):
        self.repository.fail_collection = True
        first = analyze_current(self.repository, self.request, 'user-1')
        self.assertEqual(first['unique_keywords'], ['A001'])
        self.assertTrue(first['recorded'])
        self.assertTrue(first['unmatched_collection_pending'])
        self.assertEqual(self.repository.history_writes, 1)

        self.repository.fail_collection = False
        retried = analyze_current(self.repository, self.request, 'user-1')
        self.assertFalse(retried['unmatched_collection_pending'])
        self.assertEqual(retried['analysis_id'], self.request['analysis_id'])
        self.assertEqual(self.repository.collection_calls, 2)
        self.assertEqual(self.repository.history_writes, 1)

    def test_api_rejects_integration_token_for_recorded_analysis(self):
        api.app.dependency_overrides[api.current_actor] = lambda: 'integration'
        api.app.dependency_overrides[api.get_repository] = lambda: self.repository
        try:
            with TestClient(api.app) as client:
                response = client.post('/api/v2/analyses', json=self.request)
            self.assertEqual(response.status_code, 403)
            self.assertEqual(self.repository.history_writes, 0)
        finally:
            api.app.dependency_overrides.clear()

    def test_api_keeps_no_hit_analysis_out_of_history(self):
        request = {**self.request, 'categories': ['nonexistent-category']}
        api.app.dependency_overrides[api.current_actor] = lambda: 'user-1'
        api.app.dependency_overrides[api.get_repository] = lambda: self.repository
        try:
            with TestClient(api.app) as client:
                response = client.post('/api/v2/analyses', json=request)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertFalse(response.json()['recorded'])
            self.assertFalse(response.json()['unmatched_collection_pending'])
            self.assertEqual(self.repository.history_writes, 0)
        finally:
            api.app.dependency_overrides.clear()


if __name__ == '__main__':
    unittest.main()
