"""Read-only morphology and semantic candidates; never alters keyword matches."""
from functools import lru_cache
from collections import Counter
import math
import os
import re
from threading import Lock
import time
import unicodedata

import requests

from matching_engine import _BRACKET_NOTES


UNMATCHED_SURFACE_LIMIT_REVISION = 1


class AuxiliaryUnavailable(Exception):
    pass


_kiwi_lock = Lock()


@lru_cache(maxsize=1)
def _kiwi():
    try:
        from kiwipiepy import Kiwi
        return Kiwi(num_workers=1)
    except (ImportError, OSError, RuntimeError):
        raise AuxiliaryUnavailable('Kiwi를 사용할 수 없습니다. requirements.txt의 패키지를 설치하세요.') from None


def _tokens(text, kiwi):
    # Keep negation/content words; remove grammatical endings/particles only.
    return [token for token in kiwi.tokenize(text)
            if token.tag.startswith(('N', 'V', 'M', 'X', 'SL', 'SH', 'SN'))]


_POOL_LATIN = re.compile(r"[a-z]")
_POOL_HANGUL = re.compile(r"[가-힣]")
_POOL_STOPWORDS = {"a", "an", "and", "are", "as", "at", "be", "by", "for",
                   "from", "in", "is", "it", "of", "on", "or", "that",
                   "the", "this", "to", "was", "were", "with"}


def extract_unmatched_term_surfaces(text, matches, kiwi=None, limit=1000):
    """Count unnormalized Kiwi surface forms outside matched spans."""
    text = str(text or "")
    if not text:
        return []

    uncovered = list(text)
    for match in matches or ():
        for index in range(max(0, int(match.start)), min(len(text), int(match.end))):
            uncovered[index] = " "

    counts = Counter()
    surfaces = {}
    with _kiwi_lock:
        for token in (kiwi or _kiwi()).tokenize("".join(uncovered)):
            if not token.tag.startswith(("N", "V", "M", "X", "SL", "SH")):
                continue
            surface = text[token.start:token.start + token.len].strip()
            key = unicodedata.normalize("NFKC", surface).casefold().strip()
            if (not key or len(key) > 100 or key.isdecimal()
                    or key in _POOL_STOPWORDS):
                continue
            if len(_POOL_HANGUL.findall(key)) < 2 and len(_POOL_LATIN.findall(key)) < 3:
                continue
            if len(surface) > 150:
                continue
            surfaces.setdefault(key, surface)
            counts[key] += 1

    return [
        {"surface_key": term, "surface": surfaces[term], "occurrences": count}
        for term, count in counts.most_common(None if limit is None else max(1, min(int(limit), 1000)))
    ]


def normalize_unmatched_term_candidates(surface_rows, kiwi=None):
    """Suggest Kiwi lemma forms from temporary raw candidates."""
    grouped = {}
    with _kiwi_lock:
        kiwi = kiwi or _kiwi()
        for row in surface_rows:
            surface = str(row.get("surface", "")).strip()
            if not surface:
                continue
            tokens = [token for token in kiwi.tokenize(surface)
                      if token.tag.startswith(("N", "V", "M", "X", "SL", "SH"))]
            forms = [unicodedata.normalize("NFKC", token.form).casefold().strip()
                     for token in tokens]
            forms = [form for form in forms if form]
            term = " ".join(forms) or unicodedata.normalize("NFKC", surface).casefold()
            if (len(term) > 100 or term.isdecimal()
                    or term in _POOL_STOPWORDS
                    or (len(_POOL_HANGUL.findall(term)) < 2 and len(_POOL_LATIN.findall(term)) < 3)):
                continue
            candidate = grouped.setdefault(term, {"term": term, "occurrences": 0,
                                                    "source_terms": set()})
            candidate["occurrences"] += int(row.get("occurrences", 0) or 0)
            candidate["source_terms"].add(surface)

    return [{**row, "source_terms": " | ".join(sorted(row["source_terms"]))}
            for row in sorted(grouped.values(), key=lambda item: (-item["occurrences"], item["term"]))]


@lru_cache(maxsize=4096)
def _term_forms(term):
    return tuple(token.form.lower() for token in _tokens(term, _kiwi()))


def morphology_candidates(text, records, limit):
    with _kiwi_lock:
        kiwi = _kiwi()
        source = _tokens(text, kiwi)
        forms = [token.form.lower() for token in source]
        candidates = []
        for row in records:
            term = _BRACKET_NOTES.sub('', str(row.get('키워드명', ''))).strip()
            target = list(_term_forms(term))
            if not target:
                continue
            for start in range(len(forms) - len(target) + 1):
                if forms[start:start + len(target)] == target:
                    first, last = source[start], source[start + len(target) - 1]
                    candidates.append({'kwd_no': str(row['kwd_no']),
                                       'keyword': str(row['키워드명']),
                                       'start': first.start, 'end': last.start + last.len})
                    break
        return candidates[:limit]


def _embed(texts, model, key):
    try:
        response = requests.post('https://api.openai.com/v1/embeddings',
                                 headers={'Authorization': 'Bearer ' + key},
                                 json={'model': model, 'input': list(texts),
                                       'encoding_format': 'float'}, timeout=(5, 30))
    except requests.RequestException:
        raise AuxiliaryUnavailable('임베딩 서버에 연결할 수 없습니다. 잠시 후 다시 실행하세요.') from None
    if response.status_code != 200:
        messages = {401: '임베딩 API 키를 확인하세요.',
                    429: '임베딩 API 잔액 또는 호출 한도를 확인하세요.'}
        raise AuxiliaryUnavailable(messages.get(response.status_code, '임베딩 서버 요청에 실패했습니다.'))
    try:
        data = sorted(response.json()['data'], key=lambda row: row['index'])
        if [row['index'] for row in data] != list(range(len(texts))):
            raise ValueError('Unexpected embedding indexes')
        vectors = [row['embedding'] for row in data]
        dimensions = len(vectors[0])
        if not dimensions or any(len(v) != dimensions or
                                 any(not isinstance(n, (int, float)) or not math.isfinite(n) for n in v)
                                 for v in vectors):
            raise ValueError('Invalid embedding vectors')
        return vectors
    except (ValueError, KeyError, TypeError, IndexError):
        raise AuxiliaryUnavailable('임베딩 서버의 응답 형식이 올바르지 않습니다.') from None


@lru_cache(maxsize=32)
def _catalog_batch(texts, model, key):
    # Cache catalog vectors only, never advertising text. Content/model/key changes invalidate.
    import numpy as np
    return np.asarray(_embed(texts, model, key), dtype=np.float32)


def semantic_candidates(text, records, limit):
    import numpy as np
    key = os.getenv('OPENAI_API_KEY', '').strip()
    if not key:
        raise AuxiliaryUnavailable('OPENAI_API_KEY를 설정한 후 의미 검색을 사용할 수 있습니다.')
    model = os.getenv('EMBEDDING_MODEL', 'text-embedding-3-small')
    documents = []
    for row in records:
        parts = [str(row.get(name, '')).strip() for name in
                 ('키워드명', '상품카테고리', '리스크 등급별 세부 심의기준')]
        documents.append('\n'.join(value for value in parts if value and value != '-')[:1200])
    # Preserve original sentence context, including negation. Overlap handles split boundaries.
    chunks = tuple(text[i:i + 800] for i in range(0, len(text), 700))
    queries = np.asarray(_embed(chunks, model, key), dtype=np.float32)
    batches = []
    started = time.monotonic()
    for i in range(0, len(documents), 64):
        if time.monotonic() - started > 45:
            raise AuxiliaryUnavailable('의미 검색 준비 시간이 초과되었습니다. 잠시 후 다시 실행하세요.')
        batches.append(_catalog_batch(tuple(documents[i:i + 64]), model, key))
    catalog = np.concatenate(batches)
    if queries.shape[1] != catalog.shape[1]:
        raise AuxiliaryUnavailable('임베딩 차원이 일치하지 않습니다. 모델 설정을 확인하세요.')
    queries /= np.maximum(np.linalg.norm(queries, axis=1, keepdims=True), 1e-12)
    catalog_norm = catalog / np.maximum(np.linalg.norm(catalog, axis=1, keepdims=True), 1e-12)
    scores = (queries @ catalog_norm.T).max(axis=0)
    order = np.argsort(-scores, kind='stable')[:limit]
    return [{'kwd_no': str(records[i]['kwd_no']), 'keyword': str(records[i]['키워드명']),
             'similarity': round(float(scores[i]), 4)} for i in order]


def analyze_auxiliary(text, keywords, *, categories=(), risks=(), kiwi=True,
                      embeddings=False, limit=10):
    if not text.strip() or len(text) > 20000 or not 1 <= limit <= 20:
        raise ValueError('텍스트는 1~20,000자, 후보 수는 1~20개여야 합니다.')
    selected = keywords
    for column, values in (('상품카테고리', categories), ('리스크 등급', risks)):
        if values:
            selected = selected.loc[selected[column].astype(str).str.strip().isin(values)]
    records = selected.fillna('').to_dict('records')
    result = {'kiwi': {'status': 'disabled', 'candidates': []},
              'embeddings': {'status': 'disabled', 'candidates': []}}
    for name, enabled, analyze in (('kiwi', kiwi, morphology_candidates),
                                  ('embeddings', embeddings, semantic_candidates)):
        if enabled:
            try:
                result[name] = {'status': 'ok', 'candidates': analyze(text, records, limit) if records else []}
            except AuxiliaryUnavailable as exc:
                result[name] = {'status': 'unavailable', 'candidates': [], 'message': str(exc)}
    return result
