"""Split oversized source text without dropping characters."""

from __future__ import annotations

from collections.abc import Callable


def split_with_repeated_heading(
    text: str, *, max_tokens: int, count_tokens: Callable[[str], int],
) -> list[str]:
    if count_tokens(text) <= max_tokens:
        return [text]
    heading, separator, body = text.partition("\n")
    prefix = f"{heading}\n" if separator and count_tokens(heading) < max_tokens // 3 else ""
    remaining = body if prefix else text
    windows: list[str] = []
    while remaining:
        low, high = 1, len(remaining)
        fit = 0
        while low <= high:
            middle = (low + high) // 2
            if count_tokens(prefix + remaining[:middle]) <= max_tokens:
                fit = middle
                low = middle + 1
            else:
                high = middle - 1
        if fit == 0:
            raise ValueError("chunk token budget cannot hold one character")
        windows.append(prefix + remaining[:fit])
        remaining = remaining[fit:]
    return windows


__all__ = ["split_with_repeated_heading"]
