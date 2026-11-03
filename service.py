"""The same matching and post-match filters for Streamlit and FastAPI."""
from dataclasses import asdict, replace
import hashlib
import json
import re
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


def serialize_matches(matches, keywords):
    """Include catalog metadata needed by the React hover detail table."""
    catalog = {}
    for row in keywords.to_dict('records'):
        code = str(row.get('kwd_no', '')).strip()
        if code:
            catalog[code] = row

    def value(row, column):
        item = row.get(column, '') if row else ''
        if item is None or item != item:
            return ''
        return str(item).strip()

    serialized = []
    for match in matches:
        item = asdict(match) if hasattr(match, '__dataclass_fields__') else dict(match)
        row = catalog.get(str(item.get('kwd_no') or ''))
        item.update(
            alternative=value(row, '대체키워드'),
            evidence_type=value(row, '증빙자료유형'),
            hit_count=value(row, '키워드 조회 수(누적카운트)'),
            last_search_date=value(row, '마지막 출력일자'),
        )
        serialized.append(item)
    return serialized


def enrich_previous_analysis(previous, repository, *, include_keyword_rows=False):
    """Attach one current catalog snapshot for result tables and code details."""
    if previous is None:
        return None
    matches = previous.get('matches', [])
    keywords = repository.load_keywords()
    result = dict(previous)
    if not all('alternative' in match for match in matches):
        result['matches'] = serialize_matches(matches, keywords)
    else:
        result['matches'] = matches
    if include_keyword_rows:
        codes = {str(match.get('kwd_no') or '').strip() for match in result['matches']}
        codes.discard('')
        result['unique_keyword_rows'] = [
            {str(key): str(value or '').strip() for key, value in row.items()}
            for row in keywords.to_dict('records')
            if str(row.get('kwd_no') or '').strip() in codes
        ]
        def display_order(row):
            code = str(row.get('kwd_no') or '')
            match = re.match(r'^([A-Za-z]+)(\d+)$', code)
            return ((match.group(1), int(match.group(2)), str(row.get('키워드명') or ''))
                    if match else ('', 0, str(row.get('키워드명') or '')))
        result['unique_keyword_rows'].sort(key=display_order)
        result['catalog_revision'] = keywords.attrs.get('revision')
    return result


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
            return enrich_previous_analysis(previous, repository)
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
    result = {'analysis_id': analysis_id, 'matches': serialize_matches(matches, keywords),
              'unique_keywords': sorted({str(m.kwd_no) for m in matches if m.kwd_no}),
              'keyword_revision': keywords.attrs.get('revision'),
              'offset_unit': 'unicode_codepoint', 'end_exclusive': True,
              'recorded': record}
    if record:
        return repository.record_analysis(analysis_id, fingerprint, actor,
                                           result['keyword_revision'], result)
    return result


def analyze_current(repository, request, actor):
    """Current Streamlit text rules with one idempotent recorded collection."""
    from approved_matching import SETTING_NAME, match_text as match_approved
    from auxiliary_analysis import extract_unmatched_term_surfaces

    payload = dict(request)
    analysis_id = str(payload.pop('analysis_id'))
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True,
                                 ensure_ascii=False).encode()).hexdigest()
    previous = repository.previous_analysis(analysis_id, actor, fingerprint)
    if previous is not None:
        return enrich_previous_analysis(previous, repository, include_keyword_rows=True)

    keywords = repository.load_keywords()
    config = load_matching_config(repository, MatchingConfig(
        mode=payload['mode'], exact_relaxed=True,
        partial_min_len=payload['partial_min_len'],
        similar_reverse_single=False, similar_reverse_any=False,
        **{name: payload[name] for name in NORMALIZATION_OPTIONS},
    ))
    approved = repository.load_setting(SETTING_NAME, {}) if config.mode == 'similar' else None
    text = payload['text']
    matches = match_approved(text, keywords, config=config,
                             categories=payload['categories'], risks=payload['risks'],
                             approved_partials=approved)
    coverage = (match_approved(text, keywords, config=config, approved_partials=approved)
                if payload['categories'] or payload['risks'] else matches)
    candidates = extract_unmatched_term_surfaces(text, coverage, limit=None)
    result = {'analysis_id': analysis_id, 'matches': serialize_matches(matches, keywords),
              'unique_keywords': sorted({str(m.kwd_no) for m in matches if m.kwd_no}),
              'keyword_revision': keywords.attrs.get('revision'),
              'offset_unit': 'unicode_codepoint', 'end_exclusive': True,
              'recorded': True}
    recorded = repository.record_analysis_with_unmatched(
        analysis_id, fingerprint, actor, result['keyword_revision'], result, candidates)
    return enrich_previous_analysis(recorded, repository, include_keyword_rows=True)
