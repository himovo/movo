from __future__ import annotations

import re
from typing import Any, Tuple


def parse_css_padding(value: Any) -> Tuple[float, float, float, float]:
    """Return CSS padding as (top, right, bottom, left) pixels."""
    if value in (None, ""):
        return 0.0, 0.0, 0.0, 0.0
    if isinstance(value, (int, float)):
        number = max(0.0, float(value))
        return number, number, number, number
    parts = [part for part in re.split(r"\s+", str(value).strip()) if part]
    numbers = [_css_number(part) for part in parts[:4]]
    if not numbers:
        return 0.0, 0.0, 0.0, 0.0
    if len(numbers) == 1:
        return (numbers[0],) * 4
    if len(numbers) == 2:
        return numbers[0], numbers[1], numbers[0], numbers[1]
    if len(numbers) == 3:
        return numbers[0], numbers[1], numbers[2], numbers[1]
    return numbers[0], numbers[1], numbers[2], numbers[3]


def _css_number(value: Any) -> float:
    match = re.search(r"-?\d+(?:\.\d+)?", str(value or ""))
    return max(0.0, float(match.group(0))) if match else 0.0


__all__ = ["parse_css_padding"]
