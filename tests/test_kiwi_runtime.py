import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import approved_matching
import auxiliary_analysis
import kiwi_runtime


class SharedKiwiRuntimeTests(unittest.TestCase):
    def setUp(self):
        kiwi_runtime._create_kiwi.cache_clear()

    def tearDown(self):
        kiwi_runtime._create_kiwi.cache_clear()

    def test_analysis_helpers_share_one_model_instance(self):
        instances = []

        class FakeKiwi:
            def __init__(self, *, num_workers):
                self.num_workers = num_workers
                instances.append(self)

        with patch.dict(sys.modules, {'kiwipiepy': SimpleNamespace(Kiwi=FakeKiwi)}):
            matching_model = approved_matching._kiwi()
            auxiliary_model = auxiliary_analysis._kiwi()

        self.assertIs(matching_model, auxiliary_model)
        self.assertEqual(len(instances), 1)
        self.assertEqual(instances[0].num_workers, 1)


if __name__ == '__main__':
    unittest.main()
