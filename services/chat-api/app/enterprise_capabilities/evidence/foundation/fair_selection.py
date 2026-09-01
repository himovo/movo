from __future__ import annotations

from typing import List, Sequence, TypeVar


T = TypeVar("T")


def round_robin_take(groups: Sequence[Sequence[T]], *, limit: int) -> List[T]:
    """Take items across source groups without letting early sources monopolize capacity."""

    active = [list(group) for group in groups if group]
    out: List[T] = []
    index = 0
    while active and len(out) < max(0, limit):
        next_active: List[List[T]] = []
        for group in active:
            if index < len(group):
                out.append(group[index])
                if len(out) >= limit:
                    break
            if index + 1 < len(group):
                next_active.append(group)
        active = next_active
        index += 1
    return out
