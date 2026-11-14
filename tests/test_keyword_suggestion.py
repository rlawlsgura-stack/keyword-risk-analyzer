import json
import unittest
from datetime import date
from unittest.mock import patch

import pandas as pd
import requests
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from api import KeywordSuggestionRequest, keyword_suggestion, save_ocr_keywords
from keyword_suggestion import SuggestionProviderError, suggest_keyword
from matching_engine import DB_COLS


class Repository:
    def load_keywords(self):
        return pd.DataFrame([{
            DB_COLS[0]: 'K001', DB_COLS[1]: '유사 표현', DB_COLS[2]: '화장품',
            DB_COLS[3]: '3등급', DB_COLS[4]: '권장 표현', DB_COLS[5]: '표현 확인',
            DB_COLS[6]: '시험자료',
        }])


class HospitalRepository:
    def load_keywords(self):
        return pd.DataFrame([
            {DB_COLS[0]: 'B048', DB_COLS[1]: '병균', DB_COLS[2]: '화장품',
             DB_COLS[3]: '1등급(사용금지)', DB_COLS[4]: '-', DB_COLS[5]: '(사용금지)', DB_COLS[6]: '-'},
            {DB_COLS[0]: 'B007', DB_COLS[1]: 'OO 병원에서 추천하는 안전한 화장품', DB_COLS[2]: '화장품',
             DB_COLS[3]: '1등급(사용금지)', DB_COLS[4]: '-', DB_COLS[5]: '(사용금지)', DB_COLS[6]: '-'},
            {DB_COLS[0]: 'G068', DB_COLS[1]: '병원/약국판매 건강기능식품', DB_COLS[2]: '건강기능식품',
             DB_COLS[3]: '3등급(조건부사용)', DB_COLS[4]: '-', DB_COLS[5]: '판매 장소에 따른 표현 검토', DB_COLS[6]: ''},
        ])


class Response:
    def __init__(self, suggestion):
        self.suggestion = suggestion

    def raise_for_status(self):
        pass

    def json(self):
        return {'output': [{'type': 'message', 'content': [
            {'type': 'output_text', 'text': json.dumps(self.suggestion, ensure_ascii=False)}]}]}


class KeywordSuggestionTests(unittest.TestCase):
    def suggest(self, suggestion):
        with patch.dict('os.environ', {
            'REGULATION_LLM_ENABLED': 'true', 'REGULATION_LLM_MODEL': 'test-model',
            'OPENAI_API_KEY': 'test-key', 'LEGISLATION_API_KEY': '',
            'REGULATION_EMBEDDINGS_ENABLED': 'false',
        }), patch('keyword_suggestion.search_documents', return_value=([], 'none')), \
                patch('keyword_suggestion.requests.post', return_value=Response(suggestion)):
            return suggest_keyword(Repository(), '새 표현', '', '', date(2026, 11, 12))

    def test_supported_draft_is_reviewable_and_does_not_write_catalog(self):
        result = self.suggest({
            'status': 'suggested', 'category': '화장품', 'risk': '3등급',
            'criteria': '표현 확인', 'evidence_type': '시험자료', 'alternative': '권장 표현',
            'reason': '기존 유사 사례를 참고했습니다.', 'source_ids': ['DB1'],
        })
        self.assertEqual(result['status'], 'suggested')
        self.assertEqual(result['sources'][0]['id'], 'DB1')
        self.assertEqual(result['category'], '화장품')

    def test_unverified_model_fields_are_not_applied(self):
        result = self.suggest({
            'status': 'suggested', 'category': '존재하지 않는 분류', 'risk': '3등급',
            'criteria': '임의 기준', 'evidence_type': '시험자료', 'alternative': '-',
            'reason': '모델 추정', 'source_ids': ['LAW999'],
        })
        self.assertEqual(result['status'], 'insufficient')
        self.assertEqual(result['category'], '')
        self.assertEqual(result['source_ids'], [])

    def test_short_ambiguous_term_offers_relevant_db_categories(self):
        with patch.dict('os.environ', {
            'REGULATION_LLM_ENABLED': 'true', 'REGULATION_LLM_MODEL': 'test-model',
            'OPENAI_API_KEY': 'test-key', 'LEGISLATION_API_KEY': '',
            'REGULATION_EMBEDDINGS_ENABLED': 'false',
        }), patch('keyword_suggestion.requests.post') as model_call, \
                patch('keyword_suggestion.search_documents') as document_search:
            result = suggest_keyword(HospitalRepository(), '병원', '', '', date(2026, 11, 12))
        self.assertEqual(result['status'], 'needs_category')
        self.assertEqual({option['category'] for option in result['category_options']},
                         {'화장품', '건강기능식품'})
        self.assertEqual({source['label'].split()[-1] for source in result['sources']},
                         {'B007', 'G068'})
        self.assertEqual(model_call.call_count, 2)
        self.assertEqual(document_search.call_count, 2)

    def test_selected_category_uses_applicable_db_row(self):
        suggestion = {'status': 'suggested', 'category': '화장품', 'risk': '1등급(사용금지)',
                      'criteria': '병원 추천을 암시하는 광고 표현 검토', 'evidence_type': '',
                      'alternative': '', 'reason': '기존 화장품 DB 사례', 'source_ids': ['DB1']}
        with patch.dict('os.environ', {
            'REGULATION_LLM_ENABLED': 'true', 'REGULATION_LLM_MODEL': 'test-model',
            'OPENAI_API_KEY': 'test-key', 'LEGISLATION_API_KEY': '',
            'REGULATION_EMBEDDINGS_ENABLED': 'false',
        }), patch('keyword_suggestion.search_documents', return_value=([], 'none')), \
                patch('keyword_suggestion.requests.post', return_value=Response(suggestion)):
            result = suggest_keyword(HospitalRepository(), '병원', '화장품', '', date(2026, 11, 12))
        self.assertEqual(result['status'], 'suggested')
        self.assertEqual(result['risk'], '1등급(사용금지)')
        self.assertEqual(len(result['sources']), 1)
        self.assertIn('B007', result['sources'][0]['label'])

    def test_selected_category_rejects_risk_not_supported_by_matching_db_row(self):
        suggestion = {'status': 'suggested', 'category': '화장품', 'risk': '3등급(조건부사용)',
                      'criteria': '조건부 검토', 'evidence_type': '', 'alternative': '',
                      'reason': '모델 추정', 'source_ids': ['DB1']}
        with patch.dict('os.environ', {
            'REGULATION_LLM_ENABLED': 'true', 'REGULATION_LLM_MODEL': 'test-model',
            'OPENAI_API_KEY': 'test-key', 'LEGISLATION_API_KEY': '',
            'REGULATION_EMBEDDINGS_ENABLED': 'false',
        }), patch('keyword_suggestion.search_documents', return_value=([], 'none')), \
                patch('keyword_suggestion.requests.post', return_value=Response(suggestion)) as model_call:
            result = suggest_keyword(HospitalRepository(), '병원', '화장품', '', date(2026, 11, 12))
        self.assertEqual(result['status'], 'insufficient')
        prompt = json.loads(model_call.call_args.kwargs['json']['input'][1]['content'])
        self.assertEqual(prompt['allowed_categories'], ['화장품'])
        self.assertEqual(prompt['allowed_risks'], ['1등급(사용금지)'])

    def test_short_term_does_not_fuzzy_match_unrelated_word(self):
        repository = HospitalRepository()
        repository.load_keywords = lambda: pd.DataFrame([HospitalRepository().load_keywords().iloc[0]])
        with patch.dict('os.environ', {
            'REGULATION_LLM_ENABLED': 'true', 'REGULATION_LLM_MODEL': 'test-model',
            'OPENAI_API_KEY': 'test-key', 'LEGISLATION_API_KEY': '',
            'REGULATION_EMBEDDINGS_ENABLED': 'false',
        }), patch('keyword_suggestion.search_documents', return_value=([], 'none')), \
                patch('keyword_suggestion.requests.post') as model_call:
            result = suggest_keyword(repository, '병원', '', '', date(2026, 11, 12))
        self.assertEqual(result['status'], 'insufficient')
        self.assertEqual(result['sources'], [])
        model_call.assert_not_called()

    def test_member_cannot_register_ocr_keywords(self):
        repository = Repository()
        repository.user = lambda _token: {'app_metadata': {'role': 'member'}}
        with self.assertRaises(HTTPException) as raised:
            save_ocr_keywords(None, actor='member',
                              credentials=HTTPAuthorizationCredentials(scheme='Bearer', credentials='test'),
                              repository=repository)
        self.assertEqual(raised.exception.status_code, 403)

    def test_missing_evidence_abstains_without_calling_model(self):
        repository = Repository()
        repository.load_keywords = lambda: pd.DataFrame(columns=DB_COLS)
        with patch.dict('os.environ', {
            'REGULATION_LLM_ENABLED': 'true', 'REGULATION_LLM_MODEL': 'test-model',
            'OPENAI_API_KEY': 'test-key', 'LEGISLATION_API_KEY': '',
        }), patch('keyword_suggestion.search_documents', return_value=([], 'none')), \
                patch('keyword_suggestion.requests.post') as model_call:
            result = suggest_keyword(repository, '근거 없는 표현', '', '', date(2026, 11, 12))
        self.assertEqual(result['status'], 'insufficient')
        model_call.assert_not_called()

    def test_missing_model_configuration_is_reported(self):
        with patch.dict('os.environ', {'REGULATION_LLM_ENABLED': 'false'}):
            with self.assertRaises(RuntimeError):
                suggest_keyword(Repository(), '새 표현', '', '', date(2026, 11, 12))

    def test_openai_http_error_keeps_status_without_exposing_response(self):
        response = requests.Response()
        response.status_code = 429
        response._content = b'sensitive provider response'
        with patch.dict('os.environ', {
            'REGULATION_LLM_ENABLED': 'true', 'REGULATION_LLM_MODEL': 'test-model',
            'OPENAI_API_KEY': 'test-key', 'REGULATION_EMBEDDINGS_ENABLED': 'false',
        }), patch('keyword_suggestion.search_documents', return_value=([], 'none')), \
                patch('keyword_suggestion.requests.post', return_value=response):
            with self.assertRaises(SuggestionProviderError) as raised:
                suggest_keyword(Repository(), '유사', '화장품', '', date(2026, 11, 12))
        self.assertEqual(raised.exception.status_code, 429)
        self.assertNotIn('sensitive', str(raised.exception))

    def test_suggestion_endpoint_reports_provider_limit(self):
        with patch('api.suggest_keyword', side_effect=SuggestionProviderError(429)):
            with self.assertRaises(HTTPException) as raised:
                keyword_suggestion(KeywordSuggestionRequest(term='미세먼지'),
                                   actor='member', repository=Repository())
        self.assertEqual(raised.exception.status_code, 429)
        self.assertIn('사용 한도', raised.exception.detail)


if __name__ == '__main__':
    unittest.main()
