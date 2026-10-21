"""Results captured from 2d17555 before restructuring the matching engine."""
from dataclasses import asdict, FrozenInstanceError
import json
from pathlib import Path
import unittest

import pandas as pd

from matching_engine import MatchingConfig, find_matches
from service import MODES, load_matching_config, match_text


class MatchingRegressionTests(unittest.TestCase):
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
                                  similar_reverse_single=True)
        config = load_matching_config(SettingsRepository(), original)
        self.assertEqual(config.mode, 'partial')
        self.assertTrue(config.exact_relaxed)
        self.assertEqual(config.partial_min_len, 4)
        self.assertEqual(config.ignored_symbols, MatchingConfig().ignored_symbols)
        self.assertIn('테스트말', config.ko_suffixes)
        self.assertNotIn('테스트말', original.ko_suffixes)
        with self.assertRaises(FrozenInstanceError):
            config.mode = 'exact'


if __name__ == '__main__':
    unittest.main()
