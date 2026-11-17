"""Offline regressions for the evidence actually read, returned and saved."""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from regulation_assistant import DEFAULT_GPT_MODEL, _answer_gpt_mode, _llm_explanation, _llm_research_recommendation, _review_sources
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
        result, _ = self.recommend('전달된 「근거 1」입니다. [INT1]', sources)
        self.assertEqual(result['status'], 'recommendation')

    def test_every_paragraph_and_complete_output_are_required(self):
        sources = [{'id': 'INT1', 'text': '검토 근거'}]
        for answer, status in [('근거입니다. [INT1]\n\n근거 없는 결론입니다.', 'completed'),
                               ('미완성 결론 [INT1]', 'incomplete')]:
            result, _ = self.recommend(answer, sources, status=status)
            self.assertEqual(result['status'], 'insufficient')
        answer = '조건과 예외를 포함한 검토입니다. ' * 500 + '「검토 근거」 [INT1]'
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

    def test_quote_must_exist_in_each_cited_source(self):
        sources = [{'id': 'INT1', 'text': '조건 충족 시 허용. 다만 예외 확인 필요.'},
                   {'id': 'INT2', 'text': '다른 상품의 규정입니다.'}]
        for answer in ('허용됩니다. [INT1]', '「없는 원문」 [INT1]',
                       '「조건 충족 시 허용」 [INT1] [INT2]'):
            result, _ = self.recommend(answer, sources)
            self.assertEqual(result['status'], 'insufficient')
        result, _ = self.recommend('「조건 충족 시 허용」이며 「다만 예외 확인 필요」입니다. [INT1]', sources)
        self.assertEqual(result['status'], 'recommendation')

    def test_source_types_get_a_turn_and_whole_qualifications_are_sent(self):
        long_text = '본문. ' * 800 + '다만 승인된 경우는 예외이다.'
        sources = [{'id': f'INT{i}', 'text': long_text} for i in range(1, 10)]
        sources += [{'id': 'LAW1', 'text': '공식 조문'}, {'id': 'DB1', 'text': '등록 기준'}]
        selected = _review_sources(sources)
        self.assertTrue({'INT1', 'LAW1', 'DB1'} <= {s['id'] for s in selected})
        result, payload = self.recommend('「다만 승인된 경우는 예외이다.」 [INT1]', sources)
        import json
        supplied = json.loads(payload['input'][1]['content'])['internal_and_official_evidence']
        self.assertEqual(next(s['text'] for s in supplied if s['id'] == 'INT1'), long_text)
        self.assertEqual(result['status'], 'recommendation')
        self.assertEqual(result['reviewed_source_ids'], [s['id'] for s in selected])

    def test_legacy_answer_renders_only_quote_checked_claims(self):
        import json
        response = SimpleNamespace(raise_for_status=lambda: None, json=lambda: {'choices': [
            {'message': {'content': json.dumps({'status': 'supported', 'administrator_review': False,
                'answer': '자유 생성한 검증되지 않은 결론', 'claims': [
                    {'text': '조건과 예외 확인이 필요합니다.', 'quote': '예외 조건', 'source_id': 'INT1'}]})}}]})
        with patch.dict(os.environ, {'REGULATION_LLM_ENABLED': 'true',
                'OPENAI_API_KEY': 'offline-test', 'REGULATION_LLM_MODEL': 'test-model'}), \
                patch('regulation_assistant.requests.post', return_value=response):
            result = _llm_explanation('질문', [{'id': 'INT1', 'text': '예외 조건'}])
        self.assertEqual(result['status'], 'supported')
        self.assertIn('「예외 조건」 [INT1]', result['answer'])
        self.assertNotIn('검증되지 않은', result['answer'])

    def test_gpt_summary_does_not_present_incomplete_output_as_an_answer(self):
        response = SimpleNamespace(raise_for_status=lambda: None, json=lambda: {
            'status': 'incomplete', 'usage': {'output_tokens': 2000},
            'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': '조건이 빠진 결론'}]}]})
        with patch.dict(os.environ, {'REGULATION_LLM_ENABLED': 'true', 'OPENAI_API_KEY': 'offline-test'}), \
                patch('regulation_assistant.requests.post', return_value=response):
            result = _answer_gpt_mode({'query': '연결 자료를 요약해 줘', 'model': DEFAULT_GPT_MODEL})
        self.assertEqual(result['status'], 'insufficient')
        self.assertNotIn('조건이 빠진 결론', result['answer'])
        self.assertEqual(result['openai_usage']['output_tokens'], 2000)


if __name__ == '__main__':
    unittest.main()
