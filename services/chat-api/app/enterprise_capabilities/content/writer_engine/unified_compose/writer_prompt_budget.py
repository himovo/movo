from __future__ import annotations

from dataclasses import dataclass

from app.context_engine.token_budget import estimate_tokens


FINAL_WRITER_INPUT_TOKEN_CAP = 90000
MIN_USER_PROMPT_TOKENS = 4000
_TRUNCATION_MARKER = "\n...[truncated by final writer input budget]"
_FENCE_CLOSER = "\n```"


@dataclass(frozen=True)
class WriterPromptBudgetResult:
    system: str
    user: str
    estimated_tokens: int
    truncated: bool


def _truncate_exact(text: str, max_tokens: int) -> str:
    raw = str(text or "")
    if not raw or max_tokens <= 0:
        return ""
    if estimate_tokens(raw) <= max_tokens:
        return raw

    reserved_tokens = estimate_tokens(_TRUNCATION_MARKER + _FENCE_CLOSER)
    content_budget = max(0, max_tokens - reserved_tokens)
    low, high = 0, len(raw)
    while low < high:
        mid = (low + high + 1) // 2
        if estimate_tokens(raw[:mid]) <= content_budget:
            low = mid
        else:
            high = mid - 1
    prefix = raw[:low].rstrip()
    suffix = _TRUNCATION_MARKER
    if prefix.count("```") % 2:
        suffix += _FENCE_CLOSER
    return prefix + suffix


def fit_writer_prompt(
    *,
    system: str,
    user: str,
    max_total_tokens: int = FINAL_WRITER_INPUT_TOKEN_CAP,
) -> WriterPromptBudgetResult:
    """Bound final writer input while preserving system rules before evidence tail."""

    system_text = str(system or "").strip()
    user_text = str(user or "").strip()
    cap = max(8000, int(max_total_tokens or FINAL_WRITER_INPUT_TOKEN_CAP))
    original_system = system_text
    original_user = user_text

    system_text = _truncate_exact(system_text, max(1000, cap - MIN_USER_PROMPT_TOKENS))
    user_text = _truncate_exact(user_text, max(1, cap - estimate_tokens(system_text)))
    total = estimate_tokens(system_text) + estimate_tokens(user_text)
    return WriterPromptBudgetResult(
        system=system_text,
        user=user_text,
        estimated_tokens=total,
        truncated=system_text != original_system or user_text != original_user,
    )
