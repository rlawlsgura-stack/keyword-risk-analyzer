import unittest

from scripts.evaluate_regulation_retrieval import evaluate


class RegulationEvaluationTests(unittest.TestCase):
    def test_metrics_use_reviewed_labels_and_reject_incomplete_results(self):
        cases = [
            {'case_id': 'positive', 'judgment_status': 'approved', 'category': 'cosmetics',
             'relevant_ids': ['rule-v1-a', 'rule-v1-b'], 'forbidden_ids': ['future-rule']},
            {'case_id': 'negative', 'judgment_status': 'approved', 'category': 'food', 'relevant_ids': []},
            {'case_id': 'unreviewed', 'judgment_status': 'draft', 'relevant_ids': None},
        ]
        results = [
            {'case_id': 'positive', 'retrieved_ids': ['unrelated', 'rule-v1-a', 'future-rule'],
             'latency_ms': 100, 'abstained': False},
            {'case_id': 'negative', 'retrieved_ids': [], 'latency_ms': 300, 'abstained': True},
        ]
        metrics = evaluate(cases, results)
        self.assertEqual(metrics['approved_case_count'], 2)
        self.assertEqual(metrics['excluded_unapproved_case_count'], 1)
        self.assertEqual(metrics['recall_at_5'], 0.5)
        self.assertEqual(metrics['recall_at_10'], 0.5)
        self.assertEqual(metrics['mrr_at_10'], 0.5)
        self.assertEqual(metrics['forbidden_hit_rate_at_10'], 0.5)
        self.assertEqual(metrics['no_evidence_abstention_accuracy'], 1)
        self.assertEqual(metrics['latency_ms_p50'], 100)
        self.assertEqual(metrics['latency_ms_p95'], 300)
        self.assertEqual(metrics['by_category']['cosmetics']['recall_at_10'], 0.5)
        self.assertEqual(metrics['by_category']['food']['no_evidence_abstention_accuracy'], 1)
        self.assertIsNone(metrics['by_category']['food']['recall_at_10'])

        for invalid in (
            results[:1],
            results + [results[0]],
            [{**results[0], 'retrieved_ids': ['rule-v1-a', 'rule-v1-a']}, results[1]],
            [{**results[0], 'latency_ms': float('nan')}, results[1]],
            [{**results[0], 'case_id': 'unknown'}, results[1]],
        ):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                evaluate(cases, invalid)
        with self.assertRaises(ValueError):
            evaluate([cases[2]], [])
        with self.assertRaises(ValueError):
            evaluate([{**cases[0], 'relevant_ids': None}], results[:1])
        for category in ('unknown', None, []):
            with self.subTest(category=category), self.assertRaises(ValueError):
                evaluate([{**cases[0], 'category': category}], results[:1])
        with self.assertRaises(ValueError):
            evaluate([{**cases[0], 'evaluation_type': []}], results[:1])

    def test_categories_cannot_hide_a_failed_group_and_scope_is_separate(self):
        categories = ('cosmetics', 'food', 'health_functional_food')
        cases = [{'case_id': category, 'category': category, 'judgment_status': 'approved',
                  'relevant_ids': ['shared-rule-v1']} for category in categories]
        cases.append({'case_id': 'scope', 'category': 'medical_device',
                      'judgment_status': 'approved', 'evaluation_type': 'scope', 'relevant_ids': None})
        results = [{'case_id': category, 'retrieved_ids': ['shared-rule-v1'] if category != 'food' else [],
                    'latency_ms': 100, 'abstained': category == 'food'} for category in categories]
        metrics = evaluate(cases, results)
        self.assertAlmostEqual(metrics['recall_at_10'], 2 / 3)
        self.assertEqual(metrics['by_category']['food']['recall_at_10'], 0)
        self.assertEqual(metrics['by_category']['health_functional_food']['recall_at_10'], 1)
        self.assertEqual(metrics['approved_case_count'], 3)
        self.assertEqual(metrics['excluded_non_relevance_case_count'], 1)
        self.assertEqual(metrics['excluded_unapproved_case_count'], 0)


if __name__ == '__main__':
    unittest.main()
