"""API additions used by the rebuilt React screens; no external DB needed."""
import unittest
from unittest.mock import Mock, patch

import pandas as pd
from fastapi.testclient import TestClient

import api
from matching_engine import DB_COLS

EXTRA = ['키워드등록인', '비고', '키워드 등록일자']
COLUMNS = list(DB_COLS) + EXTRA


def _row(code, term, category='화장품', registered='2026-01-02 03:04:05'):
    return dict(zip(COLUMNS, [code, term, category, '1등급(사용금지)', '-', '기준', '-', '3',
                              '2026-11-01 10:00:00', 'kim', 'note', registered]))


class CatalogColumnPreservationTests(unittest.TestCase):
    def setUp(self):
        self.repository = Mock()
        self.frame = pd.DataFrame([_row('B001', '필러'), _row('B002', '안티에이징')], columns=COLUMNS)
        self.frame.attrs['revision'] = 4
        self.repository.load_keywords.side_effect = lambda: self.frame.copy()
        self.repository.save_keywords.return_value = 5
        self.repository.user.return_value = {'id': 'u1', 'email': 'a@example.test',
                                             'app_metadata': {'role': 'admin'}}
        api.app.dependency_overrides[api.get_repository] = lambda: self.repository
        api.app.dependency_overrides[api.current_actor] = lambda: 'u1'
        self.addCleanup(api.app.dependency_overrides.clear)
        self.client = TestClient(api.app)
        self.headers = {'Authorization': 'Bearer token'}

    def saved_frame(self):
        return self.repository.save_keywords.call_args.args[0]

    def test_keywords_lists_stored_columns_in_order(self):
        response = self.client.get('/api/v1/keywords')
        self.assertEqual(response.json()['columns'], COLUMNS)

    def test_admin_save_keeps_extra_columns_and_counts(self):
        rows = [{**_row('B001', '필러 수정'), '키워드 조회 수(누적카운트)': '999'},
                _row('B002', '안티에이징'), _row('B003', '새 키워드', registered='2026-11-07 12:00:00')]
        response = self.client.put('/api/v1/admin/keywords', headers=self.headers,
                                   json={'revision': 4, 'rows': rows})
        self.assertEqual(response.status_code, 200, response.text)
        frame = self.saved_frame()
        self.assertEqual(list(frame.columns), COLUMNS)
        first = frame.set_index('kwd_no').loc['B001']
        self.assertEqual(first['키워드명'], '필러 수정')
        self.assertEqual(first['키워드 조회 수(누적카운트)'], '3')  # server keeps stored counts
        self.assertEqual(first['비고'], 'note')
        self.assertEqual(frame.set_index('kwd_no').loc['B003']['키워드 등록일자'], '2026-11-07 12:00:00')

    def test_delete_and_ocr_save_keep_extra_columns(self):
        self.client.post('/api/v1/admin/keywords/delete', headers=self.headers,
                         json={'revision': 4, 'kwd_nos': ['B002']})
        self.assertEqual(list(self.saved_frame().columns), COLUMNS)
        self.assertEqual(self.saved_frame().iloc[0]['키워드 등록일자'], '2026-01-02 03:04:05')
        response = self.client.post('/api/v1/ocr/keywords', headers=self.headers, json={
            'revision': 4, 'candidates': [{'term': '주름', 'category': '화장품', 'risk': '1등급(사용금지)',
                                           'detail': '-', 'evidence': '-'}]})
        self.assertEqual(response.status_code, 200, response.text)
        frame = self.saved_frame()
        self.assertEqual(list(frame.columns), COLUMNS)
        self.assertEqual(frame.set_index('kwd_no').loc['B001']['비고'], 'note')

    def test_register_unmatched_rows_adds_skips_duplicates_and_cleans_up(self):
        self.repository.delete_unmatched_registration_requests.return_value = 1
        response = self.client.post('/api/v1/admin/unmatched-terms/register', headers=self.headers, json={'rows': [
            {'term': '필러', 'category': '화장품', 'risk': 'r', 'criteria': 'c', 'evidence_type': 'e',
             'source_terms': '필러는 | 필러를'},
            {'term': '주름개선', 'category': '화장품', 'risk': 'r', 'criteria': 'c', 'evidence_type': 'e',
             'term_norm': '주름개선', 'request_id': '00000000-0000-0000-0000-000000000001', 'alternative': ''},
        ]})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body['added'], ['B003'])
        self.assertEqual(body['cleared_requests'], 1)
        frame = self.saved_frame()
        self.assertEqual(list(frame.columns), COLUMNS)
        added = frame.set_index('kwd_no').loc['B003']
        self.assertEqual(added['대체키워드'], '-')
        self.assertEqual(added['키워드 등록일자'], '')
        keys = self.repository.delete_unmatched_terms.call_args.args[0]
        self.assertEqual(keys, ['주름개선', '필러는', '필러를'])

    def test_register_requires_classification(self):
        response = self.client.post('/api/v1/admin/unmatched-terms/register', headers=self.headers, json={'rows': [
            {'term': 'x', 'category': '화장품', 'risk': '', 'criteria': 'c', 'evidence_type': 'e'}]})
        self.assertEqual(response.status_code, 422)
        self.repository.save_keywords.assert_not_called()


class KeywordRequestAdditionsTests(unittest.TestCase):
    def setUp(self):
        self.repository = Mock()
        frame = pd.DataFrame([_row('B001', '필러')], columns=COLUMNS)
        frame.attrs['revision'] = 1
        self.repository.load_keywords.return_value = frame
        self.repository.user.return_value = {'id': 'u1', 'email': 'm@example.test',
                                             'app_metadata': {'role': 'member'}}
        self.repository.submit_keyword_request.return_value = {'id': 'r1', 'kwd_no': 'B001'}
        api.app.dependency_overrides[api.get_repository] = lambda: self.repository
        api.app.dependency_overrides[api.current_actor] = lambda: 'u1'
        self.addCleanup(api.app.dependency_overrides.clear)
        self.client = TestClient(api.app)
        self.headers = {'Authorization': 'Bearer token'}

    def test_request_detail_is_optional_and_notification_reported(self):
        self.repository.load_request_email_notifications.return_value = True
        with patch('request_notifications.send_keyword_request_email') as send:
            response = self.client.post('/api/v1/keyword-requests', headers=self.headers, json={
                'kwd_no': 'b001', 'request_type': 'risk_grade_adjustment'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['notification'], 'sent')
        send.assert_called_once()
        payload = self.repository.submit_keyword_request.call_args.args[0]
        self.assertEqual(payload['request_detail'], '')
        self.assertEqual(payload['kwd_no'], 'B001')

    def test_notification_failure_does_not_fail_request(self):
        from request_notifications import NotificationDeliveryError
        self.repository.load_request_email_notifications.return_value = True
        with patch('request_notifications.send_keyword_request_email', side_effect=NotificationDeliveryError('x')):
            response = self.client.post('/api/v1/keyword-requests', headers=self.headers, json={
                'kwd_no': 'B001', 'request_type': 'review_criteria_change', 'request_detail': '이유'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['notification'], 'failed')

    def test_new_keyword_requests_deduplicate(self):
        self.repository.submit_new_keyword_registration_requests.return_value = 2
        response = self.client.post('/api/v1/keyword-requests/new-keywords', headers=self.headers,
                                    json={'terms': ['키워드A', ' 키워드a ', '', '키워드B']})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['submitted'], 2)
        terms = self.repository.submit_new_keyword_registration_requests.call_args.args[0]
        self.assertEqual(terms, ['키워드A', '키워드B'])

    def test_matching_rules_readable_by_members(self):
        self.repository.load_setting.side_effect = lambda name, default: (
            {'B001': {'term': '필러', 'expressions': ['필러']}} if name == 'approved_partial_expressions_v272'
            else default)
        response = self.client.get('/api/v2/matching-rules', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertIn('/', response.json()['ignored_symbols'])
        self.assertIn('B001', response.json()['approved_partials'])


if __name__ == '__main__':
    unittest.main()
