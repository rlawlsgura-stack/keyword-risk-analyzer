"""FIXED272 only: shared Kiwi content tokens plus approved literal expressions.

No automatic fragment generation or external API. Legacy engines stay unchanged.
"""
from dataclasses import replace
from functools import lru_cache
from threading import Lock

from matching_engine import (Match2, _keyword_variants, _comparison_with_map,
                             _maximal_matches)
from service import match_text as legacy_match_text

SETTING_NAME = 'approved_partial_expressions_v272'
_lock = Lock()
_CONTENT_TAGS = {'NNG', 'NNP', 'NR', 'NP', 'VV', 'VA', 'MAG', 'MAJ', 'SL', 'SH', 'SN'}
_MIN_PARTIAL_CHARS = 2


def _has_min_partial_chars(value):
    return len(''.join(str(value or '').split())) >= _MIN_PARTIAL_CHARS


@lru_cache(maxsize=1)
def _kiwi():
    try:
        from kiwipiepy import Kiwi
        return Kiwi(num_workers=1)
    except (ImportError, OSError, RuntimeError) as exc:
        raise RuntimeError('Kiwi를 사용할 수 없어 일부 일치를 중단했습니다. 설치 상태를 확인하세요.') from exc


def validate_expressions(term, expressions, config):
    """Approval must name a nonempty literal part, not invent a synonym."""
    config = replace(config, mode='exact', strip_bracket_notes=False,
                     normalize_whitespace=True, ignore_case=True, normalize_symbols=True)
    variants = [_comparison_with_map(term, config)[0]]
    approved = []
    for expression in expressions:
        expression = expression.strip()
        if not expression:
            continue
        normalized = _comparison_with_map(expression, config)[0]
        if not _has_min_partial_chars(normalized):
            raise ValueError('승인 표현은 공백을 제외하고 최소 2글자 이상이어야 합니다.')
        if not normalized or not any(normalized in v for v in variants):
            raise ValueError('승인 표현은 등록 키워드에 포함된 비어 있지 않은 표현이어야 합니다.')
        if expression not in approved:
            approved.append(expression)
    return approved


def _boundary_text(text, config):
    if config.normalization_options()['normalize_symbols']:
        for symbol in config.ignored_symbols:
            if symbol:
                text = text.replace(symbol, ' ' * len(symbol))
    return text


@lru_cache(maxsize=4096)
def _keyword_tokens(text):
    with _lock:
        return tuple(t for t in _kiwi().tokenize(text)
                     if t.tag.split('-')[0] in _CONTENT_TAGS)


def match_text(text, keywords, *, config, categories=(), risks=(), approved_partials=None, **options):
    if config.mode != 'similar':
        return legacy_match_text(text, keywords, config=config, categories=categories, risks=risks, **options)
    for column, selected in (('상품카테고리', categories), ('리스크 등급', risks)):
        if selected:
            keywords = (keywords.loc[keywords[column].astype(str).str.strip().isin(selected)]
                        if column in keywords else keywords.iloc[:0])
    # Keep original offsets: substitutions for Kiwi must never change text length.
    with _lock:
        tokens = _kiwi().tokenize(_boundary_text(text, config))
    # A grammatical particle, ending or suffix alone must not anchor a match.
    tokens = [t for t in tokens if t.tag.split('-')[0] in _CONTENT_TAGS]
    starts = {t.start for t in tokens}
    ends = {t.start + t.len for t in tokens}
    source_tokens = {}
    for token in tokens:
        key = _comparison_with_map(token.form, config)[0]
        if key and _has_min_partial_chars(key):
            source_tokens.setdefault(key, []).append((token.start, token.start + token.len))
    normalized, index_map = _comparison_with_map(text, config)
    matches = []
    for row in keywords.fillna('').to_dict('records'):
        term, code = str(row['키워드명']), str(row.get('kwd_no', ''))
        expressions = list(_keyword_variants(term, replace(config, mode='exact')))
        # Compare whole analyzed tokens, never substrings of token forms.
        forms = {_comparison_with_map(t.form, config)[0]
                 for expression in expressions
                 for t in _keyword_tokens(_boundary_text(expression, config))
                 if _has_min_partial_chars(_comparison_with_map(t.form, config)[0])}
        for form in forms:
            for start, end in source_tokens.get(form, ()):
                matches.append(Match2(term, start, end, str(row.get('상품카테고리', '')),
                                      str(row.get('리스크 등급', '')),
                                      str(row.get('리스크 등급별 세부 심의기준', '')), code or None))
        saved = (approved_partials or {}).get(code, {})
        # Renaming/reusing a keyword ID invalidates its previous approvals.
        if saved.get('term') == term:
            saved_expressions = [expression for expression in saved.get('expressions', [])
                                 if _has_min_partial_chars(_comparison_with_map(expression, config)[0])]
            expressions.extend(validate_expressions(term, saved_expressions, config))
        for expression in dict.fromkeys(expressions):
            target, _ = _comparison_with_map(expression, config)
            if not target or not _has_min_partial_chars(target):
                continue
            offset = 0
            while (found := normalized.find(target, offset)) >= 0:
                start, end = index_map[found], index_map[found + len(target) - 1] + 1
                if start in starts and end in ends:
                    matches.append(Match2(term, start, end, str(row.get('상품카테고리', '')),
                                          str(row.get('리스크 등급', '')),
                                          str(row.get('리스크 등급별 세부 심의기준', '')), code or None))
                offset = found + 1
    return sorted(_maximal_matches(matches), key=lambda m: (m.start, m.end))
