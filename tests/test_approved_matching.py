import unittest
import os
from pathlib import Path
from uuid import uuid4
from dataclasses import asdict, replace
from unittest.mock import patch

import pandas as pd

from approved_matching import match_text, validate_expressions
from matching_engine import MatchingConfig
from service import match_text as legacy_match_text


class ApprovedMatchingTests(unittest.TestCase):
    def setUp(self):
        self.config = MatchingConfig(mode='similar', strip_bracket_notes=True,
                                     normalize_whitespace=True, ignore_case=True, normalize_symbols=True)
        self.df = pd.DataFrame([
            {'kwd_no': 'A', '키워드명': '안티에이징', '상품카테고리': '화장품'},
            {'kwd_no': 'B', '키워드명': '지방', '상품카테고리': '식품'},
            {'kwd_no': 'C', '키워드명': '피부', '상품카테고리': '화장품'},
        ])
        self.approved = {'A': {'term': '안티에이징', 'expressions': ['에이징']}}

    def test_approval_repetition_original_offsets_and_boundaries(self):
        text = '😀 안티에이징으로 관리. 에이징 관리와 에이징 관리. 티에이, 마사지 방법, 피부과. 지방을 줄이다.'
        matches = match_text(text, self.df, config=self.config, approved_partials=self.approved)
        self.assertEqual([(m.kwd_no, text[m.start:m.end]) for m in matches],
                         [('A', '안티에이징'), ('A', '에이징'), ('A', '에이징'), ('B', '지방')])
        self.assertFalse(match_text('에이징 관리 티에이', self.df, config=self.config))
        stale = {'A': {'term': '이전 등록명', 'expressions': ['에이징']}}
        self.assertFalse(match_text('에이징 관리', self.df, config=self.config, approved_partials=stale))

    def test_filters_overlap_and_keyword_identity(self):
        df = pd.concat([self.df, pd.DataFrame([{'kwd_no': 'D', '키워드명': '에이징', '상품카테고리': '화장품'}])])
        hits = match_text('에이징 관리', df, config=self.config, approved_partials=self.approved)
        self.assertEqual({m.kwd_no for m in hits}, {'A', 'D'})
        self.assertEqual(len(match_text('안티에이징', self.df, config=self.config,
                                       approved_partials={'A': {'term': '안티에이징', 'expressions': ['안티에이징']}})), 1)
        self.assertFalse(match_text('에이징 관리', df, config=self.config,
                                    approved_partials=self.approved, categories=['식품']))

    def test_exact_and_exploration_unchanged_and_no_kiwi_fallback(self):
        for mode in ('exact', 'partial'):
            config = replace(self.config, mode=mode)
            expected = legacy_match_text('피부과 티에이 마사지 방법', self.df, config=config)
            actual = match_text('피부과 티에이 마사지 방법', self.df, config=config)
            self.assertEqual([asdict(m) for m in expected], [asdict(m) for m in actual])
        with patch('approved_matching._kiwi', side_effect=RuntimeError('unavailable')):
            with self.assertRaises(RuntimeError):
                match_text('티에이', self.df, config=self.config)

    def test_approval_validation_and_normalization_options(self):
        self.assertEqual(validate_expressions('안티에이징', ['', '에이징', '에이징'], self.config), ['에이징'])
        with self.assertRaises(ValueError):
            validate_expressions('안티에이징', ['보습'], self.config)
        df = pd.DataFrame([{'kwd_no': 'E', '키워드명': 'ANTIAGING(note)'}])
        self.assertEqual(len(match_text('antiaging', df, config=self.config)), 1)
        self.assertFalse(match_text('antiaging', df, config=replace(self.config, ignore_case=False)))
        self.assertFalse(match_text('note', df, config=self.config))
        self.assertEqual(len(match_text('note', df, config=replace(self.config, strip_bracket_notes=False))), 1)

    def test_shared_content_tokens_find_aging_without_approval(self):
        terms = ['노화방지', '노화관리방지', '항노화', '노화예방', '피부노화']
        df = pd.DataFrame([{'kwd_no': str(i), '키워드명': term} for i, term in enumerate(terms)])
        text = '장벽 강화: 민감해진 노화 피부를 보호하는 고밀도 수분 장벽 포뮬러'
        hits = match_text(text, df, config=self.config)
        aging = {m.term for m in hits if text[m.start:m.end] == '노화'}
        self.assertEqual(aging, set(terms))
        self.assertFalse(match_text('티에이 마사지 방법', self.df, config=self.config))
        repeated = match_text('노화와 노화', df, config=self.config)
        self.assertEqual(len(repeated), len(terms) * 2)

    def test_admin_approval_ui_and_existing_result_contract(self):
        from streamlit.testing.v1 import AppTest
        from test_integration import MemoryRepository
        from matching_engine import MATCH_MODES
        from approved_matching import SETTING_NAME
        repository = MemoryRepository()
        repository.df.loc[0, ['kwd_no', '키워드명']] = ['A', '안티에이징']
        settings = {}
        actor = {'id': str(uuid4()), 'email': 'admin@example.test', 'app_metadata': {'role': 'admin'}}
        with patch.dict(os.environ, {'STORAGE_BACKEND': 'supabase',
                                     'SUPABASE_URL': 'https://example.supabase.co',
                                     'SUPABASE_SECRET_KEY': 'test-only'}), \
             patch('repository.SupabaseRepository.user', return_value=actor), \
             patch('repository.SupabaseRepository.load_keywords', side_effect=repository.load_keywords), \
             patch('repository.SupabaseRepository.load_setting', side_effect=lambda k, default: settings.get(k, default)), \
             patch('repository.SupabaseRepository.save_setting', side_effect=settings.__setitem__), \
             patch('repository.SupabaseRepository.load_hits', side_effect=repository.load_hits), \
             patch('repository.SupabaseRepository.record_analysis') as record:
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'keyword_app2_fixed272.py'))
            app.session_state['auth_session'] = {'access_token': 'test-token', 'expires_at': 9999999999}
            app.session_state['match_mode'] = MATCH_MODES['similar']
            app.run(timeout=30)
            self.assertFalse(app.exception)
            app.text_area[0].input('에이징 관리와 에이징 관리. 티에이')
            app.button(key='btn_analyze').click().run(timeout=30)
            record.assert_not_called()
            editor = next(area for area in app.text_area if (area.key or '').startswith('approved_partial_text_'))
            editor.input('에이징')
            next(button for button in app.button if button.label == '승인 표현 저장').click().run(timeout=30)
            self.assertEqual(settings[SETTING_NAME]['A']['expressions'], ['에이징'])
            app.button(key='btn_analyze').click().run(timeout=30)
            self.assertFalse(app.exception)
            self.assertEqual(app.session_state['analysis_count'], 1)
            self.assertEqual(len(app.session_state['analysis_df_full']), 2)
            self.assertIn("data-kwd='A'", app.session_state['analysis_highlight_html'])
            self.assertNotIn('실제 일치 문구', app.session_state['analysis_df_display_unique'].columns)
            self.assertEqual(record.call_args.args[-1]['unique_keywords'], ['A'])
            actor['app_metadata']['role'] = 'member'
            app.run(timeout=30)
            self.assertFalse(app.exception)
            self.assertFalse(any(button.label == '승인 표현 저장' for button in app.button))


if __name__ == '__main__':
    unittest.main()
