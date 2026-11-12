import json
import unittest
from datetime import date
from unittest.mock import patch

import pandas as pd
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from api import save_ocr_keywords
from keyword_suggestion import suggest_keyword
from matching_engine import DB_COLS


class Repository:
    def load_keywords(self):
        return pd.DataFrame([{
            DB_COLS[0]: 'K001', DB_COLS[1]: '유사 표현', DB_COLS[2]: '화장품',
            DB_COLS[3]: '3등급', DB_COLS[4]: '권장 표현', DB_COLS[5]: '표현 확인',
            DB_COLS[6]: '시험자료',
        }])


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


if __name__ == '__main__':
    unittest.main()
