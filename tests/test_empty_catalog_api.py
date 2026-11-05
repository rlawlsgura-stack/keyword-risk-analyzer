"""Read-only API regressions for a fresh local database; no external DB needed."""
import unittest
from unittest.mock import Mock

import pandas as pd
from fastapi.testclient import TestClient

import api
from matching_engine import DB_COLS, MatchingConfig, _KO_SUFFIX_WHITELIST


class EmptyCatalogApiTests(unittest.TestCase):
    def setUp(self):
        self.repository = Mock()
        self.frame = pd.DataFrame(columns=DB_COLS)
        self.frame.attrs['revision'] = 6
        self.repository.load_keywords.side_effect = lambda: self.frame.copy()
        self.repository.load_setting.side_effect = lambda name, default: default
        self.repository.user.return_value = {'app_metadata': {'role': 'admin'}}
        api.app.dependency_overrides[api.get_repository] = lambda: self.repository
        api.app.dependency_overrides[api.current_actor] = lambda: 'test-admin'
        self.addCleanup(api.app.dependency_overrides.clear)
        self.client = TestClient(api.app)

    def test_empty_catalog_search_and_filters_return_empty_page(self):
        for params in ({}, {'q': '안티에이징'},
                       {'q': '[', 'category': '화장품', 'risk': '1등급', 'evidence_type': '-'}):
            with self.subTest(params=params):
                response = self.client.get('/api/v1/keywords', params=params)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), {'total': 0, 'revision': 6, 'items': []})

    def test_nonempty_catalog_retains_literal_search_and_combined_filters(self):
        self.frame = pd.DataFrame([
            dict(zip(DB_COLS, ['A001', '안티[에이징]', '화장품', '1등급', '보습', '-', '-', '0', ''])),
            dict(zip(DB_COLS, ['B001', '안티[에이징]', '식품', '2등급', '-', '-', '-', '0', ''])),
        ])
        self.frame.attrs['revision'] = 7
        for query in ('[', '보습', 'a001'):
            with self.subTest(query=query):
                response = self.client.get('/api/v1/keywords', params={
                    'q': query, 'category': '화장품', 'risk': '1등급', 'evidence_type': '-',
                })
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()['total'], 1)
                self.assertEqual(response.json()['items'][0]['kwd_no'], 'A001')

    def test_unconfigured_normalization_uses_matching_defaults(self):
        response = self.client.get('/api/v1/admin/normalization-settings',
                                   headers={'Authorization': 'Bearer test-token'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            'ignored_symbols': list(MatchingConfig().ignored_symbols),
            'extra_suffixes': [], 'default_suffix_count': len(_KO_SUFFIX_WHITELIST),
        })
        self.repository.save_setting.assert_not_called()

    def test_saved_normalization_is_preserved(self):
        self.repository.load_setting.side_effect = lambda name, default: {
            'ignored_special_symbols': {'symbols': ['#', '/']},
            'ko_suffix_whitelist': {'extra_suffixes': ['이라도']},
        }.get(name, default)
        response = self.client.get('/api/v1/admin/normalization-settings',
                                   headers={'Authorization': 'Bearer test-token'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['ignored_symbols'], ['#', '/'])
        self.assertEqual(response.json()['extra_suffixes'], ['이라도'])

    def test_normalization_still_requires_admin(self):
        self.repository.user.return_value = {'app_metadata': {'role': 'member'}}
        response = self.client.get('/api/v1/admin/normalization-settings',
                                   headers={'Authorization': 'Bearer test-token'})
        self.assertEqual(response.status_code, 403)
        self.repository.load_setting.assert_not_called()


if __name__ == '__main__':
    unittest.main()
