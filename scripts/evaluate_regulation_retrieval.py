"""Score exported retrieval results against reviewed relevance labels, offline.

This does not run an embedding model or decide whether an advertisement is legal.
Run from the repository root with --cases labels.jsonl --results results.jsonl.
"""
import argparse
import json
import math
from pathlib import Path
import statistics


def read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding='utf-8-sig').splitlines()
            if line.strip()]


def by_case_id(rows, label):
    indexed = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('case_id'), str) or not row['case_id']:
            raise ValueError(f'{label}: each row needs a non-empty case_id')
        key = row['case_id']
        if key in indexed:
            raise ValueError(f'{label}: duplicate case_id {key}')
        indexed[key] = row
    return indexed


def ids(value, label):
    if not isinstance(value, list) or any(not isinstance(x, str) or not x for x in value):
        raise ValueError(f'{label}: expected a list of non-empty IDs; null is not an empty label')
    if len(value) != len(set(value)):
        raise ValueError(f'{label}: duplicate IDs')
    return value


def summarize(scores):
    def mean(field):
        values = [row[field] for row in scores if row[field] is not None]
        return statistics.mean(values) if values else None

    latencies = sorted(row['latency_ms'] for row in scores)
    return {
        'approved_case_count': len(scores),
        'positive_case_count': sum(row['recall_at_5'] is not None for row in scores),
        'no_evidence_case_count': sum(row['no_evidence_abstention_accuracy'] is not None for row in scores),
        **{field: mean(field) for field in (
            'recall_at_5', 'recall_at_10', 'mrr_at_10',
            'no_evidence_abstention_accuracy', 'forbidden_hit_rate_at_10')},
        'latency_ms_p50': latencies[math.ceil(len(latencies) * 0.50) - 1],
        'latency_ms_p95': latencies[math.ceil(len(latencies) * 0.95) - 1],
        'latency_percentile_method': 'nearest_rank',
    }


def evaluate(cases, results):
    all_cases = by_case_id(cases, 'cases')
    for row in all_cases.values():
        evaluation_type = row.get('evaluation_type', 'relevance')
        if not isinstance(evaluation_type, str) or evaluation_type not in {'relevance', 'scope', 'generation_safety'}:
            raise ValueError(f"{row['case_id']}: unknown evaluation_type")
    approved = {key: row for key, row in all_cases.items()
                if row.get('judgment_status') == 'approved'
                and row.get('evaluation_type', 'relevance') == 'relevance'}
    if not approved:
        raise ValueError('No approved relevance judgments. Draft cases cannot measure model quality.')
    predictions = by_case_id(results, 'results')
    if approved.keys() != predictions.keys():
        raise ValueError('Results must cover exactly the approved case IDs; missing or unknown cases found.')

    scores = []
    for key, case in approved.items():
        category = case.get('category')
        if not isinstance(category, str) or category not in {'cosmetics', 'food', 'health_functional_food'}:
            raise ValueError(f'{key}: a supported product category is required')
        gold = set(ids(case.get('relevant_ids'), f'{key}.relevant_ids'))
        forbidden = set(ids(case.get('forbidden_ids', []), f'{key}.forbidden_ids'))
        if gold & forbidden:
            raise ValueError(f'{key}: an ID cannot be both relevant and forbidden')
        result = predictions[key]
        ranked = ids(result.get('retrieved_ids'), f'{key}.retrieved_ids')
        elapsed = result.get('latency_ms')
        if (isinstance(elapsed, bool) or not isinstance(elapsed, (int, float))
                or not math.isfinite(elapsed) or elapsed < 0):
            raise ValueError(f'{key}: latency_ms must be finite and non-negative')
        if not isinstance(result.get('abstained'), bool):
            raise ValueError(f'{key}: abstained must be a boolean')
        scores.append({
            'category': category,
            'latency_ms': elapsed,
            'forbidden_hit_rate_at_10': bool(set(ranked[:10]) & forbidden),
            'recall_at_5': len(set(ranked[:5]) & gold) / len(gold) if gold else None,
            'recall_at_10': len(set(ranked[:10]) & gold) / len(gold) if gold else None,
            'mrr_at_10': next((1 / rank for rank, item in enumerate(ranked[:10], 1)
                               if item in gold), 0) if gold else None,
            'no_evidence_abstention_accuracy': (not ranked and result['abstained']) if not gold else None,
        })
    return {
        **summarize(scores),
        'excluded_unapproved_case_count': sum(row.get('judgment_status') != 'approved' for row in all_cases.values()),
        'excluded_non_relevance_case_count': sum(row.get('judgment_status') == 'approved'
            and row.get('evaluation_type', 'relevance') != 'relevance' for row in all_cases.values()),
        'by_category': {category: summarize([row for row in scores if row['category'] == category])
                        for category in sorted({row['category'] for row in scores})},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases', required=True, type=Path)
    parser.add_argument('--results', required=True, type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        metrics = evaluate(read_jsonl(args.cases), read_jsonl(args.results))
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    rendered = json.dumps(metrics, ensure_ascii=False, indent=2, allow_nan=False)
    if args.output:
        args.output.write_text(rendered + '\n', encoding='utf-8')
    print(rendered)


if __name__ == '__main__':
    main()
