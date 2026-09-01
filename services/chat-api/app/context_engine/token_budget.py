from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List

from app.context_engine.types import ContextBlock, RenderedBlock


MODEL_CONTEXT_WINDOWS = {
    "gpt-5.2": 400000,
    "gpt-5.2-chat": 400000,
    "gpt-5.3-codex": 400000,
    "gpt-4o": 128000,
    "gpt-4.1": 1047576,
    "qwen-plus": 128000,
}


def estimate_tokens(text: str) -> int:
    """Fast conservative token estimate without requiring tiktoken."""
    raw = str(text or "")
    if not raw:
        return 0
    cjk = len(re.findall(r"[\u4e00-\u9fff]", raw))
    non_cjk_chars = max(0, len(raw) - cjk)
    # Chinese tokens are often close to 1 char/token. English/code averages
    # closer to 3.5-4 chars/token. Use a conservative mixed estimate.
    return max(1, int(math.ceil(cjk * 1.1 + non_cjk_chars / 3.5)))


def truncate_to_tokens(text: str, max_tokens: int) -> str:
    raw = str(text or "")
    if max_tokens <= 0 or not raw:
        return ""
    if estimate_tokens(raw) <= max_tokens:
        return raw
    # Convert token budget back to a conservative char budget. Keep this simple
    # and deterministic; the builder re-checks after truncation.
    char_budget = max(120, int(max_tokens * 2.8))
    if len(raw) <= char_budget:
        return raw
    return raw[:char_budget].rstrip() + "\n...[truncated by context budget]"


def model_context_window(model_name: str) -> int:
    model = str(model_name or "").strip().lower()
    if not model:
        return 128000
    for key, size in MODEL_CONTEXT_WINDOWS.items():
        if key in model:
            return size
    if "codex" in model or "gpt-5" in model:
        return 400000
    if "qwen" in model:
        return 128000
    return 128000


@dataclass
class ContextBudgeter:
    default_context_window: int = 128000
    response_reserve_ratio: float = 0.20
    hard_cap_tokens: int = 90000

    def resolve_budget(self, output_spec: Dict[str, Any]) -> int:
        explicit = output_spec.get("context_token_budget") or output_spec.get("max_context_tokens")
        try:
            if explicit:
                return max(4000, int(explicit))
        except Exception:
            pass
        model = str(output_spec.get("model") or output_spec.get("model_name") or "").strip()
        window = model_context_window(model) if model else self.default_context_window
        usable = int(window * (1.0 - self.response_reserve_ratio))
        return max(4000, min(usable, self.hard_cap_tokens))

    def allocate(self, blocks: Iterable[ContextBlock], *, total_budget: int) -> List[RenderedBlock]:
        remaining = max(1, int(total_budget or 1))
        rendered: List[RenderedBlock] = []
        ordered = sorted(list(blocks or []), key=lambda b: (not b.required, -int(b.priority)))
        for block in ordered:
            raw = str(block.content or "").strip()
            if not raw:
                rendered.append(RenderedBlock(block=block, content="", estimated_tokens=0, included=False, reason="empty"))
                continue
            requested = max(1, int(block.token_budget or remaining))
            allowance = min(requested, remaining)
            if allowance <= 0 and not block.required:
                rendered.append(RenderedBlock(block=block, content="", estimated_tokens=0, included=False, reason="budget_exhausted"))
                continue
            if allowance <= 0:
                allowance = min(256, requested)
            content = truncate_to_tokens(raw, allowance)
            used = estimate_tokens(content)
            remaining -= used
            rendered.append(
                RenderedBlock(
                    block=block,
                    content=content,
                    estimated_tokens=used,
                    included=bool(content),
                    reason="included" if content else "empty_after_truncation",
                )
            )
        return rendered

    def render_metadata(self, rendered: List[RenderedBlock], total_budget: int) -> Dict[str, Any]:
        included = [r for r in rendered if r.included]
        used = sum(int(r.estimated_tokens or 0) for r in included)
        return {
            "token_budget": int(total_budget or 0),
            "estimated_tokens": int(used),
            "remaining_tokens": max(0, int(total_budget or 0) - int(used)),
            "included_blocks": [r.block.block_type.value for r in included],
            "dropped_blocks": [
                {"type": r.block.block_type.value, "reason": r.reason}
                for r in rendered
                if not r.included
            ],
        }
