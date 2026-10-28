"""Direct Law.go.kr Open API adapter used by regulation_assistant."""
from __future__ import annotations

import os
from typing import Any

import requests


SEARCH_URL = "https://www.law.go.kr/DRF/lawSearch.do"
SERVICE_URL = "https://www.law.go.kr/DRF/lawService.do"
DEFAULT_REFERER = "https://www.law.go.kr/"


class LegislationApiError(RuntimeError):
    pass


def _api_key() -> str:
    key = os.getenv("LEGISLATION_API_KEY", "").strip()
    if not key:
        raise LegislationApiError("LEGISLATION_API_KEY is not configured")
    return key


def _fetch(service: str, target: str, arguments: dict[str, Any]) -> dict[str, Any]:
    endpoint = SEARCH_URL if service == "search" else SERVICE_URL
    params = {"OC": _api_key(), "target": target, "type": "JSON", **arguments}
    referer = os.getenv("LEGISLATION_REFERER", DEFAULT_REFERER).strip() or DEFAULT_REFERER
    try:
        response = requests.get(
            endpoint, params=params, headers={"Referer": referer}, timeout=(5, 30)
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise LegislationApiError(
            f"Law.go.kr {target} request failed ({type(exc).__name__})"
        ) from exc
    if not isinstance(payload, dict):
        raise LegislationApiError(f"Law.go.kr {target} returned an unexpected response")
    error = _find_error(payload)
    if error:
        raise LegislationApiError(f"Law.go.kr {target} returned an error: {error}")
    return payload


def _find_error(value: Any) -> str | None:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).casefold() in {"errmsg", "error", "errormessage"} and item:
                return str(item)[:300]
            if str(key).casefold() in {"resultcode", "errcode", "errorcode"}:
                if str(item).strip() not in {"", "0", "00", "200", "success"}:
                    return str(item)[:300]
            found = _find_error(item)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _find_error(item)
            if found:
                return found
    return None


def _flatten(value: Any, prefix: str = "") -> list[str]:
    lines: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            # The API credential must never be included in user-visible source text.
            if str(key).casefold() == "oc":
                continue
            lines.extend(_flatten(item, f"{prefix}{key}: "))
    elif isinstance(value, list):
        for item in value:
            lines.extend(_flatten(item, prefix))
    elif value is not None and str(value).strip():
        lines.append(f"{prefix}{value}")
    return lines


def _article_lines(value: Any, prefix: str = "") -> list[str]:
    """Keep actual provision text for DB matching; omit law metadata and links."""
    text_fields = {"조문내용", "항내용", "호내용", "목내용", "전문", "본문내용"}
    lines: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key)
            if key_text.casefold() == "oc":
                continue
            if key_text in text_fields and isinstance(item, (str, int, float)) and str(item).strip():
                lines.append(f"{prefix}{key_text}: {item}")
            else:
                lines.extend(_article_lines(item, prefix))
    elif isinstance(value, list):
        for item in value:
            lines.extend(_article_lines(item, prefix))
    return lines


def _article_metadata(value: Any) -> list[str]:
    fields = {"법령명한글", "법령명_한글", "시행일자", "공포일자", "법령상세링크",
              "법령상세링크주소", "법령ID", "MST", "법령일련번호"}
    lines: list[str] = []

    def collect(item: Any) -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                if str(key).casefold() == "oc":
                    continue
                if str(key) in fields and isinstance(child, (str, int, float)) and str(child).strip():
                    lines.append(f"{key}: {child}")
                else:
                    collect(child)
        elif isinstance(item, list):
            for child in item:
                collect(child)

    collect(value)
    return lines


def _render(payload: dict[str, Any], *, articles_only: bool = False) -> str:
    if articles_only:
        body = _article_lines(payload)
        lines = [*_article_metadata(payload), "조문 내용:", *body]
    else:
        lines = _flatten(payload)
    if not lines:
        lines = _flatten(payload)
    return "\n".join(lines)[:12000]


def _article_code(article_no: str) -> str:
    """Convert a displayed article number (for example 10 or 10의2) to JO."""
    import re

    match = re.fullmatch(r"\s*(\d+)(?:\s*의\s*(\d+))?\s*", article_no)
    if not match:
        raise LegislationApiError("Unsupported article number format")
    main, sub = int(match.group(1)), int(match.group(2) or 0)
    if main > 9999 or sub > 99:
        raise LegislationApiError("Article number is outside the supported range")
    return f"{main:04d}{sub:02d}"


def search_many(calls: list[tuple[str, dict[str, Any]]]) -> list[str]:
    """Run supported evidence searches through the Law.go.kr Open API."""
    targets = {
        "search_law": "law",
        "search_administrative_rule": "admrul",
        "search_precedent": "prec",
    }
    allowed = {*targets, "search_law_articles"}
    if any(tool not in allowed for tool, _ in calls):
        raise LegislationApiError("Unsupported legislation search operation")

    outputs = []
    for tool, arguments in calls:
        if tool in targets:
            params = {
                "query": str(arguments.get("query", ""))[:200],
                "search": int(arguments.get("search", 2)),
                "display": min(max(int(arguments.get("display", 5)), 1), 100),
                "page": 1,
            }
            payload = _fetch("search", targets[tool], params)
            outputs.append(_render(payload))
            continue

        mst = str(arguments.get("mst", "")).strip()
        if not mst.isdigit():
            raise LegislationApiError("A valid law master number is required")
        article_no = str(arguments.get("article_no", "")).strip()
        if article_no:
            target = "lawjosub"
            params = {"MST": mst, "JO": _article_code(article_no)}
        else:
            target = "law"
            params = {"MST": mst}
        payload = _fetch("service", target, params)
        outputs.append(_render(payload, articles_only=True))
    return outputs
