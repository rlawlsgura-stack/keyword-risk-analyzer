"""Token-based usage estimates for OpenAI calls made by the regulation chat."""
from __future__ import annotations

import os
import logging
import re
from decimal import Decimal, InvalidOperation
from datetime import datetime
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# Standard OpenAI text-token prices, USD per 1M tokens, reviewed 2026-11-15.
_MODEL_PRICES = {
    "gpt-4.1-mini": ("0.40", "1.60", "0.10"),
    "gpt-6-luna": ("0.10", "0.50", "0.01"),
    "gpt-6.1-terra": ("1.00", "5.00", "0.05"),
    "gpt-6.1-sol": ("2.00", "10.00", "0.10"),
    "gpt-6-astra": ("10.00", "50.00", "1.00"),
}


def _price(name: str) -> Decimal | None:
    value = os.getenv(name, "").strip()
    if not value:
        return None
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        return None
    return parsed if parsed >= 0 else None


def _model_rate(model: str, component: str, legacy_setting: str,
                default_rate: str | None) -> Decimal | None:
    model_key = re.sub(r"[^A-Z0-9]+", "_", model.upper()).strip("_")
    specific = _price(f"REGULATION_LLM_MODEL_{model_key}_{component}_USD_PER_1M")
    if specific is not None:
        return specific
    if model == os.getenv("REGULATION_LLM_MODEL", "").strip():
        configured = _price(legacy_setting)
        if configured is not None:
            return configured
    return Decimal(default_rate) if default_rate is not None else None


def usage_event(model: str, usage: dict, *, embedding: bool = False) -> dict:
    """Normalize OpenAI usage metadata and estimate token charges when rates exist."""
    input_tokens = int(usage.get("input_tokens", usage.get("prompt_tokens", 0)) or 0)
    output_tokens = int(usage.get("output_tokens", usage.get("completion_tokens", 0)) or 0)
    details = usage.get("input_tokens_details") or usage.get("prompt_tokens_details") or {}
    cached_tokens = min(input_tokens, int(details.get("cached_tokens", 0) or 0))

    if embedding:
        input_rate = _price("OPENAI_EMBEDDING_INPUT_USD_PER_1M")
        output_rate = Decimal(0)
        cached_rate = input_rate
    else:
        defaults = _MODEL_PRICES.get(model, (None, None, None))
        input_rate = _model_rate(model, "INPUT", "REGULATION_LLM_INPUT_USD_PER_1M", defaults[0])
        output_rate = _model_rate(model, "OUTPUT", "REGULATION_LLM_OUTPUT_USD_PER_1M", defaults[1])
        cached_rate = _model_rate(model, "CACHED_INPUT", "REGULATION_LLM_CACHED_INPUT_USD_PER_1M", defaults[2])
        if cached_rate is None:
            cached_rate = input_rate

    estimated_cost = None
    if input_rate is not None and output_rate is not None and cached_rate is not None:
        billable_input = input_tokens - cached_tokens
        estimated_cost = (
            Decimal(billable_input) * input_rate
            + Decimal(cached_tokens) * cached_rate
            + Decimal(output_tokens) * output_rate
        ) / Decimal(1_000_000)

    return {
        "model": model,
        "request_count": 1,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cached_input_tokens": cached_tokens,
        "estimated_cost_usd": str(estimated_cost) if estimated_cost is not None else None,
        "cost_complete": estimated_cost is not None,
    }


def monthly_budget() -> Decimal | None:
    return _price("REGULATION_CHAT_MONTHLY_BUDGET_USD")


def current_month_start() -> str:
    return datetime.now(ZoneInfo("Asia/Seoul")).date().replace(day=1).isoformat()


def record_usage(repository, event: dict | None) -> bool:
    if not event:
        return True
    try:
        repository.record_openai_usage(current_month_start(), event)
        return True
    except Exception:
        logger.exception("OpenAI usage could not be stored")
        return False
