import io
import os
import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
from zipfile import ZipFile

import requests

from regulation_corpus import _embed, _neighbor_context, extract_text, search_documents, search_tokens, split_chunks


class RegulationStructureTests(unittest.TestCase):
    def test_paragraph_and_separate_exception_are_not_cut_at_1500(self):
        body = '제1조 적용대상\n' + '가' * 1488
        exception = '다만 승인된 시험자료가 있는 경우는 예외이다.'
        self.assertEqual(len(split_chunks(body + '\n' + exception)), 1)
        self.assertEqual(len(split_chunks(body + '\n\n' + exception)), 1)
        text = '# 광고 심의 기준\n\n' + '가' * 1600
        self.assertEqual(len(split_chunks(text)), 1)
        text = '제1조 금지\n금지한다.\n\n제2조 적용\n별도로 적용한다.'
        self.assertEqual(len(split_chunks(text)), 2)

    def test_long_sections_prefer_complete_sentences_and_lose_no_text(self):
        text = ('하나의 조건을 확인합니다. ' * 400).strip()
        chunks = split_chunks(text)
        self.assertTrue(all(len(chunk) <= 6000 for chunk in chunks))
        self.assertTrue(all(chunk.endswith('.') for chunk in chunks))
        self.assertEqual(''.join(text.split()), ''.join(''.join(chunks).split()))

    def test_docx_table_rows_keep_headers_values_and_empty_cells(self):
        xml = '''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>
          <w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>상품별 심의 기준</w:t></w:r></w:p>
          <w:tbl><w:tr><w:tc><w:p><w:r><w:t>상품군</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>허용 조건</w:t></w:r></w:p></w:tc></w:tr>
          <w:tr><w:tc><w:p><w:r><w:t>화장품</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>증빙자료 확인 필요</w:t></w:r></w:p></w:tc></w:tr>
          <w:tr><w:tc><w:p><w:r><w:t>식품</w:t></w:r></w:p></w:tc><w:tc><w:p/></w:tc></w:tr></w:tbl>
        </w:body></w:document>'''
        payload = io.BytesIO()
        with ZipFile(payload, 'w') as archive:
            archive.writestr('word/document.xml', xml)
        text = extract_text('guide.docx', payload.getvalue())
        self.assertIn('# 상품별 심의 기준', text)
        self.assertIn('상품군: 화장품\n허용 조건: 증빙자료 확인 필요', text)
        self.assertIn('상품군: 식품\n허용 조건: (빈 셀)', text)

    def test_pdf_keeps_page_locations_and_still_rejects_image_only(self):
        page = lambda text: SimpleNamespace(extract_text=lambda: text)
        with patch('pypdf.PdfReader', return_value=SimpleNamespace(pages=[
                page('첫 번째 쪽의 상품 광고 검토 기준입니다.'), page('두 번째 쪽의 예외 조건입니다.')])):
            text = extract_text('guide.pdf', b'fake-pdf')
        self.assertIn('[원문 1쪽]', text)
        self.assertIn('[원문 2쪽]', text)
        with patch('pypdf.PdfReader', return_value=SimpleNamespace(pages=[page('')]*10)):
            with self.assertRaises(ValueError):
                extract_text('image.pdf', b'fake-pdf')

    def test_neighbors_stay_in_selected_version_and_keep_chunk_identity(self):
        hit = {'document_id': 'eligible-version', 'chunk_id': 'c2', 'ordinal': 2,
               'content': '원칙이다.'}
        neighbors = [{'id': 'c1', 'ordinal': 1, 'content': '제1조 적용대상'},
                     {'id': 'c2', 'ordinal': 2, 'content': '원칙이다.'},
                     {'id': 'c3', 'ordinal': 3, 'content': '다만 예외이다.'}]
        paths = []
        def request(method, path):
            paths.append(path)
            return neighbors
        result = _neighbor_context(SimpleNamespace(request=request), [hit])
        self.assertEqual(result[0]['chunk_id'], 'c2')
        self.assertEqual(result[0]['context_chunks'], neighbors)
        self.assertEqual(parse_qs(urlsplit(paths[0]).query)['document_id'], ['eq.eligible-version'])
        def unavailable(*args):
            raise requests.ConnectionError('offline')
        result = _neighbor_context(SimpleNamespace(request=unavailable), [dict(hit)])
        self.assertTrue(result[0]['context_unavailable'])

    def test_retrieval_covers_context_tail_and_batches_embedding_inputs(self):
        query = '검토 질문\n' + '앞부분 ' * 600 + '뒤쪽예외조건'
        calls = []
        def rpc(name, **params):
            calls.append(params)
            return ([{'chunk_id': 'exception', 'document_id': 'v1', 'ordinal': 2,
                      'content': '뒤쪽예외조건', 'semantic_rank': 1}]
                    if '뒤쪽예외조건' in params['p_tokens'] else [])
        repository = SimpleNamespace(rpc=rpc, request=lambda *args: [])
        with patch('regulation_corpus.search_tokens', side_effect=lambda value: value), \
                patch('regulation_corpus._embed', side_effect=lambda texts, repo: [[1.0]] * len(texts)) as embed:
            rows, method = search_documents(repository, query, '화장품', date(2026, 11, 17))
        self.assertEqual([r['chunk_id'] for r in rows], ['exception'])
        self.assertEqual(method, 'hybrid')
        embed.assert_called_once()
        self.assertTrue(any('뒤쪽예외조건' in c['p_tokens'] for c in calls))
        self.assertTrue(all(c['p_category'] == '화장품' and c['p_as_of'] == '2026-11-17' for c in calls))
        self.assertTrue(all('검토 질문' in c['p_tokens'] for c in calls))

    def test_long_paragraph_tail_is_not_dropped_from_lexical_index(self):
        text = ' '.join(f'표현{i}' for i in range(200)) + ' 꼬리예외조건'
        self.assertIn('꼬리예외조건', search_tokens(text).split())

    def test_long_embedding_covers_all_parts_without_oversized_inputs(self):
        calls = []
        def post(url, **kwargs):
            inputs = kwargs['json']['input']
            calls.extend(inputs)
            return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {
                'data': [{'index': i, 'embedding': [1.0, 0.0] if len(value) == 2000 else [0.0, 1.0]}
                         for i, value in enumerate(inputs)]})
        text = '😀' * 3000
        with patch.dict(os.environ, {'REGULATION_EMBEDDINGS_ENABLED': 'true', 'OPENAI_API_KEY': 'offline-test'}), \
                patch('regulation_corpus.requests.post', side_effect=post), \
                patch('regulation_corpus.record_usage'):
            vectors = _embed([text])
        self.assertEqual(''.join(calls), text)
        self.assertTrue(all(len(value.encode('utf-8')) <= 8000 for value in calls))
        self.assertEqual(len(vectors), 1)
        self.assertAlmostEqual(vectors[0][0], 2 / 5**0.5)
        self.assertAlmostEqual(vectors[0][1], 1 / 5**0.5)


if __name__ == '__main__':
    unittest.main()
