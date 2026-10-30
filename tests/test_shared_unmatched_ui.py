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
        self.repository.load_unmatched_registration_requests.return_value = []
        for patcher in [patch.dict(os.environ, {
                'STORAGE_BACKEND': 'supabase', 'SUPABASE_URL': 'https://example.supabase.co',
                'SUPABASE_SECRET_KEY': 'test-only'}),
                patch('repository.SupabaseRepository', return_value=self.repository),
                patch('repository.requests.request', side_effect=AssertionError('Unexpected network'))]:
            patcher.start()
            self.addCleanup(patcher.stop)

    def app(self, role='member', tab='스크립트 분석', version=297):
        self.repository.user.return_value = {
            'id': str(uuid4()), 'email': 'test@example.test', 'app_metadata': {'role': role}}
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / f'keyword_app2_fixed{version}.py'),
                                default_timeout=30)
        app.session_state['auth_session'] = {'access_token': 'test-token', 'expires_at': 9999999999}
        app.session_state['main_app_tabs'] = tab
        app.session_state['match_mode'] = MATCH_MODES['exact']
        return app

    def test_candidate_analysis_requires_an_explicit_selection(self):
        self.seed_shared_row()
        app = self.app(tab='미매칭 후보군', version=308).run()
        self.assertFalse(app.exception)
        self.assertTrue(app.dataframe)
        app.button(key='analyze_unmatched_candidate_pool').click().run()
        self.assertFalse(app.exception)
        self.assertTrue(any('표에서 선택' in item.value for item in app.warning))
        self.assertEqual(self.repository.load_unmatched_terms.call_count, 2)
        self.repository.load_unmatched_terms.assert_called_with(0, 100, '', 'occurrences')

    def test_registration_sort_is_sent_to_the_paged_query(self):
        self.seed_shared_row()
        app = self.app(tab='미매칭 후보군', version=308).run()
        self.assertFalse(app.exception)
        self.repository.load_unmatched_terms.assert_called_with(0, 100, '', 'occurrences')
        app.selectbox(key='unmatched_sort_order').set_value('등록순').run()
        self.assertFalse(app.exception)
        self.repository.load_unmatched_terms.assert_called_with(0, 100, '', 'registered')

    def test_admin_sees_requests_submitted_by_other_accounts(self):
        request_id = str(uuid4())
        self.repository.load_unmatched_registration_requests.return_value = [{
            'id': request_id, 'term': '\ubcf4\uc2b5', 'source_terms': '\ubcf4\uc2b5\ub825',
            'occurrences': 3, 'category': '', 'risk': '', 'criteria': '',
            'evidence_type': '', 'alternative': '-', 'created_at': '2026-10-28T00:00:00Z',
        }]
        app = self.app(role='admin', tab='\ubbf8\ub9e4\uce6d \ud6c4\ubcf4\uad70', version=306).run()
        self.assertFalse(app.exception)
        self.repository.load_unmatched_registration_requests.assert_called_once_with('test-token')
        self.assertTrue(any('1\uac74' in item.value for item in app.caption))
        self.assertTrue(any(button.key == 'approve_unmatched_recommendations' for button in app.button))

    def test_member_can_open_registration_request_action(self):
        app = self.app(tab='미매칭 후보군', version=306)
        app.session_state['unmatched_candidate_recommendations'] = [
            {'term': '보습', 'source_terms': '보습', 'occurrences': 3}
        ]
        app.run()
        self.assertFalse(app.exception)
        self.assertIsNotNone(app.button(key='request_unmatched_keyword_registration'))
        self.assertFalse(any(button.key == 'approve_unmatched_recommendations' for button in app.button))

    def test_refresh_restores_session_from_browser_refresh_token(self):
        self.repository.refresh.return_value = {
            'access_token': 'restored-access-token', 'refresh_token': 'rotated-refresh-token',
            'expires_at': 9999999999,
        }
        app = self.app(version=307)
        del app.session_state['auth_session']
        app.session_state['cloud_auth_session_storage'] = {
            'refresh_token': 'stored-refresh-token', 'checked': True,
        }
        app.run()
        self.assertFalse(app.exception)
        self.repository.refresh.assert_called_once_with('stored-refresh-token')
        self.repository.user.assert_called_with('restored-access-token')

    def test_both_roles_can_exclude_recommendations_and_admin_can_reject_requests(self):
        for role in ('member', 'admin'):
            app = self.app(role=role, tab='미매칭 후보군', version=306)
            app.session_state['unmatched_candidate_recommendations'] = [
                {'term': '보습', 'source_terms': '보습', 'occurrences': 2}
            ]
            app.run()
            self.assertFalse(app.exception)
            self.assertTrue(any(button.key == 'exclude_unmatched_recommendations'
                                for button in app.button))
            self.assertEqual(any(button.key == 'reject_unmatched_registration_requests'
                                 for button in app.button), role == 'admin')

    def test_latest_recommendation_table_header_selects_and_clears_every_row(self):
        app = self.app(tab='미매칭 후보군', version=321)
        app.session_state['unmatched_candidate_recommendations'] = [
            {'term': '보습', 'source_terms': '보습', 'occurrences': 2},
            {'term': '진정', 'source_terms': '진정', 'occurrences': 1},
        ]
        app.run()
        self.assertFalse(app.exception)
        select_all = next(item for item in app.checkbox if item.label == '선택')
        select_all.check().run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.session_state['unmatched_recommendation_selected_ids']), 2)
        select_all = next(item for item in app.checkbox if item.label == '선택')
        select_all.uncheck().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['unmatched_recommendation_selected_ids'], [])

    def test_keyword_editor_has_select_all_header_checkbox(self):
        app = self.app(role='admin', tab='키워드 관리', version=321).run()
        self.assertFalse(app.exception)
        app.checkbox(key='keyword_editor_select_all_dropdown').check().run()
        self.assertFalse(app.exception)
        self.assertTrue(all(row['선택'] for row in app.session_state['keyword_editor_draft_dropdown']))

    def test_sidebar_new_keyword_request_queues_terms_without_keyword_inquiry(self):
        self.repository.submit_new_keyword_registration_requests.return_value = 2
        app = self.app(version=306).run()
        app.session_state['keyword_request_type'] = 'new_keyword_registration'
        app.run()
        app.text_area(key='keyword_request_detail').set_value('알파, 베타, 알파')
        next(button for button in app.button if button.label == '입력').click().run()
        self.assertFalse(app.exception)
        self.repository.submit_new_keyword_registration_requests.assert_called_once_with(
            ['알파', '베타'], 'test-token')
        self.repository.submit_keyword_request.assert_not_called()

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
            app = self.app(tab='이미지 OCR분석', version=315)
            app.session_state['analysis_input_text'] = '필러'
            app.session_state['ocr_keyword_uploaded_files'] = [
                SimpleNamespace(name='test.png', size=len(content), getvalue=lambda: content)]
            app.run()
            app.button(key='ocr_keyword_run').click().run()
            self.assertFalse(app.exception)
            self.repository.collect_unmatched_terms.assert_not_called()
            app.button(key='ocr_keyword_preview_analysis').click().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.session_state['analysis_input_text'], '필러\n\n필러 보습\n필러 보습')
            self.repository.collect_unmatched_terms.assert_called_once()
            first_id, terms = self.repository.collect_unmatched_terms.call_args.args
            self.assertEqual(terms, [{'surface_key': '보습', 'surface': '보습', 'occurrences': 2}])
            app.button(key='btn_analyze').click().run()
            self.assertFalse(app.exception)
            self.assertEqual(self.repository.collect_unmatched_terms.call_count, 2)
            self.assertNotEqual(self.repository.collect_unmatched_terms.call_args.args[0], first_id)

    def test_admin_row_deletion_requires_confirmation(self):
        self.seed_shared_row()
        app = self.app(role='admin', tab='미매칭 후보군', version=316).run()
        self.assertFalse(app.exception)
        self.assertTrue(app.button(key='delete_selected_unmatched_review_rows').disabled)
        self.assertTrue(app.checkbox(key='confirm_selected_unmatched_delete'))
        self.assertNotIn('delete_unmatched_terms', [button.key for button in app.button])
        self.assertFalse(any(key.startswith('unmatched_delete_terms_') for key in
                             [multiselect.key for multiselect in app.multiselect]))
        self.repository.delete_unmatched_terms.assert_not_called()


if __name__ == '__main__':
    unittest.main()
