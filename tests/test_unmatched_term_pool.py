import re
import unittest
from types import SimpleNamespace

from matching_engine import Match2
from auxiliary_analysis import (
    extract_unmatched_term_surfaces,
    normalize_unmatched_term_candidates,
)


class FakeKiwi:
    def tokenize(self, text):
        return [SimpleNamespace(form=match.group(), tag="NNG", start=match.start(),
                                len=len(match.group()))
                for match in re.finditer(r"[\uac00-\ud7a3A-Za-z0-9]+", text)]


class UnmatchedTermPoolTests(unittest.TestCase):
    def test_persistent_collection_can_keep_more_than_1000_surfaces(self):
        text = ' '.join(f'candidate{i}' for i in range(1200))
        rows = extract_unmatched_term_surfaces(text, [], kiwi=FakeKiwi(), limit=None)
        self.assertEqual(len(rows), 1200)
        self.assertTrue(all(row['occurrences'] == 1 for row in rows))

    def test_extracts_unmatched_surface_forms_without_normalizing_or_saving(self):
        text = "필러 antiaging AntiAging 123"
        matches = [Match2("필러", 0, 2)]

        rows = extract_unmatched_term_surfaces(text, matches, kiwi=FakeKiwi())

        self.assertEqual(rows, [
            {"surface_key": "antiaging", "surface": "antiaging", "occurrences": 2},
        ])

    def test_normalizes_surface_forms_after_explicit_analysis(self):
        rows = normalize_unmatched_term_candidates([
            {"surface_key": "antiaging", "surface": "antiaging", "occurrences": 2},
            {"surface_key": "antiaging-alt", "surface": "AntiAging", "occurrences": 1},
        ], kiwi=FakeKiwi())

        self.assertEqual(rows, [{
            "term": "antiaging", "occurrences": 3,
            "source_terms": "AntiAging | antiaging",
        }])

    def test_real_kiwi_skips_matched_span_and_particles(self):
        text = "필러를 사용하여 피부를 관리합니다. 필러를 추천합니다."
        matches = [Match2("필러", start, start + 2)
                   for start in (0, text.rindex("필러"))]

        rows = extract_unmatched_term_surfaces(text, matches)
        surfaces = {row["surface"] for row in rows}

        self.assertNotIn("필러", surfaces)
        self.assertTrue(surfaces.intersection({"사용", "피부", "관리", "추천"}))


if __name__ == "__main__":
    unittest.main()
