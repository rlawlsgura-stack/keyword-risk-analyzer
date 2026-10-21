"""Rule-based keyword matching, independent of Streamlit and file storage.

Inputs are text, a pandas DataFrame, and explicit MatchingConfig/options.
Results contain original-text offsets; no counters, files, or UI are changed.
Matching and overlap rules are preserved from keyword_app2_fixed270.py.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List
import re

import pandas as pd

DB_COLS = [
    "kwd_no", "키워드명", "상품카테고리", "리스크 등급", "대체키워드",
    "리스크 등급별 세부 심의기준", "증빙자료유형",
    "키워드 조회 수(누적카운트)", "마지막 출력일자"
]


_delim_pattern = re.compile(r"[\/,;\|]")


_KO_SUFFIX_WHITELIST = {
    "와","과","은","는","이","가","을","를","의","도","만","까지","부터","보다","마다",
    "에","에서","에게","께","한테","로","으로","로서","으로서","로써","으로써","처럼","같이",
    "나","이나","든","든지","라도","이나마",
    "라고","이라고","이라","이라도","이라면","이면","면","라는","이란","란","이라는","이라는","이야","야",
    "에는","에선","에서","에서의","에의","에만","에도","부터는","까지는",
}


_DEFAULT_IGNORED_SPECIAL_SYMBOLS = ["/", "&", ",", "*"]


@dataclass(frozen=True)
class MatchingConfig:
    """Snapshot of matching settings; does not read session or file state.

    Passing an empty tuple/set explicitly disables the corresponding rules.
    The app adapter retains its existing handling of empty saved settings.
    """

    ignored_symbols: tuple[str, ...] = tuple(_DEFAULT_IGNORED_SPECIAL_SYMBOLS)
    ko_suffixes: frozenset[str] = frozenset(_KO_SUFFIX_WHITELIST)


@dataclass
class Match2:
    term: str
    start: int
    end: int
    category: str = ""
    risk: str = ""
    detail: str = ""
    kwd_no: str | None = None


def generate_keyword_variants(term: str) -> list:
    """Generate safe keyword variants for '유사 키워드 포함' mode.

    변경점(정밀도 개선):
    - (A) prefix(앞부분) 변형(예: 여드, 다이) 생성 로직 제거
    - 구두점/구분자 분리, 괄호 안/밖 텍스트 추출 등 '표기 변형'만 허용
    """
    if term is None:
        return []
    t = str(term).strip()
    if not t:
        return []
    variants = set()

    def add(v: str):
        v = (v or "").strip()
        if not v:
            return
        # 너무 짧은 토큰은 오탐 위험이 높아 제외 (영문 3미만, 한글 2미만)
        if re.search(r"[A-Za-z]", v):
            if len(v) < 3:
                return
        else:
            if len(v) < 2:
                return
        variants.add(v)

    # 원문
    add(t)

    # 구분자(/ , ; |) 분리
    for piece in _delim_pattern.split(t):
        add(piece)

    # 괄호 밖 텍스트만 추출
    outside = re.sub(r"\s*[\(\[（【].*?[\)\]）】]\s*", " ", t).strip()
    add(outside)

    # (추가) 괄호 제거 결과를 한 번 더 정리해 '여드름(acne)' 같은 표기에서 '여드름'이 안정적으로 후보에 포함되도록 함
    outside_clean = re.sub(r"[^\w가-힣]+", " ", outside).strip()
    outside_clean = re.sub(r"\s+", " ", outside_clean)
    add(outside_clean)
    for piece in _delim_pattern.split(outside_clean):
        add(piece)

    # 괄호 안 텍스트도 후보로 추가
    for inner in re.findall(r"[\(\[（【](.*?)[\)\]）】]", t):
        add(inner)
        for piece in _delim_pattern.split(inner):
            add(piece)

    # 공백 정규화
    variants = {re.sub(r"\s+", " ", v) for v in variants}
    return list(variants)


def _tokenize_with_spans(s: str):
    """Tokenize text into (token, start, end) spans.
    - 한글/영문/숫자 덩어리를 토큰으로 취급
    - 매칭은 토큰 단위(=단어 경계)로 수행하기 위함
    """
    if not s:
        return []
    token_re = re.compile(r"[A-Za-z0-9]+|[가-힣]+")
    return [(m.group(0), m.start(), m.end()) for m in token_re.finditer(s)]


def _tokenize_only(s: str):
    return [t for (t, _, _) in _tokenize_with_spans(s)]


def _normalize_english_token(token: str) -> str:
    """Lowercase & strip non-letter/hyphen characters for simple English comparisons."""
    return re.sub(r"[^a-zA-Z\-]", "", str(token)).lower()


def _english_inflection_common_prefix(a: str, b: str) -> int:
    """Return length of common prefix if a,b are considered inflectional variants (core rule set1+set2); otherwise 0.
    This is used only in '유사 키워드 포함' mode to highlight the shared stem part."""
    a_norm = _normalize_english_token(a)
    b_norm = _normalize_english_token(b)
    if not a_norm or not b_norm:
        return 0
    if a_norm == b_norm:
        # highlight full token when exactly equal
        return len(a_norm)

    def _is_variant(base: str, other: str) -> bool:
        # basic regular inflections: plural, past, progressive, comparative/superlative
        if len(base) < 3 or len(other) < 3:
            return False
        # direct suffixes for core rule sets 1+2
        for suf in ("s", "es", "ed", "ing", "er", "est"):
            if other == base + suf:
                return True
        # e-drop variants: base[:-1] + ed/ing/er/est when base endswith 'e'
        if base.endswith("e") and len(base) > 3:
            root = base[:-1]
            for suf in ("ed", "ing", "er", "est"):
                if other == root + suf:
                    return True
            # special: keep trailing 'e' and just add 'd' (e.g. 'even-tone' -> 'even-toned')
            if other == base + "d":
                return True
        return False

    eq = _is_variant(a_norm, b_norm) or _is_variant(b_norm, a_norm)
    if not eq:
        return 0

    # They are inflectional variants -> highlight longest common prefix as shared stem
    pref = 0
    for ch_a, ch_b in zip(a_norm, b_norm):
        if ch_a == ch_b:
            pref += 1
        else:
            break
    # avoid extremely short stems
    if pref < 3:
        return 0
    return pref


def _replace_ignored_symbols_with_space_keep_len(s: str, symbols: list) -> str:
    """Replace each configured symbol character with a single space.
    Length is preserved (important for start/end index mapping).
    """
    if not s:
        return s or ""
    if not symbols:
        return s
    # Build safe regex class for the given characters
    try:
        cls = "[" + "".join(re.escape(ch) for ch in symbols if isinstance(ch, str) and len(ch) == 1) + "]"
        if cls == "[]":
            return s
        return re.sub(cls, " ", s)
    except Exception:
        # Fallback: simple replace loop (still length-preserving)
        out = s
        for ch in symbols:
            if isinstance(ch, str) and len(ch) == 1:
                out = out.replace(ch, " ")
        return out


def _normalize_relaxed_whitespace_with_map(s: str) -> tuple[str, list[int]]:
    """
    Normalize text for relaxed exact matching while preserving a mapping back to original indices.

    - Collapse any run of whitespace-like chars (space, \n, \t, NBSP, ZWSP, BOM, etc.) into a single ' '.
    - Casefold for stable matching.
    - Returns (normalized_string, index_map) where index_map[i] is the original index of normalized_string[i].
    """
    if s is None:
        return "", []
    norm_chars: list[str] = []
    idx_map: list[int] = []
    in_ws = False

    def _is_ws(ch: str) -> bool:
        return ch.isspace() or ch in ("\u00A0", "\u200B", "\uFEFF")

    for i, ch in enumerate(s):
        if _is_ws(ch):
            if not in_ws:
                norm_chars.append(" ")
                idx_map.append(i)
                in_ws = True
            continue
        in_ws = False
        norm_chars.append(ch.casefold())
        idx_map.append(i)

    return "".join(norm_chars), idx_map


def _normalize_relaxed_whitespace(s: str) -> str:
    """Normalize like _normalize_relaxed_whitespace_with_map but without index mapping."""
    return _normalize_relaxed_whitespace_with_map(s)[0]


def _find_spans_by_compact_match(original: str, target: str, symbols: list) -> list:
    """Find spans in original where removing spaces and configured symbols yields target.
    Returns list of (start, end) spans (end is exclusive).
    This enables 'ignore special symbols' matching while preserving highlight indices.
    """
    if not original or not target:
        return []
    symset = set(ch for ch in (symbols or []) if isinstance(ch, str) and len(ch) == 1)
    n = len(original)
    tlen = len(target)
    spans = []
    for i in range(n):
        # quick skip: if char is ignorable, don't start here
        if original[i].isspace() or original[i] in symset:
            continue
        j = i
        built = []
        # Build compact until length reaches target length or end.
        while j < n and len(built) < tlen:
            ch = original[j]
            if ch.isspace() or ch in symset:
                j += 1
                continue
            built.append(ch)
            j += 1
        if len(built) != tlen:
            continue
        if "".join(built) == target:
            spans.append((i, j))
    return spans


def find_matches(text: str, kw_df: pd.DataFrame, match_mode: str = "유사 키워드 포함", exact_relaxed: bool = False, suffix_suggestions: dict = None, *, config: MatchingConfig | None = None, **kwargs) -> List[Match2]:
    """Find keyword matches in text.

    정밀도 개선(요청사항):
    - (A) prefix 변형 생성 제거: generate_keyword_variants에서 처리
    - (B) 단어 경계 매칭: 유사 모드에서 토큰 경계 기준으로만 검출
    - (C) 토큰 기반 매칭: 본문/키워드를 토큰화하고 토큰 시퀀스 비교로 검출

    * '정확 일치' 모드는 기존 substring 기반 동작을 유지합니다.
    """
    config = config if config is not None else MatchingConfig()
    matches: List[Match2] = []
    base = text or ""
    # For relaxed normalization, optionally replace configured special symbols with spaces (length preserved)
    base_for_match = base
    if exact_relaxed:
        try:
            base_for_match = _replace_ignored_symbols_with_space_keep_len(base_for_match, config.ignored_symbols)
        except Exception:
            base_for_match = base
    lower = base_for_match.lower()
    # Precompute normalized base (whitespace-collapsed + casefold) for relaxed exact matching
    base_norm, base_norm_map = ("", [])
    if exact_relaxed:
        try:
            base_norm, base_norm_map = _normalize_relaxed_whitespace_with_map(base_for_match)
        except Exception:
            base_norm, base_norm_map = ("", [])

    df = kw_df.copy()
    for col in DB_COLS:
        if col not in df.columns:
            df[col] = ""
    df = df[df["키워드명"].astype(str).str.strip() != ""]

    occupied_set = set()
    exact_candidates: List[Match2] = []  # exact-mode candidates collected before overlap resolution
    records = df.to_dict("records")

    # 토큰화(유사 모드에서 사용)
    token_spans = _tokenize_with_spans(base_for_match)
    tokens_lower = [t.lower() for (t, _, _) in token_spans]
    tokens_compact = [re.sub(r"\s+", "", t.lower()) for (t, _, _) in token_spans]  # 안전장치

    for r in records:
        term = str(r["키워드명"]).strip()
        category = str(r.get("상품카테고리", ""))
        risk = str(r.get("리스크 등급", ""))
        detail = str(r.get("리스크 등급별 세부 심의기준", ""))
        kwd_no = r.get("kwd_no") or None

        # 부분 문자열(최소 글자수) 모드: 키워드 내부 부분 문자열로 느슨하게 매칭
        if match_mode == "부분 문자열(최소 글자수)":
            try:
                min_len = int(kwargs.get("partial_min_len", 2))
            except Exception:
                min_len = 2
            if min_len < 2:
                min_len = 2
            term_norm = re.sub(r"\s+", "", str(term))
            if term_norm and len(term_norm) >= min_len:
                seen_spans = set()
                base_lower = base_for_match.lower()
                term_norm_lower = term_norm.lower()
                for L in range(min_len, len(term_norm_lower) + 1):
                    for i_sub in range(0, len(term_norm_lower) - L + 1):
                        sub = term_norm_lower[i_sub:i_sub+L]
                        start_idx = 0
                        while True:
                            idx2 = base_lower.find(sub, start_idx)
                            if idx2 == -1:
                                break
                            end2 = idx2 + L
                            span_key = (idx2, end2)
                            if span_key in seen_spans:
                                start_idx = idx2 + 1
                                continue
                            seen_spans.add(span_key)
                            range_occupied = any(i in occupied_set for i in range(idx2, end2))

                            # NOTE: 부분 문자열 모드에서도 같은 span(동일 start/end)에 대해
                            # 서로 다른 kwd_no(또는 term)가 매칭되는 경우는 결과 리스트에 함께 남깁니다.
                            # 하이라이트(occupied_set)는 최초 1회만 점유하도록 유지합니다.
                            already_same_span = False
                            if kwd_no is not None:
                                already_same_span = any(
                                    (m.start == idx2 and m.end == end2 and (m.kwd_no == kwd_no))
                                    for m in matches
                                )
                            else:
                                already_same_span = any(
                                    (m.start == idx2 and m.end == end2 and (m.term == term))
                                    for m in matches
                                )

                            if (not range_occupied) or (range_occupied and not already_same_span):
                                matches.append(
                                    Match2(
                                        term=term,
                                        start=idx2,
                                        end=end2,
                                        category=category,
                                        risk=risk,
                                        detail=detail,
                                        kwd_no=kwd_no,
                                    )
                                )
                                if not range_occupied:
                                    for i2 in range(idx2, end2):
                                        occupied_set.add(i2)
                            start_idx = idx2 + 1
            continue  # 다음 키워드로

        variants = generate_keyword_variants(term)

        # 기존 옵션: (괄호 제거·공백 정규화·영문 대소문자 무시)
        if match_mode == "유사 키워드 포함" and exact_relaxed:
            term_no_br = re.sub(r"\s*[\(\[（【].*?[\)\]）】]\s*", " ", str(term)).strip()
            term_no_br = re.sub(r"\s+", " ", term_no_br)
            term_norm = re.sub(r"\s+", " ", str(term)).strip()
            for _cand in [term_no_br, term_norm]:
                if _cand and _cand not in variants:
                    variants.insert(0, _cand)
                # Also add a version with ignored special symbols replaced by spaces (length preserved)
                if _cand and exact_relaxed:
                    try:
                        _cand2 = _replace_ignored_symbols_with_space_keep_len(_cand, config.ignored_symbols)
                        _cand2 = re.sub(r"\s+", " ", _cand2).strip()
                        if _cand2 and _cand2 not in variants:
                            variants.insert(0, _cand2)
                    except Exception:
                        pass

        if match_mode == "정확 일치":
            variants = [str(term)]
            if exact_relaxed:
                term_no_br = re.sub(r"\s*[\(\[（【].*?[\)\]）】]\s*", " ", str(term)).strip()
                term_no_br = re.sub(r"\s+", " ", term_no_br)
                term_norm = re.sub(r"\s+", " ", str(term)).strip()
                for _cand in [term_no_br, term_norm]:
                    if _cand and _cand not in variants:
                        variants.append(_cand)

        variants = [v for v in variants if v]
        variants.sort(key=lambda s: len(s), reverse=True)

        # ----------------------------
        # 유사 모드: 토큰 기반 + 단어 경계 + (안전한) 띄어쓰기 무시(토큰 결합) 매칭
        # ----------------------------
        if match_mode == "유사 키워드 포함":
            for v in variants:
                v = str(v).strip()
                if not v:
                    continue
                v_tokens = _tokenize_only(v)
                if not v_tokens:
                    continue
                v_tokens_lower = [x.lower() for x in v_tokens]
                v_compact = "".join(v_tokens_lower)

                n = len(v_tokens_lower)
                if n <= 0:
                    continue

                # 1) 정확한 토큰 시퀀스 일치
                # Helpers for highlight-span overrides (init before reverse-single)
                suffix_hit_end = {}  # legacy: end override (kept for backward compatibility)
                span_override = {}   # {token_index: (start_orig, end_orig)} for highlight span overrides

                starts = []
                for i in range(0, max(0, len(tokens_lower) - n + 1)):
                    if tokens_lower[i:i+n] == v_tokens_lower:
                        starts.append(i)

                # 2) 띄어쓰기 변형(붙여쓰기)을 위한 토큰 결합 일치
                #    - 예: '피부 보습' ↔ '피부보습'
                #    - window 토큰들을 붙인 문자열이 키워드 토큰 결합과 같으면 매칭
                #    - 단, 2토큰 이상일 때만 수행(1토큰은 1)에서 충분)
                if n >= 2:
                    for i in range(0, max(0, len(tokens_lower) - n + 1)):
                        if "".join(tokens_compact[i:i+n]) == v_compact:
                            starts.append(i)

                

                # (2-c) Reverse matching for single-token input (옵션):
                #   - When the input text is just one token (e.g., 'spot'), many DB keywords are longer (2+ tokens)
                #     so forward token-window matching cannot trigger. If enabled, allow matching when the
                #     single input token is contained in any keyword token (including compound tokens).
                #   - Highlight span remains the input token itself.
                # Reverse-match on input (옵션):
                #   - 기존: 입력이 1토큰(단어)일 때만 역매칭 허용
                #   - 신규: 옵션(similar_reverse_any) ON 시 토큰 수와 무관하게 역매칭 허용 (오탐/성능 영향 가능)
                use_rev_any = bool(kwargs.get("similar_reverse_any", False))
                use_rev_single = bool(kwargs.get("similar_reverse_single", False))

                # Reverse-match modes:
                #  - single-token mode: only when the whole input is 1 token (legacy behavior)
                #  - any-token mode: allow additional hit positions even if forward matches already exist,
                #    but keep it conservative: only match tokens that equal the FIRST token of the keyword.
                #    (This helps cases like later 'acne' showing the same keyword set as earlier 'acne mark care'.)
                if use_rev_single and (not starts) and len(tokens_lower) == 1:
                    q = (tokens_lower[0] or "").strip()
                    if q and any((q in t) for t in v_tokens_lower):
                        starts = [0]
                        try:
                            span_override[0] = (token_spans[0][1], token_spans[0][2])
                        except Exception:
                            pass

                if use_rev_any and (tokens_lower is not None) and v_tokens_lower:
                    for i_tok, q0 in enumerate(tokens_lower or []):
                        q = (q0 or "").strip()
                        if not q:
                            continue
                        # multi-token input: skip very short tokens to reduce false positives
                        if len(tokens_lower) != 1 and len(q) < 4:
                            continue                        # 역매칭: 키워드 토큰 어디든 포함되면 허용 (토큰 제한 없음)
                        if not any((q.lower() in t) for t in v_tokens_lower):
                            continue
                        if i_tok not in starts:
                            starts.append(i_tok)
                        try:
                            span_override[i_tok] = (token_spans[i_tok][1], token_spans[i_tok][2])
                        except Exception:
                            pass

                # If token-based match fails, allow limited Korean stem+suffix hits (whitelist),
                # e.g., '여드름에는' matching keyword '여드름' in fuzzy mode.
                # (3) 조사/어미(접미사) 화이트리스트 기반 매칭 + (4) 합성어(붙여쓰기) 내부 접미 매칭(제한적)
                # - 3) 예: '여드름에는' -> '여드름' + '에는'(whitelist)
                # - 4) 예: '미세스피큘' -> '스피큘'(token suffix)  ※ 유사일치에서만, 한글 키워드에 한해 제한적으로 허용

                # 2-b) English inflection-aware token sequence match (core rule sets 1+2)
                #     - 단수/복수, 시제(-ed), 진행형(-ing), 비교급/최상급(-er/-est) 정도의 굴절만 허용
                #     - '정확 일치'가 아닌 '유사 키워드 포함' 모드에서만 사용
                if n >= 1:
                    window_len = max(0, len(tokens_lower) - n + 1)
                    for i2 in range(window_len):
                        # 정확 일치로 이미 검출된 window는 건너뜀
                        if tokens_lower[i2:i2+n] == v_tokens_lower:
                            continue
                        ok = True
                        local_override = None
                        # 각 토큰이 같거나(동일) 영어 굴절형(세트1+2) 관계인지 검사
                        for j2 in range(n):
                            src_tok = v_tokens_lower[j2]
                            tgt_tok = tokens_lower[i2 + j2]
                            if src_tok == tgt_tok:
                                continue
                            stem_len = _english_inflection_common_prefix(src_tok, tgt_tok)
                            if stem_len <= 0:
                                ok = False
                                break
                            # 공통 어간 부분까지만 하이라이트하도록 span_override에 기록
                            # (여러 토큰이 굴절형인 경우도 있을 수 있으나, 우선 마지막 것으로 덮어쓰기)
                            t_start = token_spans[i2 + j2][1]
                            t_end = t_start + stem_len
                            # window 전체 기준으로는, 첫 토큰 시작~공통 어간 끝까지 표시
                            local_override = (token_spans[i2][1], t_end)
                        if ok:
                            starts.append(i2)
                            if local_override is not None:
                                span_override[i2] = local_override


                is_korean_kw = (n == 1 and v_compact and any("가" <= ch <= "힣" for ch in v_compact))
                if is_korean_kw:
                    kw_len = len(v_compact)

                    # 3) 키워드 어간 + 조사/어미(접미사) 화이트리스트
                    for _i, _tok in enumerate(tokens_compact):
                        if _tok.startswith(v_compact) and len(_tok) > kw_len:
                            _suf = _tok[kw_len:]
                            if _suf in config.ko_suffixes:
                                starts.append(_i)
                                _s = token_spans[_i][1]
                                _e = token_spans[_i][1] + kw_len
                                span_override[_i] = (_s, _e)
                                suffix_hit_end[_i] = _e
                            else:
                                # 후보 접미사 제안(승인형): 유사일치에서 키워드 어간+접미사 형태로 보이지만
                                # 화이트리스트에 없어 매칭되지 않은 접미사를 수집합니다.
                                if isinstance(suffix_suggestions, dict):
                                    suffix_suggestions[_suf] = suffix_suggestions.get(_suf, 0) + 1

                    # 4) 합성어 내부 접미(끝부분) 매칭: token.endswith(keyword)
                    #    - 오탐 방지: (a) 한글 키워드 최소 길이, (b) 접두부 길이 제한, (c) 한글 토큰에 한함
                    if kw_len >= 2:
                        for _i, _tok in enumerate(tokens_compact):
                            if _tok.endswith(v_compact) and len(_tok) > kw_len:
                                prefix = _tok[:-kw_len]
                                # 접두부가 너무 길면 오탐 가능성이 커져 제한합니다.
                                if not (1 <= len(prefix) <= 6):
                                    continue
                                # 토큰이 순수 한글 덩어리일 때만 적용
                                if not all(("가" <= ch <= "힣") for ch in _tok):
                                    continue
                                # 하이라이트는 키워드 부분만(토큰 끝에서 kw_len)
                                _e = token_spans[_i][2]
                                _s = _e - kw_len
                                starts.append(_i)
                                span_override[_i] = (_s, _e)

                    # 5) 합성어 내부 접두(앞부분) 매칭: token.startswith(keyword)
                    #    - 오탐 방지: (a) 한글 키워드 최소 길이, (b) 접미부 길이 제한, (c) 한글 토큰에 한함
                    if kw_len >= 2:
                        for _i, _tok in enumerate(tokens_compact):
                            if _tok.startswith(v_compact) and len(_tok) > kw_len:
                                suffix = _tok[kw_len:]
                                # 접미부가 너무 길면 오탐 가능성이 커져 제한합니다.
                                if not (1 <= len(suffix) <= 6):
                                    continue
                                # 토큰이 순수 한글 덩어리일 때만 적용
                                if not all(("가" <= ch <= "힣") for ch in _tok):
                                    continue
                                # 하이라이트는 키워드 부분만(토큰 시작에서 kw_len)
                                _s = token_spans[_i][1]
                                _e = _s + kw_len
                                # 안전장치: 계산된 end가 토큰 끝을 넘지 않도록
                                if _e > token_spans[_i][2]:
                                    _e = token_spans[_i][2]
                                starts.append(_i)
                                span_override[_i] = (_s, _e)


                # (4/5-EN) English compound/prefix/suffix fuzzy hits (옵션 A):
                #     - Korean '합성어 내부 접두/접미' 규칙을 영어에도 동일한 철학으로 적용
                #     - 예: 'spot' -> 'hotspot'(endswith), 'spotless'(startswith)
                #     - 오탐 방지: (a) 키워드 최소 길이, (b) 접두/접미 길이 제한, (c) 알파벳 토큰에 한함
                is_english_kw = (n == 1 and v_compact and all('a' <= ch <= 'z' for ch in v_compact))
                if is_english_kw:
                    kw_len = len(v_compact)
                    if kw_len >= 2:
                        for _i, _tok in enumerate(tokens_compact):
                            if not _tok or len(_tok) <= kw_len:
                                continue
                            # 알파벳 토큰에만 적용 (숫자/혼합/기호 제외)
                            if not _tok.isalpha():
                                continue

                            # 접미(끝부분) 매칭: token.endswith(keyword)
                            if _tok.endswith(v_compact):
                                prefix = _tok[:-kw_len]
                                if not (1 <= len(prefix) <= 6):
                                    pass
                                else:
                                    _e = token_spans[_i][2]
                                    _s = _e - kw_len
                                    starts.append(_i)
                                    span_override[_i] = (_s, _e)

                            # 접두(앞부분) 매칭: token.startswith(keyword)
                            if _tok.startswith(v_compact):
                                suffix = _tok[kw_len:]
                                if not (1 <= len(suffix) <= 6):
                                    pass
                                else:
                                    _s = token_spans[_i][1]
                                    _e = _s + kw_len
                                    if _e > token_spans[_i][2]:
                                        _e = token_spans[_i][2]
                                    starts.append(_i)
                                    span_override[_i] = (_s, _e)
# dedup starts
                if not starts:
                    continue
                starts = sorted(set(starts))

                for si in starts:
                    if 'span_override' in locals() and si in span_override:
                        start_orig, end_orig = span_override[si]
                    else:
                        start_orig = token_spans[si][1]
                        end_orig = suffix_hit_end.get(si, token_spans[si + n - 1][2])

                    # 기존 겹침/우선순위 로직 유지
                    for _i_m, _m in enumerate(list(matches)):
                        old_start = getattr(_m, 'start', None)
                        old_end = getattr(_m, 'end', 0)
                        if old_start is None:
                            continue
                        old_len = max(0, old_end - old_start)
                        new_len = max(0, end_orig - start_orig)
                        # 기존 로직: 같은 시작점에서 더 긴 매치가 있으면 교체 (대표 span 유지)
                        if old_start == start_orig and old_end < end_orig:
                            for _j in range(old_start, old_end):
                                occupied_set.discard(_j)
                            _m.start = start_orig
                            _m.end = end_orig
                            for _j in range(start_orig, end_orig):
                                occupied_set.add(_j)
                            continue
                        # 보완 로직: 포함 관계인 경우 더 넓은 구간을 대표 span으로 사용하고,
                        #           이후 매치들은 이 대표 span에 kwd_no를 누적해서 표시
                        if (start_orig <= old_start and end_orig >= old_end) or (old_start <= start_orig and old_end >= end_orig):
                            new_start = min(start_orig, old_start)
                            new_end = max(end_orig, old_end)
                            # 기존 occupied 구간 정리 후 대표 구간 재설정
                            for _j in range(old_start, old_end):
                                occupied_set.discard(_j)
                            _m.start = new_start
                            _m.end = new_end
                            for _j in range(new_start, new_end):
                                occupied_set.add(_j)
                            # 현재 후보도 대표 구간을 사용
                            start_orig, end_orig = new_start, new_end

                    range_occupied = any(i in occupied_set for i in range(start_orig, end_orig))

                    if not range_occupied:
                        matches.append(Match2(term=term, start=start_orig, end=end_orig, category=category, risk=risk, detail=detail, kwd_no=kwd_no))
                        for i2 in range(start_orig, end_orig):
                            occupied_set.add(i2)
                    else:
                        same_span_exists = any((m2.start == start_orig and m2.end == end_orig) for m2 in matches)
                        already_same = any((m2.start == start_orig and m2.end == end_orig and (m2.kwd_no == kwd_no and m2.category == category and m2.risk == risk)) for m2 in matches)
                        if same_span_exists and not already_same:
                            matches.append(Match2(term=term, start=start_orig, end=end_orig, category=category, risk=risk, detail=detail, kwd_no=kwd_no))
            continue  # 다음 키워드로

        # ----------------------------
        # ----------------------------
        # 정확 일치 모드: 후보 수집 후 "긴 span 우선"으로 overlap 해결
        # - 기존 occupied_set(중복 방지) 때문에 짧은 키워드가 먼저 잡히면
        #   긴 문장 키워드가 스킵되는 문제를 방지하기 위함
        # ----------------------------
        _before_term_exact_count = len(exact_candidates)
        for v in variants:
            v_cmp = str(v)
            if exact_relaxed:
                try:
                    v_cmp = _replace_ignored_symbols_with_space_keep_len(v_cmp, config.ignored_symbols)
                except Exception:
                    v_cmp = str(v)
            v_lower = str(v_cmp).lower()

            def _add_exact(_s: int, _e: int):
                if _s < 0 or _e <= _s:
                    return
                exact_candidates.append(Match2(term=term, start=_s, end=_e, category=category, risk=risk, detail=detail, kwd_no=kwd_no))

            # 1) ignored symbol-aware compact match (e.g., '안티&에이징' ↔ '안티에이징')
            if exact_relaxed:
                try:
                    syms = config.ignored_symbols
                except Exception:
                    syms = []
                if syms:
                    target_compact = re.sub(r"\s+", "", v_lower)
                    try:
                        spans = _find_spans_by_compact_match(base.lower(), target_compact, syms)
                    except Exception:
                        spans = []
                    for (_s0, _e0) in spans:
                        _add_exact(_s0, _e0)

            # 2) whitespace-flex regex on original base (keeps indices for highlight)
            if exact_relaxed and (" " in str(v_cmp)):
                try:
                    ws_class = r"[ \t\r\n\u00A0\u200B\uFEFF]+"
                    pat = re.escape(str(v_cmp).strip())
                    pat = re.sub(r"(\\ )+", ws_class, pat)
                    for _m_ws in re.finditer(pat, base, flags=re.IGNORECASE):
                        _add_exact(_m_ws.start(), _m_ws.end())
                except Exception:
                    pass

            # 3) normalized relaxed exact match (collapse whitespace to one space) with index mapping
            if exact_relaxed:
                try:
                    kw_norm = _normalize_relaxed_whitespace(str(v_cmp)).strip()
                    if kw_norm and base_norm and base_norm_map and ("".join(kw_norm.split()) != ""):
                        _p = 0
                        kw_cf = kw_norm.casefold()
                        while True:
                            _hit = base_norm.find(kw_cf, _p)
                            if _hit == -1:
                                break
                            _hit_end = _hit + len(kw_norm)
                            _s0 = base_norm_map[_hit]
                            _e0 = base_norm_map[_hit_end - 1] + 1
                            _add_exact(_s0, _e0)
                            _p = _hit + 1
                except Exception:
                    pass

            # 4) plain substring find on preprocessed lower (keeps indices as-is)
            start2 = 0
            while True:
                idx = lower.find(v_lower, start2)
                if idx == -1:
                    break
                _add_exact(idx, idx + len(v_cmp))
                start2 = idx + len(v_cmp)

        # (옵션) 긴 문장 키워드: 정확(완전)일치 실패 시 유사(토큰) 매칭으로 1회 재시도
        # - 조건: 이 term에서 exact 후보가 하나도 생성되지 않았고, 키워드 토큰 수 >= N
        # - 목적: 공백/줄바꿈/특수 공백 차이 등으로 긴 문장 키워드가 통째로 미검출되는 경우 보완
        try:
            _fallback_enabled = bool(kwargs.get("exact_fallback_similar", True))
        except Exception:
            _fallback_enabled = True
        try:
            _fallback_min_tokens = int(kwargs.get("exact_fallback_min_tokens", 4))
        except Exception:
            _fallback_min_tokens = 4

        if _fallback_enabled and len(exact_candidates) == _before_term_exact_count:
            _fb_v = str(variants[0]).strip() if variants else ""
            _fb_tokens = _tokenize_only(_fb_v) if _fb_v else []
            if _fb_tokens and len(_fb_tokens) >= _fallback_min_tokens:
                _fb_tokens_lower = [x.lower() for x in _fb_tokens]
                _fb_compact = "".join(_fb_tokens_lower)
                _n = len(_fb_tokens_lower)

                _starts = []
                for _i in range(0, max(0, len(tokens_lower) - _n + 1)):
                    if tokens_lower[_i:_i+_n] == _fb_tokens_lower:
                        _starts.append(_i)

                if _n >= 2:
                    for _i in range(0, max(0, len(tokens_lower) - _n + 1)):
                        if "".join(tokens_compact[_i:_i+_n]) == _fb_compact:
                            _starts.append(_i)

                for _s in sorted(set(_starts)):
                    try:
                        start_orig = token_spans[_s][1]
                        end_orig = token_spans[_s + _n - 1][2]
                    except Exception:
                        continue
                    _add_exact(start_orig, end_orig)
        # (옵션) 긴 문장 키워드: 정확(완전)일치 실패 시 유사(토큰) 매칭으로 1회 재시도
        # - 조건: 이 term에서 exact match가 하나도 생성되지 않았고, 키워드 토큰 수 >= N
        # - 목적: 공백/줄바꿈/특수 공백 차이 등으로 긴 문장 키워드가 통째로 미검출되는 경우 보완
        try:
            _fallback_enabled = bool(kwargs.get("exact_fallback_similar", True))
        except Exception:
            _fallback_enabled = True
        try:
            _fallback_min_tokens = int(kwargs.get("exact_fallback_min_tokens", 4))
        except Exception:
            _fallback_min_tokens = 4

        if _fallback_enabled and len(matches) == _before_term_exact_count:
            _fb_v = str(variants[0]).strip() if variants else ""
            _fb_tokens = _tokenize_only(_fb_v) if _fb_v else []
            if _fb_tokens and len(_fb_tokens) >= _fallback_min_tokens:
                _fb_tokens_lower = [x.lower() for x in _fb_tokens]
                _fb_compact = "".join(_fb_tokens_lower)
                _n = len(_fb_tokens_lower)

                # forward: exact token sequence
                _starts = []
                for _i in range(0, max(0, len(tokens_lower) - _n + 1)):
                    if tokens_lower[_i:_i+_n] == _fb_tokens_lower:
                        _starts.append(_i)

                # forward: spacing variation (token-compact)
                if _n >= 2:
                    for _i in range(0, max(0, len(tokens_lower) - _n + 1)):
                        if "".join(tokens_compact[_i:_i+_n]) == _fb_compact:
                            _starts.append(_i)

                # add matches
                for _s in sorted(set(_starts)):
                    try:
                        start_orig = token_spans[_s][1]
                        end_orig = token_spans[_s + _n - 1][2]
                    except Exception:
                        continue
                    if start_orig < 0 or end_orig <= start_orig:
                        continue

                    # same overlap policy as exact: do not override occupied range
                    if any(i in occupied_set for i in range(start_orig, end_orig)):
                        continue
                    matches.append(Match2(term=term, start=start_orig, end=end_orig, category=category, risk=risk, detail=detail, kwd_no=kwd_no))
                    for _j in range(start_orig, end_orig):
                        occupied_set.add(_j)

    # Resolve overlaps for exact match mode by preferring longer spans.
    if match_mode == "정확 일치":
        try:
            by_span = {}  # (start,end) -> list[Match2]
            for m in exact_candidates:
                by_span.setdefault((m.start, m.end), []).append(m)
            spans = list(by_span.keys())
            # Prefer longer matches first, then earlier start
            spans.sort(key=lambda se: (-(se[1]-se[0]), se[0], se[1]))

            def _overlaps(a, b):
                return not (a[1] <= b[0] or b[1] <= a[0])

            selected = []
            for sp in spans:
                if any(_overlaps(sp, s0) for s0 in selected):
                    continue
                selected.append(sp)

            matches = []
            for sp in selected:
                matches.extend(by_span.get(sp, []))
        except Exception:
            matches = list(exact_candidates)
    matches.sort(key=lambda m: (m.start, m.end))
    return matches


def find_matches_nlp(
    text: str,
    kw_df: pd.DataFrame,
    match_mode: str = "유사 키워드 포함",
    exact_relaxed: bool = False,
    suffix_suggestions: dict = None,
    *,
    config: MatchingConfig | None = None,
    **kwargs,
) -> List[Match2]:
    """Compatibility entry point for the existing app.

    The former additional spacing matcher returned no results. The old wrapper
    also did not forward suffix_suggestions to the core matcher; preserve that
    behavior here. Call find_matches directly to collect suffix suggestions.
    """
    return find_matches(
        text, kw_df, match_mode=match_mode, exact_relaxed=exact_relaxed,
        config=config, **kwargs,
    )

