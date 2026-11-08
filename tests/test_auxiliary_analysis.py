import os
import unittest
from unittest.mock import Mock, patch

import pandas as pd
from fastapi.testclient import TestClient

import api
from auxiliary_analysis import (AuxiliaryUnavailable, _catalog_batch, _embed,
                                analyze_auxiliary, morphology_candidates)


class AuxiliaryTests(unittest.TestCase):
    def setUp(self):
        self.df = pd.DataFrame([
            {'kwd_no': 'K1', '키워드명': '개선하다', '상품카테고리': '화장품', '리스크 등급': '1'},
            {'kwd_no': 'K2', '키워드명': '지방', '상품카테고리': '식품', '리스크 등급': '2'},
        ])
        _catalog_batch.cache_clear()

    def test_real_kiwi_handles_inflection_without_joining_distinct_words(self):
        candidates = morphology_candidates('개선했어요. 마사지 방법입니다.', self.df.to_dict('records'), 10)
        self.assertEqual([item['kwd_no'] for item in candidates], ['K1'])
        self.assertEqual(candidates[0]['start'], 0)
        self.assertTrue(candidates[0]['end'] > 0)

    def test_semantics_preserves_context_filters_before_embedding_and_caches_catalog(self):
        original = self.df.copy(deep=True)
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}), \
             patch('auxiliary_analysis._embed', return_value=[[1.0, 0.0]]) as embed:
            for _ in range(2):
                result = analyze_auxiliary('효과가 없습니다.', self.df, categories=['화장품'],
                                           kiwi=False, embeddings=True)
                self.assertEqual(result['embeddings']['candidates'][0]['kwd_no'], 'K1')
            self.assertEqual(embed.call_count, 3)  # Two original queries; one cached catalog.
            self.assertEqual(embed.call_args_list[0].args[0], ('효과가 없습니다.',))
            self.assertNotIn('지방', str(embed.call_args_list))
            self.df.loc[0, '키워드명'] = '노화 방지'
            analyze_auxiliary('효과가 없습니다.', self.df, categories=['화장품'],
                              kiwi=False, embeddings=True)
            self.assertEqual(embed.call_count, 5)  # Changed catalog invalidates vectors.
        self.df.loc[0, '키워드명'] = original.loc[0, '키워드명']
        pd.testing.assert_frame_equal(self.df, original)

    def test_provider_errors_do_not_discard_kiwi_or_expose_response_secrets(self):
        response = Mock(status_code=429, text='sensitive server response')
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}), \
             patch('auxiliary_analysis.requests.post', return_value=response):
            result = analyze_auxiliary('개선했어요', self.df, embeddings=True)
            self.assertEqual(result['kiwi']['status'], 'ok')
            self.assertEqual(result['embeddings']['status'], 'unavailable')
            self.assertNotIn('sensitive', str(result))
        response = Mock(status_code=200)
        response.json.return_value = {'data': [{'index': 0, 'embedding': [float('nan')]}]}
        with patch('auxiliary_analysis.requests.post', return_value=response):
            with self.assertRaises(AuxiliaryUnavailable):
                _embed(['test'], 'test', 'test-key')

    def test_auxiliary_endpoint_is_retired(self):
        with TestClient(api.app) as client:
            response = client.post('/api/v1/auxiliary-analyses', json={'text': 'test'})
            self.assertEqual(response.status_code, 404)


if __name__ == '__main__':
    unittest.main()
