"""Results captured from 2d17555 before restructuring the matching engine."""
from dataclasses import asdict, FrozenInstanceError, replace
from itertools import product
import json
from pathlib import Path
import unittest

import pandas as pd

from matching_engine import MatchingConfig, find_matches
from service import MODES, load_matching_config, match_text


class MatchingRegressionTests(unittest.TestCase):
    def test_keyword_ranges_preserve_repetitions_codes_and_literal_symbols(self):
        base = MatchingConfig(strip_bracket_notes=True, normalize_whitespace=True,
                              ignore_case=True, normalize_symbols=False)
        for mode in ('exact', 'similar', 'partial'):
            keywords = pd.DataFrame([{'kwd_no': 'S', '키워드명': '피부'},
                                     {'kwd_no': 'L', '키워드명': '피부보습'}])
            with self.subTest(mode=mode):
                found = find_matches('피부보습', keywords, config=replace(base, mode=mode))
                self.assertEqual([(m.kwd_no, m.start, m.end) for m in found], [('S', 0, 2), ('L', 0, 4)])
                found = find_matches('피부피부', keywords.iloc[:1], config=replace(base, mode=mode))
                self.assertEqual([(m.start, m.end) for m in found], [(0, 2), (2, 4)])
            if mode != 'partial':
                for term in ('&피부', '피부&'):
                    keywords = pd.DataFrame([{'kwd_no': 'K', '키워드명': term}])
                    self.assertEqual(find_matches('피부', keywords, config=replace(base, mode=mode)), [])
                    self.assertTrue(find_matches('피부', keywords, config=replace(
                        base, mode=mode, normalize_symbols=True)))
        keywords = pd.DataFrame([{'kwd_no': 'K', '키워드명': 'Spot Care'}])
        found = find_matches('Spots Care', keywords, config=replace(base, mode='similar'))
        self.assertEqual([(m.start, m.end) for m in found], [(0, 10)])

    def test_filters_apply_before_other_keywords_can_suppress_matches(self):
        keywords = pd.DataFrame([
            {'kwd_no': 'S', '키워드명': '피부', '상품카테고리': '화장품', '리스크 등급': '1등급'},
            {'kwd_no': 'L', '키워드명': '피부보습', '상품카테고리': '식품', '리스크 등급': '3등급'},
        ])
        for mode in ('exact', 'similar', 'partial'):
            for config in (MatchingConfig(mode=mode), MatchingConfig(mode=mode,
                    strip_bracket_notes=True, normalize_whitespace=True, ignore_case=True, normalize_symbols=True)):
                for filters in ({'categories': ['화장품']}, {'risks': ['1등급']}):
                    with self.subTest(mode=mode, config=config, filters=filters):
                        found = match_text('피부보습', keywords, config=config, **filters)
                        self.assertEqual({m.kwd_no for m in found}, {'S'})
                        self.assertEqual({(m.start, m.end) for m in found}, {(0, 2)})

    def test_fragment_search_uses_any_consecutive_part_and_keeps_maximal_occurrences(self):
        base = MatchingConfig(mode='partial', strip_bracket_notes=True, normalize_whitespace=True,
                              ignore_case=True, normalize_symbols=False, partial_min_len=3)
        keywords = pd.DataFrame([{'kwd_no': 'K', '키워드명': '안티에이징'}])
        text = '에이징 관리가 필요하다. 에이징을 다시 확인한다.'
        found = match_text(text, keywords, config=base)
        self.assertEqual([(m.start, m.end) for m in found], [(0, 3), (14, 17)])
        self.assertEqual(match_text(text, keywords, config=replace(base, partial_min_len=4)), [])
        keywords['키워드명'] = '피부보습'
        found = match_text('피부보습', keywords, config=replace(base, partial_min_len=2))
        self.assertEqual([(m.start, m.end) for m in found], [(0, 4)])
        keywords['키워드명'] = 'aba'
        found = match_text('ababa', keywords, config=replace(base, partial_min_len=2))
        self.assertEqual([(m.start, m.end) for m in found], [(0, 3), (2, 5)])

    def test_independent_options_control_each_normalization_without_bypasses(self):
        for matcher in (find_matches, match_text):
            for mode in ('exact', 'similar'):
                keywords = pd.DataFrame([{'kwd_no': 'X001', '키워드명': 'Anti Aging(note)'}])
                text = '🙂 anti&\naging'
                for bracket, whitespace, case, symbols in product((False, True), repeat=4):
                    with self.subTest(matcher=matcher.__name__, mode=mode, flags=(bracket, whitespace, case, symbols)):
                        config = MatchingConfig(mode=mode, exact_relaxed=True,
                            strip_bracket_notes=bracket, normalize_whitespace=whitespace,
                            ignore_case=case, normalize_symbols=symbols)
                        found = matcher(text, keywords, config=config)
                        self.assertEqual(bool(found), all((bracket, whitespace, case, symbols)))
                        if found:
                            self.assertEqual({text[m.start:m.end] for m in found}, {'anti&\naging'})

            cases = [
                ('strip_bracket_notes', '안티에이징(anti-aging)', '안티에이징으로', '안티에이징'),
                ('normalize_whitespace', '피부보습', '피부\n\t\u00a0\u200b\ufeff보습', '피부\n\t\u00a0\u200b\ufeff보습'),
                ('normalize_whitespace', 'one two three four', 'one\ntwo three four', 'one\ntwo three four'),
                ('ignore_case', 'Spot', 'spot', 'spot'),
                ('normalize_symbols', '피부 보습', '피부&보습', '피부&보습'),
            ]
            for mode in ('exact', 'similar', 'partial'):
                for name, term, text, expected in cases:
                    if mode == 'partial' and name == 'strip_bracket_notes':
                        continue  # Partial search intentionally permits a fragment of the full name.
                    keywords = pd.DataFrame([{'kwd_no': 'X001', '키워드명': term}])
                    for enabled in (False, True):
                        with self.subTest(matcher=matcher.__name__, mode=mode, option=name, enabled=enabled):
                            options = dict(strip_bracket_notes=False, normalize_whitespace=False,
                                           ignore_case=False, normalize_symbols=False)
                            options[name] = enabled
                            found = matcher(text, keywords, config=MatchingConfig(
                                mode=mode, partial_min_len=len(term.replace(' ', ''))
                                if name == 'normalize_whitespace' else len(term), **options))
                            self.assertEqual(bool(found), enabled)
                            if found:
                                self.assertEqual({text[m.start:m.end] for m in found}, {expected})

            # Case-sensitive inflection, compound and reverse paths must honor the same switch.
            for term, text in [('Care', 'caring'), ('Spot', 'spotless'), ('Dark Spot', 'spot')]:
                keywords = pd.DataFrame([{'kwd_no': 'X001', '키워드명': term}])
                for enabled in (False, True):
                    found = matcher(text, keywords, config=MatchingConfig(
                        mode='similar', ignore_case=enabled, similar_reverse_single=True))
                    self.assertEqual(bool(found), enabled, (term, text, enabled))

            keywords = pd.DataFrame([{'kwd_no': 'X001', '키워드명': 'X(note)'}])
            self.assertEqual(matcher('X', keywords, config=MatchingConfig(
                mode='similar', strip_bracket_notes=True)), [])

    def test_exact_parenthetical_name_depends_on_relaxed_option_not_suffixes(self):
        self.assertIn('으로', MatchingConfig().ko_suffixes)
        text = '이제 깊이가 다른 안티에이징으로 지워냅니다.'
        start = text.index('안티에이징')
        keywords = pd.DataFrame([{'kwd_no': 'B245', '키워드명': '안티에이징(anti-aging)'}])
        for matcher in (find_matches, match_text):
            for suffixes in (frozenset(), frozenset({'으로'})):
                with self.subTest(matcher=matcher.__name__, suffixes=suffixes):
                    config = MatchingConfig(mode='exact', exact_relaxed=False, ko_suffixes=suffixes)
                    self.assertEqual(matcher(text, keywords, config=config), [])
                    found = matcher(text, keywords, config=MatchingConfig(
                        mode='exact', exact_relaxed=True, ko_suffixes=suffixes))
                    self.assertTrue(found)
                    self.assertEqual({(m.kwd_no, m.start, m.end) for m in found},
                                     {('B245', start, start + len('안티에이징'))})
                    found = matcher(text, keywords, config=MatchingConfig(
                        mode='similar', exact_relaxed=False, ko_suffixes=suffixes))
                    self.assertEqual([(m.kwd_no, m.start, m.end) for m in found],
                                     [('B245', start, start + len('안티에이징'))])
            plain_keywords = keywords.copy()
            plain_keywords['키워드명'] = '안티에이징'
            found = matcher(text, plain_keywords, config=MatchingConfig(
                mode='exact', exact_relaxed=False, ko_suffixes=frozenset()))
            self.assertEqual([(m.start, m.end) for m in found],
                             [(start, start + len('안티에이징'))])
            literal = '안티에이징(anti-aging)으로'
            found = matcher(literal, keywords, config=MatchingConfig(mode='exact'))
            self.assertEqual([(m.start, m.end) for m in found], [(0, len('안티에이징(anti-aging)'))])

    def test_captured_results_keep_positions_duplicates_and_overlap_rules(self):
        fixture = Path(__file__).parent / 'fixtures' / 'matching_baseline.json'
        for case in json.loads(fixture.read_text(encoding='utf-8'))['cases']:
            with self.subTest(case=case['name']):
                keywords = pd.DataFrame(case['keywords'])
                options = dict(match_mode=MODES[case['mode']],
                               exact_relaxed=case['exact_relaxed'], **case['options'])
                for matcher in (find_matches, match_text):
                    actual = [asdict(m) for m in matcher(case['text'], keywords, **options)]
                    actual.sort(key=lambda m: (m['start'], m['end'], m['kwd_no']))
                    self.assertEqual(actual, case['expected'])
                    config = MatchingConfig(mode=case['mode'], exact_relaxed=case['exact_relaxed'],
                                            **case['options'])
                    actual = [asdict(m) for m in matcher(case['text'], keywords, config=config)]
                    actual.sort(key=lambda m: (m['start'], m['end'], m['kwd_no']))
                    self.assertEqual(actual, case['expected'])

    def test_common_rules_preserve_run_options_and_empty_list_fallback(self):
        class SettingsRepository:
            def load_setting(self, name, default):
                return {'ignored_special_symbols': {'symbols': []},
                        'ko_suffix_whitelist': {'extra_suffixes': ['테스트말']}}[name]

        original = MatchingConfig(mode='partial', exact_relaxed=True, partial_min_len=4,
                                  similar_reverse_single=True, strip_bracket_notes=False,
                                  normalize_whitespace=True, ignore_case=False, normalize_symbols=True)
        config = load_matching_config(SettingsRepository(), original)
        self.assertEqual(config.mode, 'partial')
        self.assertTrue(config.exact_relaxed)
        self.assertEqual(config.partial_min_len, 4)
        self.assertFalse(config.strip_bracket_notes)
        self.assertTrue(config.normalize_whitespace)
        self.assertFalse(config.ignore_case)
        self.assertTrue(config.normalize_symbols)
        self.assertEqual(config.ignored_symbols, MatchingConfig().ignored_symbols)
        self.assertIn('테스트말', config.ko_suffixes)
        self.assertNotIn('테스트말', original.ko_suffixes)
        with self.assertRaises(FrozenInstanceError):
            config.mode = 'exact'


if __name__ == '__main__':
    unittest.main()
