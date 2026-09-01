from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from typing import Dict, Iterator, List


@dataclass
class DecisionTurnChannel:
    """Request-local bridge from LLM decision turns to the V3 event stream."""

    locale: str = ""
    pending: List[Dict[str, str]] = field(default_factory=list)

    def publish(self, payload: Dict[str, str]) -> None:
        self.pending.append(dict(payload))

    def drain(self) -> List[Dict[str, str]]:
        drained = list(self.pending)
        self.pending.clear()
        return drained


_CHANNEL: ContextVar[DecisionTurnChannel | None] = ContextVar(
    "decision_turn_channel",
    default=None,
)


def current_decision_turn_channel() -> DecisionTurnChannel | None:
    return _CHANNEL.get()


@contextmanager
def activate_decision_turn_channel(channel: DecisionTurnChannel) -> Iterator[DecisionTurnChannel]:
    """Activate an existing channel within one asyncio execution context."""

    token: Token[DecisionTurnChannel | None] = _CHANNEL.set(channel)
    try:
        yield channel
    finally:
        _CHANNEL.reset(token)


@contextmanager
def bind_decision_turn_channel(*, locale: str = "") -> Iterator[DecisionTurnChannel]:
    channel = DecisionTurnChannel(locale=str(locale or ""))
    with activate_decision_turn_channel(channel):
        yield channel
