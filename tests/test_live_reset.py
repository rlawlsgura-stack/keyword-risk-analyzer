"""Explicit live regression: performs the administrator's requested count reset.

Run manually: python -m unittest discover -s tests -p test_live_reset.py -v
with KRA_TEST_LIVE_RESET=1. Never runs as part of normal test discovery.
"""
import os
import unittest

from app_config import configure
from repository import COUNT_COL, LAST_COL, SupabaseRepository


@unittest.skipUnless(os.getenv('KRA_TEST_LIVE_RESET') == '1', 'explicit live reset opt-in required')
class LiveResetTests(unittest.TestCase):
    def test_http_reset_clears_counts_and_preserves_keyword_data(self):
        configure()
        repository = SupabaseRepository()
        before = repository.load_keywords()
        hits_before = repository.load_hits()
        repository.reset_counts()
        after = repository.load_keywords()
        hits_after = repository.load_hits()
        self.assertTrue(after[COUNT_COL].eq('0').all())
        self.assertTrue(after[LAST_COL].eq('').all())
        self.assertTrue(before.drop(columns=[COUNT_COL, LAST_COL]).equals(
            after.drop(columns=[COUNT_COL, LAST_COL])))
        self.assertTrue(hits_before.equals(hits_after))
        # The same request succeeds when no rows need changing.
        repository.reset_counts()
