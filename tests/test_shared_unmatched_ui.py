import io
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

import pandas as pd
from PIL import Image
from streamlit.testing.v1 import AppTest

from matching_engine import DB_COLS, MATCH_MODES
from repository import StorageError


class SharedUnmatchedUITests(unittest.TestCase):
    def setUp(self):
        self.repository = Mock()
        keywords = pd.DataFrame([dict(zip(DB_COLS, [
            'A001', '필러', '화장품', '1등급(사용금지)', '-', '-', '-', '0', ''
        ]))])
        keywords.attrs['revision'] = 1
        self.repository.load_keywords.side_effect = keywords.copy
        self.repository.load_setting.side_effect = lambda name, default: default
        self.repository.load_hits.return_value = pd.DataFrame(columns=['ts', 'kwd_no'])
        self.repository.load_keyword_requests.return_value = []
        self.repository.load_unmatched_terms.return_value = {'rows': [], 'total': 0}
        for patcher in [patch.dict(os.environ, {
                'STORAGE_BACKEND': 'supabase', 'SUPABASE_URL': 'https://example.supabase.co',
                'SUPABASE_SECRET_KEY': 'test-only'}),
                patch('repository.SupabaseRepository', return_value=self.repository),
                patch('repository.requests.request', side_effect=AssertionError('Unexpected network'))]:
            patcher.start()
            self.addCleanup(patcher.stop)

    def app(self, role='member', tab='스크립트 분석'):
        self.repository.user.return_value = {
            'id': str(uuid4()), 'email': 'test@example.test', 'app_metadata': {'role': role}}
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'keyword_app2_fixed292.py'),
                                default_timeout=30)
        app.session_state['auth_session'] = {'access_token': 'test-token', 'expires_at': 9999999999}
        app.session_state['main_app_tabs'] = tab
        app.session_state['match_mode'] = MATCH_MODES['exact']
        return app

    def seed_shared_row(self):
        row = {'term_norm': '보습', 'display_term': '보습', 'total_occurrences': 3,
               'analysis_count': 2, 'first_seen': '2026-10-28T00:00:00Z',
               'last_seen': '2026-10-28T01:00:00Z', 'review_status': 'pending'}
        self.repository.load_unmatched_terms.return_value = {'rows': [row], 'total': 1}
        return row

    def test_shared_rows_load_after_logout_and_under_another_account(self):
        self.seed_shared_row()
        first = self.app(tab='미매칭 후보군').run()
        self.assertFalse(first.exception)
        self.assertTrue(any('보습' in frame.value.to_string() for frame in first.dataframe))
        first.button(key='analyze_unmatched_candidate_pool').click().run()
        self.assertFalse(first.exception)
        first.button(key='clear_unmatched_candidate_pool').click().run()
        self.assertFalse(first.exception)
        self.assertTrue(any('보습' in frame.value.to_string() for frame in first.dataframe))
        self.repository.delete_unmatched_terms.assert_not_called()
        first.button(key='cloud_logout').click().run()
        self.assertFalse(first.exception)
        second = self.app(tab='미매칭 후보군').run()
        self.assertFalse(second.exception)
        self.repository.load_unmatched_terms.assert_called_with(0, 100, '')
        self.assertTrue(any('보습' in frame.value.to_string() for frame in second.dataframe))
        self.assertFalse(any(button.key == 'delete_unmatched_terms' for button in second.button))

    def test_failed_save_retries_same_event_and_blocks_loss_on_logout(self):
        self.repository.collect_unmatched_terms.side_effect = [StorageError('offline'), 1]
        app = self.app().run()
        app.text_area(key='analysis_input_text').set_value('필러 보습').run()
        app.button(key='btn_analyze').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.session_state['unmatched_pending_collections']), 1)
        original = self.repository.collect_unmatched_terms.call_args
        app.run()
        self.assertEqual(self.repository.collect_unmatched_terms.call_count, 1)
        app.button(key='cloud_logout').click().run()
        self.repository.logout.assert_not_called()
        # The next render shows the retry control after the guarded logout.
        app.run()
        app.button(key='retry_unmatched_collection').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(self.repository.collect_unmatched_terms.call_count, 2)
        self.assertEqual(self.repository.collect_unmatched_terms.call_args, original)
        self.assertFalse(app.session_state['unmatched_pending_collections'])

    def test_raw_ocr_counts_repetitions_at_60_percent_and_preview_does_not_recollect(self):
        buffer = io.BytesIO()
        Image.new('RGB', (200, 100), 'white').save(buffer, format='PNG')
        content = buffer.getvalue()
        rows = [
            {'text': '필러 보습', 'confidence': score, 'bbox': [10, 10, 180, 30]}
            for score in (0.99, 0.60)
        ] + [{'text': '제외어', 'confidence': 0.599, 'bbox': [10, 40, 100, 60]}]
        with patch.dict(sys.modules, {'paddleocr': SimpleNamespace(PaddleOCR=Mock(return_value=object()))}), \
                patch('ocr_keyword_import.extract_text_lines', return_value=rows):
            app = self.app(tab='이미지 OCR분석')
            app.session_state['ocr_keyword_uploaded_files'] = [
                SimpleNamespace(name='test.png', size=len(content), getvalue=lambda: content)]
            app.run()
            app.button(key='ocr_keyword_run').click().run()
            self.assertFalse(app.exception)
            self.repository.collect_unmatched_terms.assert_called_once()
            first_id, terms = self.repository.collect_unmatched_terms.call_args.args
            self.assertEqual(terms, [{'surface_key': '보습', 'surface': '보습', 'occurrences': 2}])
            app.button(key='ocr_keyword_preview_analysis').click().run()
            self.assertFalse(app.exception)
            self.repository.collect_unmatched_terms.assert_called_once()
            app.button(key='btn_analyze').click().run()
            self.assertFalse(app.exception)
            self.assertEqual(self.repository.collect_unmatched_terms.call_count, 2)
            self.assertNotEqual(self.repository.collect_unmatched_terms.call_args.args[0], first_id)

    def test_admin_deletion_requires_confirmation_and_uses_authenticated_token(self):
        self.seed_shared_row()
        def delete(terms, token):
            self.repository.load_unmatched_terms.return_value = {'rows': [], 'total': 0}
            return 1
        self.repository.delete_unmatched_terms.side_effect = delete
        app = self.app(role='admin', tab='미매칭 후보군').run()
        self.assertFalse(app.exception)
        self.assertTrue(app.button(key='delete_unmatched_terms').disabled)
        app.multiselect(key='unmatched_delete_terms_0').set_value(['보습']).run()
        app.checkbox(key='confirm_unmatched_delete').check().run()
        app.button(key='delete_unmatched_terms').click().run()
        self.assertFalse(app.exception)
        self.repository.delete_unmatched_terms.assert_called_once_with(['보습'], 'test-token')


if __name__ == '__main__':
    unittest.main()
