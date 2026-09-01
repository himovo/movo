from __future__ import annotations

from collections.abc import AsyncIterable, Callable
from typing import Any, Protocol

from .assertions import assert_scenario
from .collector import EventCollector, ScenarioResult
from .loader import ScenarioCase


class StreamAdapter(Protocol):
    def stream(self, case: ScenarioCase) -> AsyncIterable[str | bytes | dict[str, Any]]: ...


class GraphOrchestratorAdapter:
    """Thin adapter around the production graph stream; it changes no runtime state."""

    def __init__(self, orchestrator: Any) -> None:
        self.orchestrator = orchestrator

    def stream(self, case: ScenarioCase) -> AsyncIterable[str]:
        output_spec = dict(case.output_spec)
        output_spec.setdefault("route_kind", "task")
        return self.orchestrator.run_stream(
            [{"role": "user", "content": case.prompt}],
            output_spec=output_spec,
        )


class CallableStreamAdapter:
    def __init__(self, factory: Callable[[ScenarioCase], AsyncIterable[Any]]) -> None:
        self.factory = factory

    def stream(self, case: ScenarioCase) -> AsyncIterable[Any]:
        return self.factory(case)


class ScenarioRunner:
    def __init__(self, adapter: StreamAdapter) -> None:
        self.adapter = adapter
        self.collector = EventCollector()

    async def run(self, case: ScenarioCase, *, verify: bool = True) -> ScenarioResult:
        result = await self.collector.collect(self.adapter.stream(case))
        if verify:
            assert_scenario(case, result)
        return result
