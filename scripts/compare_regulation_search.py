"""Read-only comparison of reviewed questions against the approved document corpus.

Run with an API environment: python scripts/compare_regulation_search.py cases.jsonl
The case file must use the fields documented by evaluate_regulation_retrieval.py.
"""
import argparse
import json
import os
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app_config import configure
from regulation_corpus import search_documents
from repository import SupabaseRepository
from scripts.evaluate_regulation_retrieval import evaluate, read_jsonl


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('cases', type=Path)
    parser.add_argument('--output-dir', type=Path, default=Path('tmp/regulation-evaluation'))
    args = parser.parse_args()
    configure()
    repository = SupabaseRepository()
    cases = read_jsonl(args.cases)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    strategies = ('raw', 'lexical', 'fuzzy', 'semantic', 'hybrid') if os.getenv('REGULATION_EMBEDDINGS_ENABLED', 'false').lower() == 'true' else ('raw', 'lexical', 'fuzzy', 'hybrid')
    if 'semantic' not in strategies:
        print('임베딩 비활성: semantic 비교를 건너뛰며 hybrid는 어휘·유사 문자열 결합만 평가합니다.')
    for strategy in strategies:
        results = []
        for case in cases:
            if case.get('judgment_status') != 'approved' or case.get('evaluation_type', 'relevance') != 'relevance':
                continue
            started = time.perf_counter()
            rows, _ = search_documents(repository, case['question'],
                case.get('category_filter', ''), date.fromisoformat(case['as_of']), strategy)
            results.append({'case_id': case['case_id'],
                            'retrieved_ids': [row['chunk_id'] for row in rows],
                            'abstained': not bool(rows),
                            'latency_ms': round((time.perf_counter() - started) * 1000, 2)})
        output = args.output_dir / f'{strategy}.jsonl'
        output.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in results), encoding='utf-8')
        try:
            summary = evaluate(cases, results)
            print(strategy, json.dumps(summary, ensure_ascii=False))
        except ValueError as exc:
            print(f'{strategy}: 평가 라벨 확인 필요: {exc}')


if __name__ == '__main__':
    main()
