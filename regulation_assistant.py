"""Evidence-first regulation lookup and explanation orchestration."""
from __future__ import annotations

import json
import os
import re
from typing import Any

import pandas as pd
import requests
from legislation_source import LegislationApiError, search_many as _law_api_search_many
from regulation_corpus import search_documents
from auxiliary_analysis import AuxiliaryUnavailable, semantic_candidates


class RegulationSearchError(RuntimeError):
    pass


def _search_legislation_many(calls: list[tuple[str, dict[str, Any]]]) -> list[str]:
    try:
        return _law_api_search_many(calls)
    except LegislationApiError as exc:
        raise RegulationSearchError(str(exc)) from exc
    except Exception as exc:
        raise RegulationSearchError(
            f"Legislation search failed ({type(exc).__name__})"
        ) from exc


def _search_legislation(tool: str, arguments: dict[str, Any]) -> str:
    return _search_legislation_many([(tool, arguments)])[0]


def _source(source_id: str, label: str, text: str) -> dict[str, str]:
    match = re.search(r"https?://[^\s)]+", text)
    return {"id": source_id, "label": label, "text": text,
            "url": match.group(0).rstrip(".,") if match else ""}


def _db_source(keywords: pd.DataFrame, query: str, category: str) -> dict[str, Any]:
    source = keywords.copy()
    if category and "상품카테고리" in source:
        source = source[source["상품카테고리"].astype(str).str.strip() == category]
    tokens = list(dict.fromkeys(re.findall(r"[가-힣A-Za-z0-9]{2,}", query)))[:30]
    stop = {"관련", "법령", "조항", "찾아", "알려", "해주세요", "키워드", "광고", "문구"}
    tokens = [token for token in tokens if token not in stop]
    if not tokens or source.empty or "키워드명" not in source:
        return {"matches": [], "source": None}
    mask = source["키워드명"].fillna("").astype(str).map(
        lambda term: any(token.casefold() in term.casefold() or term.casefold() in token.casefold()
                         for token in tokens if len(token) >= 2))
    rows = source.loc[mask].head(20)
    matches = []
    for row in rows.to_dict("records"):
        matches.append({key: str(row.get(key, "") or "") for key in
                        ("kwd_no", "키워드명", "상품카테고리", "리스크 등급",
                         "대체키워드", "리스크 등급별 세부 심의기준")})
    if not matches:
        return {"matches": [], "source": None}
    evidence = "\n".join(json.dumps(row, ensure_ascii=False) for row in matches)
    return {"matches": matches, "source": _source("DB1", "현재 키워드 DB", evidence)}


def _llm_explanation(question: str, sources: list[dict[str, str]], conversation_history: list[dict[str, str]] | None = None) -> dict[str, Any] | None:
    if os.getenv("REGULATION_LLM_ENABLED", "false").lower() != "true":
        return None
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    model = os.getenv("REGULATION_LLM_MODEL", "").strip()
    if not api_key or not model:
        return None

    source_ids = {source["id"] for source in sources}
    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": (
                    "검색 도구 결과만 근거로 한국어 답변을 작성하라. 검색 결과에 없는 사실·법령·판례를 만들지 말라. "
                    "DB 내부 등급은 법률 판단과 구분하라. 근거가 서로 상충하거나 충분하지 않으면 status를 conflict "
                    "또는 insufficient로 하고, administrator_review를 true로 하라. 각 주장에 source_id와 원문에 실제 "
                    "포함된 짧은 quote를 붙여라. JSON 형식: {status, answer, administrator_review, claims:[{text,source_id,quote}]}"
                )},
                *[{"role": item["role"], "content": item["content"]} for item in (conversation_history or [])[-12:]],
                {"role": "user", "content": json.dumps(
                    {"question": question, "sources": sources}, ensure_ascii=False)},
            ],
        }, timeout=45,
    )
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    result = json.loads(content)
    claims = result.get("claims") or []
    source_by_id = {source["id"]: source["text"] for source in sources}
    citations_valid = bool(claims) and all(
        claim.get("source_id") in source_ids
        and bool(claim.get("quote"))
        and claim.get("quote", "") in source_by_id.get(claim.get("source_id"), "")
        for claim in claims
    )
    if (result.get("status") != "supported" or result.get("administrator_review")
            or not citations_valid):
        return {"status": "conflict", "administrator_review": True,
                "answer": "검색 자료 사이의 관계를 명확히 확정하지 못했습니다. 아래 자료와 차이를 그대로 표시합니다. "
                          "이 결과만으로 적법 여부를 판단하지 말고 세부 판단은 관리자에게 문의해 주세요."}
    citations = ', '.join(f"[{claim['source_id']}]" for claim in claims)
    return {"status": "supported", "administrator_review": False,
            "answer": str(result.get("answer", ""))[:3800] + f"\n\n근거: {citations}"}


def answer_regulation_question(request: dict[str, Any], repository) -> dict[str, Any]:
    if request.get('scope', 'legacy') != 'legacy':
        return _answer_scoped_question(request, repository)
    direction = request["direction"]
    query = request["query"].strip()
    context = request.get("context_text", "")[:20000]
    category = request.get("category", "")
    conversation_history = request.get("conversation_history", [])[-12:]
    prior_context = "\n".join(item["content"] for item in conversation_history)
    retrieval_context = "\n".join(part for part in (query, prior_context, context) if part)
    keywords = repository.load_keywords()
    db_result = (_db_source(keywords, retrieval_context, category)
                 if direction == "keyword_to_law" else {"matches": [], "source": None})
    sources = [db_result["source"]] if db_result["source"] else []
    matches = db_result["matches"]
    tool_calls: list[dict[str, Any]] = []

    if direction == "keyword_to_law":
        # Law.go.kr is queried only after the user submits a question.
        stop_terms = {"관련", "법령", "조문", "판례", "찾아", "알려", "해주세요",
                      "해줘", "이내용", "이문구", "광고", "문구", "내용", "대해서",
                      "무엇", "어떤", "저촉", "위반", "기준", "현재"}
        terms = [term for term in dict.fromkeys(
            re.findall(r"[가-힣A-Za-z0-9]{2,}", f"{query}\n{context}"))
                 if term not in stop_terms][:3]
        if not terms:
            terms = [query[:80]]
        calls = []
        labels = []
        for index, term in enumerate(terms, 1):
            for tool, label in (("search_law", "법령"),
                                ("search_administrative_rule", "행정규칙"),
                                ("search_precedent", "판례")):
                calls.append((tool, {"query": term, "search": 2, "display": 5}))
                labels.append((tool, term, index, label))
        for (tool, term, sequence, label), text in zip(labels, _search_legislation_many(calls)):
            tool_calls.append({"tool": tool, "query": term})
            if text.strip():
                source_prefix = {"법령": "LAW", "행정규칙": "RULE", "판례": "CASE"}[label]
                sources.append(_source(f"{source_prefix}{sequence}", f"{label} 검색: {term}", text))
        if not any(source["id"].startswith(("LAW", "CASE")) for source in sources):
            raise RegulationSearchError("Law.go.kr returned no law or precedent search results")
    elif direction == "law_to_keywords":
        law_match = re.search(r"(.+?(?:법률|법|령|규칙))\s*(?:제\s*(\d+(?:의\d+)?)\s*조)?", query)
        if not law_match:
            raise RegulationSearchError("법령명과 조항을 함께 입력해 주세요. 예: 화장품법 제13조")
        law_name = law_match.group(1).strip()
        article_no = law_match.group(2)
        law_text = _search_legislation("search_law", {"query": law_name, "search": 1, "display": 5})
        tool_calls.append({"tool": "search_law", "query": law_name})
        mst_match = re.search(r"(?:MST|법령일련번호)\s*[:：=]?\s*(\d{5,})", law_text, re.I)
        if not mst_match:
            sources.append(_source("LAW1", f"법령 검색: {law_name}", law_text))
            return {"status": "insufficient", "administrator_review": False,
                    "answer": "법령명은 검색했지만 상세 조문을 특정하지 못했습니다. 검색 결과에서 법령을 확인한 뒤 "
                              "정확한 법령명과 조항을 입력해 주세요.",
                    "sources": sources, "keyword_matches": [], "tool_calls": tool_calls,
                    "llm_used": False}
        args: dict[str, Any] = {"mst": mst_match.group(1), "include_content": True, "display": 100}
        if article_no:
            args["article_no"] = article_no
        article_text = _search_legislation("search_law_articles", args)
        tool_calls.append({"tool": "search_law_articles", "law": law_name, "article": article_no or "all"})
        article_body = article_text
        for marker in ("**조문 내용:**", "조문 내용:"):
            if marker in article_body:
                article_body = article_body.split(marker, 1)[1]
                break
        sources.append(_source("LAW1", f"{law_name}{' 제' + article_no + '조' if article_no else ' 조문'}", article_text))
        try:
            from matching_engine import MatchingConfig, find_matches_nlp
            article_keywords = keywords
            if category and "상품카테고리" in article_keywords:
                article_keywords = article_keywords[
                    article_keywords["상품카테고리"].astype(str).str.strip() == category]
            exact = find_matches_nlp(article_body, article_keywords,
                                     config=MatchingConfig(mode="exact"))
            seen: set[str] = set()
            for hit in exact:
                term = str(hit.term)
                if term not in seen:
                    matches.append({"kwd_no": hit.kwd_no or "", "키워드명": term,
                                    "상품카테고리": hit.category, "리스크 등급": hit.risk,
                                    "대체키워드": "", "리스크 등급별 세부 심의기준": hit.detail})
                    seen.add(term)
        except Exception as exc:
            raise RegulationSearchError("키워드 DB와 조문 비교 중 오류가 발생했습니다") from exc
    else:
        raise RegulationSearchError("Unsupported question direction")

    if matches and not db_result["source"]:
        evidence = "\n".join(json.dumps(row, ensure_ascii=False) for row in matches)
        sources.insert(0, _source("DB1", "현재 키워드 DB", evidence))
    llm_question = query + (f"\n\n사용자가 제공한 분석 문구:\n{context}" if context else "")
    try:
        llm_sources = [{**source, "text": source["text"][:3000]} for source in sources[:6]]
        llm = (_llm_explanation(llm_question, llm_sources, conversation_history)
               if request.get('use_llm', True) else None)
    except (requests.RequestException, ValueError, KeyError):
        # Retrieval remains useful when the optional explanation service is unavailable.
        llm = None
    if llm:
        answer = llm["answer"]
        status = llm["status"]
        needs_admin = llm["administrator_review"]
    elif direction == "law_to_keywords":
        answer = (f"조회한 조문에서 현재 DB 키워드 {len(matches)}개가 직접 일치했습니다."
                  if matches else "조회한 조문 원문에서 현재 DB 키워드가 직접 일치하지 않았습니다."
                  " 의미상 관련된 키워드까지 찾은 결과는 아닙니다.")
        status, needs_admin = "retrieved", False
    else:
        answer = (f"현재 DB에서 관련 후보 {len(matches)}개를 찾았습니다. 아래 법령·판례 검색 결과를 "
                  "근거 자료로 확인해 주세요. 검색 결과만으로 적법 여부를 판단하지 않습니다.")
        status, needs_admin = "retrieved", False
    return {"status": status, "administrator_review": needs_admin,
            "answer": answer, "sources": sources,
            "keyword_matches": matches[:50], "tool_calls": tool_calls,
            "llm_used": bool(llm)}


def _answer_scoped_question(request: dict[str, Any], repository) -> dict[str, Any]:
    scope = request['scope']
    query = request['query'].strip()
    category = request.get('category', '')
    context = request.get('context_text', '')[:20000]
    sources: list[dict[str, Any]] = []
    matches: list[dict[str, Any]] = []
    related_candidates: list[dict[str, Any]] = []
    tool_calls: list[dict[str, Any]] = []
    search_methods: list[str] = []
    warnings: list[str] = []
    law_to_keywords = request['direction'] == 'law_to_keywords'

    if law_to_keywords and scope in {'internal', 'keyword'}:
        return {'status': 'insufficient', 'administrator_review': False,
                'answer': '법령 조문에서 등록 키워드를 찾으려면 국가법령정보센터 또는 통합 검색 범위를 선택해 주세요.',
                'sources': [], 'keyword_matches': [], 'related_candidates': [],
                'tool_calls': [], 'search_methods': [], 'llm_used': False}
    if law_to_keywords:
        legacy = answer_regulation_question({**request, 'scope': 'legacy', 'use_llm': False}, repository)
        sources.extend(legacy['sources'])
        matches.extend(legacy['keyword_matches'])
        tool_calls.extend(legacy['tool_calls'])
        if request.get('include_keyword_candidates'):
            if os.getenv('REGULATION_EMBEDDINGS_ENABLED', 'false').lower() != 'true':
                warnings.append('키워드 의미 관련 후보는 서버 임베딩 설정 후 사용할 수 있습니다.')
            else:
                records = repository.load_keywords().fillna('').to_dict('records')
                if category:
                    records = [row for row in records if row.get('상품카테고리') == category]
                try:
                    related_candidates = (semantic_candidates(sources[-1]['text'][:2000], records, 10)
                                          if records else [])
                except (AuxiliaryUnavailable, ValueError) as exc:
                    warnings.append(f'키워드 의미 관련 후보를 만들지 못했습니다: {exc}')

    if scope in {'keyword', 'all'} and not law_to_keywords:
        keywords = repository.load_keywords()
        db_result = _db_source(keywords, f'{query}\n{context}', category)
        matches = db_result['matches']
        if db_result['source']:
            sources.append(db_result['source'])
        tool_calls.append({'tool': 'keyword_db', 'query': query})
        if request.get('include_keyword_candidates'):
            if os.getenv('REGULATION_EMBEDDINGS_ENABLED', 'false').lower() != 'true':
                warnings.append('키워드 의미 관련 후보는 서버 임베딩 설정 후 사용할 수 있습니다.')
            else:
                records = keywords.fillna('').to_dict('records')
                if category:
                    records = [row for row in records if row.get('상품카테고리') == category]
                try:
                    related_candidates = (semantic_candidates((context or query)[:2000], records, 10)
                                          if records else [])
                except (AuxiliaryUnavailable, ValueError) as exc:
                    warnings.append(f'키워드 의미 관련 후보를 만들지 못했습니다: {exc}')

    if scope in {'internal', 'all'}:
        rows, method = search_documents(repository, f'{query}\n{context}'[:2000],
                                        category, request['as_of'])
        search_methods.append(method)
        if method == 'lexical_fuzzy_embedding_unavailable':
            warnings.append('의미 검색 서버 응답에 문제가 있어 사내문서는 단어·유사 문자열로 검색했습니다.')
        for index, row in enumerate(rows, 1):
            sources.append({'id': f'INT{index}',
                'label': f"사내 지침: {row['title']} v{row['version']} · {row['ordinal']}번 문단",
                'text': row['content'], 'url': '',
                'document_id': row['document_id'], 'chunk_id': row['chunk_id'],
                'version': row['version'], 'content_sha256': row['content_sha256']})
        tool_calls.append({'tool': 'internal_guidance', 'query': query, 'method': method})

    if scope in {'law', 'all'} and not law_to_keywords:
        terms = [term for term in dict.fromkeys(re.findall(r'[가-힣A-Za-z0-9]{2,}', query))
                 if term not in {'법령', '근거', '광고', '문구', '관련', '알려주세요'}][:2]
        if not terms:
            terms = [query[:80]]
        calls = [(tool, {'query': term, 'search': 2, 'display': 5})
                 for term in terms for tool in ('search_law', 'search_administrative_rule')]
        try:
            results = _search_legislation_many(calls)
            for index, ((tool, args), result) in enumerate(zip(calls, results), 1):
                if result.strip():
                    label = '법령' if tool == 'search_law' else '행정규칙'
                    sources.append(_source(f'LAW{index}', f'{label} 검색: {args["query"]}', result))
                tool_calls.append({'tool': tool, 'query': args['query']})
        except RegulationSearchError:
            if scope == 'law':
                raise
            warnings.append('국가법령정보센터 조회에 실패했습니다. 현재 답변에는 해당 근거가 없습니다.')

    if not sources:
        answer = '선택한 범위에서 확인 가능한 근거를 찾지 못했습니다. 검색어, 상품 카테고리, 기준일을 확인해 주세요.'
        status, needs_admin, llm_used = 'insufficient', False, False
    else:
        llm = None
        if request.get('use_llm'):
            if (os.getenv('REGULATION_LLM_ENABLED', 'false').lower() != 'true'
                    or not os.getenv('OPENAI_API_KEY') or not os.getenv('REGULATION_LLM_MODEL')):
                warnings.append('LLM 요약이 서버에 설정되지 않아 검색 결과만 표시합니다.')
            else:
                try:
                    selected = [source for prefix in ('LAW', 'INT', 'DB')
                                for source in [item for item in sources
                                               if item['id'].startswith(prefix)][:2]]
                    llm_sources = [{**source, 'text': source['text'][:3000]} for source in selected]
                    llm = _llm_explanation(query + ('\n' + context if context else ''),
                                           llm_sources, request.get('conversation_history', []))
                except (requests.RequestException, ValueError, KeyError):
                    warnings.append('LLM 설명을 생성하지 못했습니다. 검색 근거를 직접 확인해 주세요.')
        if llm:
            answer, status, needs_admin = llm['answer'], llm['status'], llm['administrator_review']
            llm_used = True
        else:
            citations = ', '.join(f"[{source['id']}] {source['label']}" for source in sources[:5])
            lead = (legacy['answer'] if law_to_keywords else
                    f'관련 근거 {len(sources)}건을 찾았습니다. 아래 출처의 원문과 적용 시점을 확인해 주세요.')
            answer = f'{lead}\n\n{citations}'
            status, needs_admin, llm_used = 'retrieved', False, False
    if warnings:
        answer += '\n\n' + '\n'.join(warnings)
    return {'status': status, 'administrator_review': needs_admin,
            'answer': answer, 'sources': sources[:10], 'keyword_matches': matches[:50],
            'related_candidates': related_candidates,
            'tool_calls': tool_calls, 'search_methods': search_methods,
            'llm_used': llm_used, 'warnings': warnings}
