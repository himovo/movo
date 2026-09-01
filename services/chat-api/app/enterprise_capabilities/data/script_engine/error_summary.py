"""Compact execution errors without losing the actionable exception tail."""

from __future__ import annotations


def execution_error_summary(error: BaseException, *, max_chars: int = 1000) -> str:
    text = str(error).strip() or type(error).__name__
    if len(text) <= max_chars:
        return text
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    tail = "\n".join(lines[-3:])
    available = max(80, max_chars - len(tail) - 18)
    return f"{text[:available]}\n… [truncated] …\n{tail}"[-max_chars:]


__all__ = ["execution_error_summary"]
