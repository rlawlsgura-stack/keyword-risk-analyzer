"""Exercise role isolation and saved evidence through the public API contract."""
import os
import hashlib
import unittest
from datetime import datetime
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

import api
from repository import StorageError
from regulation_assistant import _llm_explanation


class FakeRepository:
    def __init__(self, role='member'):
        self.role = role
        self.calls = []
        self.delete_result = True
        self.delete_prefer = None
        self.documents = []
        self.search_results = None
        self.chunk_results = []

    def user(self, token):
        return {'id': '00000000-0000-0000-0000-000000000001',
                'app_metadata': {'role': self.role}}

    def load_openai_usage(self, month_start):
        return {}

    def rpc(self, name, **params):
        self.calls.append((name, params))
        if name == 'search_regulation_chunks':
            if self.search_results is not None:
                return self.search_results
            return [{'chunk_id': 'chunk-1', 'document_id': 'document-1',
                     'title': '심의 지침', 'version': '2026-11',
                     'ordinal': 1, 'content': '화장품 광고 문구 심의 기준입니다.',
                     'content_sha256': 'a' * 64}]
        if name == 'save_regulation_turn':
            return '00000000-0000-0000-0000-000000000002'
        if name == 'create_regulation_document':
            return '00000000-0000-0000-0000-000000000003'
        if name == 'approve_regulation_document':
            return params['p_id']
        if name == 'delete_regulation_draft':
            return True
        raise AssertionError(name)

    def request(self, method, path, *args, **kwargs):
        self.calls.append((method, path))
        if method == 'DELETE':
            self.delete_prefer = kwargs.get('prefer')
            return [{'id': 'deleted'}] if self.delete_result else []
        if method == 'GET' and 'kra_regulation_documents' in path:
            query = parse_qs(urlsplit(path).query)
            for column in ('source_key', 'content_sha256', 'id'):
                if column in query:
                    value = query[column][0].removeprefix('eq.')
                    return [row for row in self.documents if row.get(column) == value]
            return self.documents
        if method == 'GET' and 'kra_regulation_chunks' in path:
            return self.chunk_results
        return []


class RegulationCorpusApiTests(unittest.TestCase):
    def tearDown(self):
        api.app.dependency_overrides.clear()

    def client(self, repository, actor='00000000-0000-0000-0000-000000000001'):
        api.app.dependency_overrides[api.get_repository] = lambda: repository
        api.app.dependency_overrides[api.current_actor] = lambda: actor
        return TestClient(api.app)

    def test_member_cannot_open_document_management(self):
        client = self.client(FakeRepository('member'))
        response = client.get('/api/v1/admin/regulation/documents',
                              headers={'Authorization': 'Bearer test'})
        self.assertEqual(response.status_code, 403)
        match = client.post('/api/v1/admin/regulation/documents/matches',
            files={'file': ('guide.txt', b'Enough text for a document match.')},
            headers={'Authorization': 'Bearer test'})
        self.assertEqual(match.status_code, 403)

    def test_internal_answer_saves_versioned_evidence(self):
        repository = FakeRepository()
        client = self.client(repository)
        with patch.dict(os.environ, {'REGULATION_EMBEDDINGS_ENABLED': 'false'}):
            response = client.post('/api/v1/regulation/questions',
                json={'direction': 'keyword_to_law', 'scope': 'internal',
                      'query': '화장품 광고 기준', 'as_of': '2026-11-10'},
                headers={'Authorization': 'Bearer test'})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body['sources'][0]['version'], '2026-11')
        self.assertEqual(body['thread_id'], '00000000-0000-0000-0000-000000000002')
        saved = next(params for name, params in repository.calls if name == 'save_regulation_turn')
        self.assertEqual(saved['p_evidence'][0]['document_id'], 'document-1')
        self.assertEqual(saved['p_evidence'][0]['chunk_id'], 'chunk-1')
        self.assertEqual(saved['p_evidence'][0]['content_sha256'], 'a' * 64)

    def test_integration_token_cannot_read_conversations(self):
        client = self.client(FakeRepository(), actor='integration')
        self.assertEqual(client.get('/api/v1/regulation/threads',
            headers={'Authorization': 'Bearer test'}).status_code, 403)

    def test_member_deletes_only_their_own_saved_conversation(self):
        repository = FakeRepository()
        client = self.client(repository)
        thread_id = '00000000-0000-0000-0000-000000000002'
        response = client.delete(f'/api/v1/regulation/threads/{thread_id}',
                                 headers={'Authorization': 'Bearer test'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()['deleted'])
        path = next(path for method, path in repository.calls if method == 'DELETE')
        self.assertIn(f'id=eq.{thread_id}', path)
        self.assertIn('owner_id=eq.00000000-0000-0000-0000-000000000001', path)
        self.assertEqual(repository.delete_prefer, 'return=representation')

        repository.delete_result = False
        missing = client.delete(f'/api/v1/regulation/threads/{thread_id}',
                                headers={'Authorization': 'Bearer test'})
        self.assertEqual(missing.status_code, 404)

    def test_integration_token_cannot_delete_saved_conversation(self):
        client = self.client(FakeRepository(), actor='integration')
        response = client.delete('/api/v1/regulation/threads/00000000-0000-0000-0000-000000000002',
                                 headers={'Authorization': 'Bearer test'})
        self.assertEqual(response.status_code, 403)

    def test_admin_uploads_draft_before_approval(self):
        repository = FakeRepository('admin')
        client = self.client(repository)
        with patch.dict(os.environ, {'REGULATION_EMBEDDINGS_ENABLED': 'false'}):
            response = client.post('/api/v1/admin/regulation/documents',
                data={'category': '화장품', 'effective_from': '', 'effective_to': '',
                      'replace_document_id': '', 'new_document': 'true'},
                files={'file': ('guidance.txt', '화장품 광고 심의 지침의 테스트 본문입니다.'.encode('utf-8'))},
                headers={'Authorization': 'Bearer test'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['status'], 'draft')
        created = next(params for name, params in repository.calls if name == 'create_regulation_document')
        self.assertRegex(created['p_source_key'], r'^doc-[0-9a-f]{24}$')
        self.assertEqual(created['p_title'], 'guidance')
        self.assertEqual(created['p_category'], '화장품')
        self.assertEqual(created['p_effective_from'], datetime.now(ZoneInfo('Asia/Seoul')).date().isoformat())
        self.assertIsNone(created['p_effective_to'])
        self.assertEqual(created['p_chunks'][0]['ordinal'], 1)
        self.assertIsNone(created['p_chunks'][0]['embedding'])
        document_id = response.json()['id']
        approved = client.post(f'/api/v1/admin/regulation/documents/{document_id}/approve',
                               headers={'Authorization': 'Bearer test'})
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(approved.json()['status'], 'approved')

    def test_draft_upload_does_not_call_openai_when_embeddings_are_enabled(self):
        repository = FakeRepository('admin')
        with patch.dict(os.environ, {'REGULATION_EMBEDDINGS_ENABLED': 'true',
                                      'OPENAI_API_KEY': ''}), \
             patch('regulation_corpus._embed', side_effect=AssertionError('unexpected embedding')) as embed:
            response = self.client(repository).post('/api/v1/admin/regulation/documents',
                data={'category': '화장품', 'new_document': 'true'},
                files={'file': ('guide.txt', b'Enough text for a regulation document draft.')},
                headers={'Authorization': 'Bearer test'})
        self.assertEqual(response.status_code, 200, response.text)
        embed.assert_not_called()

    def test_storage_failure_returns_actionable_upload_error(self):
        repository = FakeRepository('admin')
        with patch.object(repository, 'rpc', side_effect=StorageError('sensitive storage details')), \
             patch('api.logger.warning'):
            response = self.client(repository).post('/api/v1/admin/regulation/documents',
                data={'category': '화장품', 'new_document': 'true'},
                files={'file': ('guide.txt', b'Enough text for a regulation document draft.')},
                headers={'Authorization': 'Bearer test'})
        self.assertEqual(response.status_code, 503)
        self.assertIn('문서 저장소', response.json()['detail'])
        self.assertNotIn('sensitive', response.text)

    def test_explicit_replacement_reuses_identity_after_filename_change(self):
        repository = FakeRepository('admin')
        repository.documents = [{
            'id': '00000000-0000-0000-0000-000000000004', 'source_key': 'old-manual-key',
            'version': '2026-10', 'category': '화장품', 'status': 'approved',
            'content_sha256': '0' * 64, 'effective_from': '2026-11-14',
            'effective_to': None, 'original_name': 'guidance.txt',
        }]
        client = self.client(repository)
        with patch.dict(os.environ, {'REGULATION_EMBEDDINGS_ENABLED': 'false'}):
            response = client.post('/api/v1/admin/regulation/documents',
                data={'category': '화장품', 'replace_document_id': repository.documents[0]['id']},
                files={'file': ('renamed-guidance.txt', '새로운 화장품 광고 심의 지침입니다.'.encode('utf-8'))},
                headers={'Authorization': 'Bearer test'})
        self.assertEqual(response.status_code, 200, response.text)
        created = next(params for name, params in repository.calls if name == 'create_regulation_document')
        self.assertEqual(created['p_source_key'], 'old-manual-key')
        self.assertIsNone(created['p_effective_to'])

    def test_identical_approved_file_is_not_registered_again(self):
        repository = FakeRepository('admin')
        payload = '화장품 광고 심의 지침의 테스트 본문입니다.'.encode('utf-8')
        repository.documents = [{
            'id': '00000000-0000-0000-0000-000000000004', 'source_key': 'old-manual-key',
            'version': '2026-10', 'category': '화장품', 'status': 'approved',
            'content_sha256': hashlib.sha256(payload).hexdigest(),
            'effective_from': '2026-10-10',
            'effective_to': None, 'original_name': 'guidance.txt',
        }]
        client = self.client(repository)
        response = client.post('/api/v1/admin/regulation/documents',
            data={'category': '화장품'}, files={'file': ('renamed-guidance.txt', payload)},
            headers={'Authorization': 'Bearer test'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['id'], repository.documents[0]['id'])
        self.assertTrue(response.json()['unchanged'])
        self.assertFalse(any(name == 'create_regulation_document' for name, _ in repository.calls))

    def test_identical_content_in_multiple_documents_requires_choice(self):
        repository = FakeRepository('admin')
        payload = b'New guidance text with enough content.'
        content_hash = hashlib.sha256(payload).hexdigest()
        repository.documents = [
            {'id': 'doc-a', 'source_key': 'manual-a', 'content_sha256': content_hash},
            {'id': 'doc-b', 'source_key': 'manual-b', 'content_sha256': content_hash},
        ]
        response = self.client(repository).post('/api/v1/admin/regulation/documents',
            data={'category': '화장품'}, files={'file': ('guide.txt', payload)},
            headers={'Authorization': 'Bearer test'})
        self.assertEqual(response.status_code, 409)
        self.assertFalse(any(name == 'create_regulation_document' for name, _ in repository.calls))

    def test_admin_can_keep_identical_file_as_separate_document(self):
        repository = FakeRepository('admin')
        payload = b'New guidance text with enough content.'
        content_hash = hashlib.sha256(payload).hexdigest()
        repository.documents = [{
            'id': 'doc-a', 'source_key': 'manual-a', 'content_sha256': content_hash,
            'category': '화장품', 'status': 'approved', 'effective_from': '2026-10-10',
            'effective_to': None,
        }]
        with patch.dict(os.environ, {'REGULATION_EMBEDDINGS_ENABLED': 'false'}):
            response = self.client(repository).post('/api/v1/admin/regulation/documents',
                data={'category': '공산품', 'new_document': 'true'},
                files={'file': ('other.txt', payload)}, headers={'Authorization': 'Bearer test'})
        self.assertEqual(response.status_code, 200, response.text)
        created = next(params for name, params in repository.calls if name == 'create_regulation_document')
        self.assertNotEqual(created['p_source_key'], 'manual-a')

    def test_match_endpoint_suggests_similar_document_for_review(self):
        repository = FakeRepository('admin')
        content = '화장품 광고 심의 지침의 테스트 본문입니다. 표현과 증빙자료를 검토합니다.'
        previous_content = content.replace('테스트', '운영')
        repository.documents = [{
            'id': '00000000-0000-0000-0000-000000000004', 'source_key': 'existing-doc',
            'title': '기존 지침', 'category': '화장품', 'status': 'approved',
            'content_sha256': '0' * 64, 'effective_from': '2026-10-10',
            'effective_to': None, 'original_name': 'old.txt',
        }]
        repository.search_results = [{'document_id': repository.documents[0]['id'], 'content': previous_content}]
        repository.chunk_results = [{'id': 'chunk-1', 'ordinal': 1, 'content': previous_content, 'embedding_model': None}]
        response = self.client(repository).post('/api/v1/admin/regulation/documents/matches',
            files={'file': ('new.txt', content.encode('utf-8'))}, headers={'Authorization': 'Bearer test'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['exact'], [])
        self.assertEqual(response.json()['candidates'][0]['document']['id'], repository.documents[0]['id'])
        self.assertGreater(response.json()['candidates'][0]['similarity'], 0.5)

    def test_match_endpoint_finds_identical_file_after_rename(self):
        repository = FakeRepository('admin')
        payload = b'Enough text for the renamed regulation document.'
        repository.documents = [{
            'id': '00000000-0000-0000-0000-000000000004', 'source_key': 'existing-doc',
            'title': '기존 지침', 'category': '화장품', 'status': 'approved',
            'content_sha256': hashlib.sha256(payload).hexdigest(),
            'effective_from': '2026-10-10', 'effective_to': None, 'original_name': 'old.txt',
        }]
        response = self.client(repository).post('/api/v1/admin/regulation/documents/matches',
            files={'file': ('renamed.txt', payload)}, headers={'Authorization': 'Bearer test'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['exact'][0]['id'], repository.documents[0]['id'])
        self.assertEqual(response.json()['candidates'], [])

    def test_match_failure_blocks_unreviewed_registration(self):
        repository = FakeRepository('admin')
        with patch('api.similar_document_candidates', side_effect=RuntimeError('storage unavailable')), \
             patch('api.logger.warning'):
            response = self.client(repository).post('/api/v1/admin/regulation/documents/matches',
                files={'file': ('new.txt', b'Enough text for the regulation document.')},
                headers={'Authorization': 'Bearer test'})
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('storage unavailable', response.text)

    def test_llm_answer_requires_a_verbatim_citation(self):
        class Response:
            def raise_for_status(self):
                return None

            def json(self):
                return {'choices': [{'message': {'content':
                    '{"status":"supported","answer":"검토가 필요합니다.","administrator_review":false,'
                    '"claims":[{"text":"검토가 필요합니다","source_id":"INT1","quote":"광고 문구"}]}'}}]}

        with patch.dict(os.environ, {'REGULATION_LLM_ENABLED': 'true',
                                      'OPENAI_API_KEY': 'test-key', 'REGULATION_LLM_MODEL': 'test-model'}), \
             patch('regulation_assistant.requests.post', return_value=Response()):
            result = _llm_explanation('질문', [{'id': 'INT1', 'label': '지침',
                                           'text': '광고 문구', 'url': ''}])
        self.assertEqual(result['status'], 'supported')
        self.assertIn('[INT1]', result['answer'])


if __name__ == '__main__':
    unittest.main()
