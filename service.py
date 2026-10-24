"""The same matching and post-match filters for Streamlit and FastAPI."""
from dataclasses import asdict, replace
import hashlib
import json
from uuid import uuid4

from matching_engine import MATCH_MODES as MODES, NORMALIZATION_OPTIONS, MatchingConfig, _KO_SUFFIX_WHITELIST, find_matches_nlp

def load_matching_config(repository, config):
    """Add saved common rules to a frozen per-analysis configuration."""
    symbols = repository.load_setting('ignored_special_symbols', None)
    suffixes = repository.load_setting('ko_suffix_whitelist', {'extra_suffixes': []})
    ignored_symbols = MatchingConfig().ignored_symbols
    if symbols is not None:
        # Preserve the existing app/API fallback for an empty saved list.
        ignored_symbols = tuple(symbols.get('symbols', [])) or ignored_symbols
    return replace(config,
                   ignored_symbols=ignored_symbols,
                   ko_suffixes=frozenset(_KO_SUFFIX_WHITELIST) |
                               frozenset(suffixes.get('extra_suffixes', [])))


def match_text(text, keywords, *, match_mode=None, exact_relaxed=None,
               config=None, categories=(), risks=(), **options):
    # Excluded keywords must never suppress eligible candidates during overlap handling.
    for column, selected in (('상품카테고리', categories), ('리스크 등급', risks)):
        if selected:
            keywords = (keywords.loc[keywords[column].astype(str).str.strip().isin(selected)]
                        if column in keywords else keywords.iloc[:0])
    return find_matches_nlp(text, keywords, match_mode=match_mode,
                            exact_relaxed=exact_relaxed, config=config, **options)


def analyze(repository, request, actor):
    payload = dict(request)
    # Preserve fingerprints of recorded legacy requests when new fields are omitted/null.
    for name in NORMALIZATION_OPTIONS:
        if payload.get(name) is None:
            payload.pop(name, None)
    analysis_id = str(payload.pop('analysis_id', None) or uuid4())
    record = payload.pop('record', False)
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True,
                                 ensure_ascii=False).encode()).hexdigest()
    if record:
        previous = repository.previous_analysis(analysis_id, actor, fingerprint)
        if previous is not None:
            return previous
    keywords = repository.load_keywords()
    config = load_matching_config(repository, MatchingConfig(
        mode=payload.get('mode', 'similar'),
        exact_relaxed=payload.get('exact_relaxed', False),
        partial_min_len=payload.get('partial_min_len', 2),
        similar_reverse_single=payload.get('similar_reverse_single', True),
        similar_reverse_any=payload.get('similar_reverse_any', False),
        **{name: payload.get(name) for name in NORMALIZATION_OPTIONS}))
    matches = match_text(payload['text'], keywords, config=config,
                         categories=payload.get('categories', []), risks=payload.get('risks', []))
    result = {'analysis_id': analysis_id, 'matches': [asdict(m) for m in matches],
              'unique_keywords': sorted({str(m.kwd_no) for m in matches if m.kwd_no}),
              'keyword_revision': keywords.attrs.get('revision'),
              'offset_unit': 'unicode_codepoint', 'end_exclusive': True,
              'recorded': record}
    if record:
        return repository.record_analysis(analysis_id, fingerprint, actor,
                                           result['keyword_revision'], result)
    return result
