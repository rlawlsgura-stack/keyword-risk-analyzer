"""The same matching and post-match filters for Streamlit and FastAPI."""
from dataclasses import asdict
import hashlib
import json
from uuid import uuid4

from matching_engine import MatchingConfig, _KO_SUFFIX_WHITELIST, find_matches_nlp

MODES = {'exact': '정확 일치', 'similar': '유사 키워드 포함',
         'partial': '부분 문자열(최소 글자수)'}


def match_text(text, keywords, *, match_mode='유사 키워드 포함', exact_relaxed=False,
               config=None, categories=(), risks=(), **options):
    matches = find_matches_nlp(text, keywords, match_mode=match_mode,
                               exact_relaxed=exact_relaxed, config=config, **options)
    # Preserve the original overlap behavior: filter AFTER matching.
    if categories:
        matches = [m for m in matches if m.category.strip() in categories]
    if risks:
        matches = [m for m in matches if m.risk.strip() in risks]
    return matches


def analyze(repository, request, actor):
    payload = dict(request)
    analysis_id = str(payload.pop('analysis_id', None) or uuid4())
    record = payload.pop('record', False)
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True,
                                 ensure_ascii=False).encode()).hexdigest()
    if record:
        previous = repository.previous_analysis(analysis_id, actor, fingerprint)
        if previous is not None:
            return previous
    keywords = repository.load_keywords()
    symbols = repository.load_setting('ignored_special_symbols', None)
    suffixes = repository.load_setting('ko_suffix_whitelist', {'extra_suffixes': []})
    config = MatchingConfig(ko_suffixes=frozenset(_KO_SUFFIX_WHITELIST) |
                             frozenset(suffixes.get('extra_suffixes', [])))
    if symbols is not None:
        # Retain the app's empty-list fallback behavior.
        config = MatchingConfig(ignored_symbols=tuple(symbols.get('symbols', [])) or
                                  MatchingConfig().ignored_symbols,
                                ko_suffixes=config.ko_suffixes)
    matches = match_text(payload['text'], keywords, config=config,
                         match_mode=MODES[payload.get('mode', 'similar')],
                         exact_relaxed=payload.get('exact_relaxed', False),
                         categories=payload.get('categories', []), risks=payload.get('risks', []),
                         partial_min_len=payload.get('partial_min_len', 2),
                         similar_reverse_single=payload.get('similar_reverse_single', True),
                         similar_reverse_any=payload.get('similar_reverse_any', False))
    result = {'analysis_id': analysis_id, 'matches': [asdict(m) for m in matches],
              'unique_keywords': sorted({str(m.kwd_no) for m in matches if m.kwd_no}),
              'keyword_revision': keywords.attrs.get('revision'),
              'offset_unit': 'unicode_codepoint', 'end_exclusive': True,
              'recorded': record}
    if record:
        return repository.record_analysis(analysis_id, fingerprint, actor,
                                           result['keyword_revision'], result)
    return result
