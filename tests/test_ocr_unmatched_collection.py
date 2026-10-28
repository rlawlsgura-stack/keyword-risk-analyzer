import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

import pandas as pd
from streamlit.testing.v1 import AppTest

from matching_engine import DB_COLS, MATCH_MODES


class OCRUnmatchedCollectionTests(unittest.TestCase):
    def test_preview_click_collects_unmatched_terms_without_second_analysis(self):
        keywords = pd.DataFrame([dict(zip(DB_COLS, [
            'A001', '필러', '화장품', '1등급(사용금지)', '-', '-', '-', '0', ''
        ]))])
        keywords.attrs['revision'] = 1
        repository = Mock()
        repository.user.return_value = {
            'id': str(uuid4()), 'email': 'member@example.test',
            'app_metadata': {'role': 'member'},
        }
        repository.load_keywords.side_effect = keywords.copy
        repository.load_setting.side_effect = lambda name, default: default
        repository.load_hits.return_value = pd.DataFrame(columns=['ts', 'kwd_no'])
        repository.load_keyword_requests.return_value = []
        repository.load_unmatched_terms.return_value = {'rows': [], 'total': 0}
        source = Path(__file__).resolve().parents[1] / 'keyword_app2_fixed297.py'

        for text, collect in [('필러 보습 관리', True), ('보습 관리', True),
                              ('필러 보습 관리', False)]:
            with self.subTest(text=text, collect=collect), \
                    patch.dict(os.environ, {
                        'STORAGE_BACKEND': 'supabase',
                        'SUPABASE_URL': 'https://example.supabase.co',
                        'SUPABASE_SECRET_KEY': 'test-only',
                    }), \
                    patch('repository.SupabaseRepository', return_value=repository), \
                    patch('repository.requests.request', side_effect=AssertionError('Unexpected network')):
                repository.record_analysis.reset_mock()
                repository.collect_unmatched_terms.reset_mock()
                app = AppTest.from_file(str(source), default_timeout=30)
                app.session_state['auth_session'] = {
                    'access_token': 'test-token', 'expires_at': 9999999999,
                }
                app.session_state['main_app_tabs'] = '이미지 OCR분석'
                app.session_state['match_mode'] = MATCH_MODES['exact']
                app.session_state['collect_unmatched_pool'] = collect
                app.session_state['ocr_keyword_candidates'] = [
                    {'term': term, 'confidence': 0.98, 'category': '', 'risk': '',
                     'alternative': '-', 'detail': '', 'evidence': '',
                     'approved': approved, 'duplicate': ''}
                    for term, approved in [(text, True), ('제외어', False)]
                ]
                app.run()
                self.assertFalse(app.exception)

                app.button(key='ocr_keyword_preview_analysis').click().run()

                self.assertFalse(app.exception)
                self.assertFalse(app.error)
                self.assertEqual(app.session_state['analysis_input_text'], text)
                # Collection remains mandatory even with an old unchecked preference.
                repository.collect_unmatched_terms.assert_called_once()
                event, candidates = repository.collect_unmatched_terms.call_args.args
                self.assertTrue(event)
                self.assertEqual({row['surface_key'] for row in candidates}, {'보습', '관리'})
                self.assertTrue(all(row['occurrences'] == 1 for row in candidates))
                if '필러' in text:
                    self.assertTrue(app.session_state['analysis_highlight_html'])
                    repository.record_analysis.assert_called_once()

                # Ordinary rerenders must not collect the same analysis twice.
                app.run()
                self.assertFalse(app.exception)
                repository.collect_unmatched_terms.assert_called_once()
                if '필러' in text:
                    repository.record_analysis.assert_called_once()


if __name__ == '__main__':
    unittest.main()
