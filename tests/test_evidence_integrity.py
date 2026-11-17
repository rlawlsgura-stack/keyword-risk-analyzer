"""Offline regressions for the evidence actually read, returned and saved."""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from regulation_assistant import _llm_research_recommendation
from regulation_corpus import save_turn


class EvidenceIntegrityTests(unittest.TestCase):
    def recommend(self, answer, sources, annotations=(), status='completed'):
        response = SimpleNamespace(raise_for_status=lambda: None, json=lambda: {
            'status': status, 'output': [{'type': 'message', 'content': [
                {'type': 'output_text', 'text': answer, 'annotations': list(annotations)}]}]})
        with patch.dict(os.environ, {'REGULATION_LLM_ENABLED': 'true',
                'OPENAI_API_KEY': 'offline-test', 'REGULATION_LLM_MODEL': 'test-model'}), \
                patch('regulation_assistant.requests.post', return_value=response) as post:
            result = _llm_research_recommendation('질문', sources, '', '2026-11-17')
        return result, post.call_args.kwargs['json']

    def test_unseen_source_is_not_accepted_as_citation(self):
        sources = [{'id': f'INT{i}', 'text': f'근거 {i}'} for i in range(1, 10)]
        result, _ = self.recommend('전달되지 않은 근거입니다. [INT9]', sources)
        self.assertEqual(result['status'], 'insufficient')
        result, _ = self.recommend('전달된 근거입니다. [INT1]', sources)
        self.assertEqual(result['status'], 'recommendation')

    def test_every_paragraph_and_complete_output_are_required(self):
        sources = [{'id': 'INT1', 'text': '검토 근거'}]
        for answer, status in [('근거입니다. [INT1]\n\n근거 없는 결론입니다.', 'completed'),
                               ('미완성 결론 [INT1]', 'incomplete')]:
            result, _ = self.recommend(answer, sources, status=status)
            self.assertEqual(result['status'], 'insufficient')
        answer = '조건과 예외를 포함한 검토입니다. ' * 500 + '[INT1]'
        result, _ = self.recommend(answer, sources)
        self.assertTrue(result['answer'].endswith(answer))

    def test_official_web_annotations_support_current_and_nested_shapes(self):
        for annotation in (
            {'type': 'url_citation', 'url': 'https://www.law.go.kr/test',
             'title': '공식 근거', 'end_index': 5},
            {'url_citation': {'url': 'https://www.law.go.kr/test',
                              'title': '공식 근거', 'end_index': 5}},
        ):
            result, _ = self.recommend('공식 근거', [], [annotation])
            self.assertEqual(result['status'], 'recommendation')
            self.assertEqual(result['sources'][0]['id'], 'WEB1')
        result, _ = self.recommend('공식 근거', [], [
            {'type': 'url_citation', 'url': 'https://law.go.kr.example.org', 'end_index': 5}])
        self.assertEqual(result['status'], 'insufficient')

    def test_late_cited_source_and_entire_evidence_survive_storage(self):
        sources = [{'id': f'INT{i}', 'text': '원문' * 2000,
                    'version': 'v1', 'content_sha256': 'a' * 64} for i in range(1, 15)]
        captured = {}
        repository = SimpleNamespace(rpc=lambda name, **params: captured.update(params))
        save_turn(repository, None, 'owner', 'all', '질문', '뒤쪽 근거 [INT14]', sources)
        self.assertEqual(len(captured['p_evidence']), len(sources))
        self.assertEqual(captured['p_evidence'][-1]['text'], sources[-1]['text'])
        self.assertEqual(captured['p_evidence'][-1]['content_sha256'], 'a' * 64)


if __name__ == '__main__':
    unittest.main()
