"""FIXED272 only: shared Kiwi content tokens plus approved literal expressions.

No automatic fragment generation or external API. Legacy engines stay unchanged.
"""
from dataclasses import asdict, dataclass, field, replace
from functools import lru_cache

from matching_engine import (Match2, _keyword_variants, _comparison_with_map,
                             _maximal_matches)
from service import match_text as legacy_match_text
from kiwi_runtime import get_kiwi, tokenization_lock

SETTING_NAME = 'approved_partial_expressions_v272'
_lock = tokenization_lock
_CONTENT_TAGS = {'NNG', 'NNP', 'NR', 'NP', 'VV', 'VA', 'MAG', 'MAJ', 'SL', 'SH', 'SN'}
_MIN_PARTIAL_CHARS = 2


@dataclass
class ExplainedMatch(Match2):
    match_reason: str = ''
    matched_expression: str = ''
    registered_expression: str = ''
    normalization_options: dict = field(default_factory=dict)


def _explain(match, text, config, reason, expression):
    target, _ = _comparison_with_map(expression, config)
    registered, positions = _comparison_with_map(match.term, config)
    offset = registered.find(target) if target else -1
    surface = (match.term[positions[offset]:positions[offset + len(target) - 1] + 1]
               if offset >= 0 else '')
    if reason == 'similar_keyword':
        surface = expression
    return ExplainedMatch(**asdict(match), match_reason=reason,
                          matched_expression=text[match.start:match.end],
                          registered_expression=surface,
                          normalization_options=config.normalization_options())


def _has_min_partial_chars(value):
    return len(''.join(str(value or '').split())) >= _MIN_PARTIAL_CHARS


def _kiwi():
    try:
        return get_kiwi()
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


def match_text(text, keywords, *, config, categories=(), risks=(), approved_partials=None,
               similar_keywords=None, **options):
    if config.mode != 'similar':
        matches = legacy_match_text(text, keywords, config=config, categories=categories, risks=risks, **options)
        matches = [_explain(match, text, config, 'exact' if config.mode == 'exact' else 'substring',
                            text[match.start:match.end]) for match in matches]
        # Approved similar keywords are literal aliases and apply in every analysis mode.
        if similar_keywords:
            selected = keywords
            for column, values in (('상품카테고리', categories), ('리스크 등급', risks)):
                if values:
                    selected = (selected.loc[selected[column].astype(str).str.strip().isin(values)]
                                if column in selected else selected.iloc[:0])
            boundary_tokens = _kiwi().tokenize(_boundary_text(text, config))
            starts = {token.start for token in boundary_tokens}
            ends = {token.start + token.len for token in boundary_tokens}
            normalized, index_map = _comparison_with_map(text, config)
            for row in selected.fillna('').to_dict('records'):
                term, code = str(row['키워드명']), str(row.get('kwd_no', ''))
                saved = similar_keywords.get(code, {})
                if saved.get('term') != term:
                    continue
                for item in saved.get('items', []):
                    if not isinstance(item, dict) or item.get('canonical_term') != term:
                        continue
                    expression = str(item.get('expression', '')).strip()
                    target, _ = _comparison_with_map(expression, config)
                    if not _has_min_partial_chars(target):
                        continue
                    offset = 0
                    while (found := normalized.find(target, offset)) >= 0:
                        start, end = index_map[found], index_map[found + len(target) - 1] + 1
                        if start in starts and end in ends:
                            match = Match2(term, start, end, str(row.get('상품카테고리', '')),
                                           str(row.get('리스크 등급', '')),
                                           str(row.get('리스크 등급별 세부 심의기준', '')), code or None)
                            matches.append(_explain(match, text, config, 'similar_keyword', expression))
                        offset = found + 1
        return sorted(_maximal_matches(matches), key=lambda m: (m.start, m.end))
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
    alias_tokens = _kiwi().tokenize(_boundary_text(text, config))
    alias_starts = {t.start for t in alias_tokens}
    alias_ends = {t.start + t.len for t in alias_tokens}
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
                match = Match2(term, start, end, str(row.get('상품카테고리', '')),
                                      str(row.get('리스크 등급', '')),
                                      str(row.get('리스크 등급별 세부 심의기준', '')), code or None)
                matches.append(_explain(match, text, config, 'content_token', form))
        saved = (approved_partials or {}).get(code, {})
        approved = []
        # Renaming/reusing a keyword ID invalidates its previous approvals.
        if saved.get('term') == term:
            saved_expressions = [expression for expression in saved.get('expressions', [])
                                 if _has_min_partial_chars(_comparison_with_map(expression, config)[0])]
            approved = validate_expressions(term, saved_expressions, config)
            expressions.extend(approved)
        similar_saved = (similar_keywords or {}).get(code, {})
        aliases = []
        if similar_saved.get('term') == term:
            aliases = [str(item.get('expression', '')).strip()
                       for item in similar_saved.get('items', [])
                       if isinstance(item, dict) and item.get('canonical_term') == term]
            aliases = [value for value in aliases if _has_min_partial_chars(
                _comparison_with_map(value, config)[0])]
            expressions.extend(aliases)
        for expression in dict.fromkeys(expressions):
            target, _ = _comparison_with_map(expression, config)
            if not target or not _has_min_partial_chars(target):
                continue
            offset = 0
            while (found := normalized.find(target, offset)) >= 0:
                start, end = index_map[found], index_map[found + len(target) - 1] + 1
                boundaries = (alias_starts, alias_ends) if expression in aliases else (starts, ends)
                if start in boundaries[0] and end in boundaries[1]:
                    match = Match2(term, start, end, str(row.get('상품카테고리', '')),
                                          str(row.get('리스크 등급', '')),
                                          str(row.get('리스크 등급별 세부 심의기준', '')), code or None)
                    reason = ('similar_keyword' if expression in aliases else
                              'approved_expression' if expression in approved else 'literal_expression')
                    matches.append(_explain(match, text, config, reason, expression))
                offset = found + 1
    return sorted(_maximal_matches(matches), key=lambda m: (m.start, m.end))
