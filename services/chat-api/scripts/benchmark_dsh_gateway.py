#!/usr/bin/env python3
"""Compare the thin ASKAI Gateway with direct calls to the same DSH Host."""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import tempfile
from pathlib import Path
from time import perf_counter

CHAT_API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CHAT_API_ROOT))

from app.dsh_runtime import (
    DshAgentKernelGateway,
    DshHostConfig,
    DshRuntimeHostManager,
    HttpKernelHostTransport,
)
from app.dsh_runtime.contracts import (
    ContentBlock,
    CreateRuntimeRequest,
    CreateSessionRequest,
    SendRequest,
    SessionSpec,
)


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(len(ordered) * fraction + 0.9999) - 1))
    return ordered[index]


async def latest_cursor(transport: HttpKernelHostTransport, runtime_id: str, session_id: str) -> int:
    response = await transport.request(
        "GET",
        f"/v1/runtimes/{runtime_id}/sessions/{session_id}/events",
        params={"after": 0},
    )
    return max((int(event["cursor"]) for event in response["events"]), default=0)


async def direct_round(
    transport: HttpKernelHostTransport,
    runtime_id: str,
    session_id: str,
    index: int,
) -> tuple[float, float]:
    cursor = await latest_cursor(transport, runtime_id, session_id)
    started = perf_counter()
    await transport.request(
        "POST",
        f"/v1/runtimes/{runtime_id}/sessions/{session_id}/send",
        json={
            "mode": "followup",
            "content": [{"type": "text", "data": {"text": f"direct-{index}"}}],
        },
    )
    first_event_ms = None
    async for event in transport.stream(
        "GET",
        f"/v1/runtimes/{runtime_id}/sessions/{session_id}/event-stream",
        params={"after": cursor},
    ):
        elapsed = (perf_counter() - started) * 1000
        if first_event_ms is None:
            first_event_ms = elapsed
        if event.get("nativeType") == "turn/end":
            return first_event_ms, (perf_counter() - started) * 1000
    raise RuntimeError("direct DSH stream ended before turn completion")


async def gateway_round(
    gateway: DshAgentKernelGateway,
    transport: HttpKernelHostTransport,
    runtime_id: str,
    session_id: str,
    index: int,
) -> tuple[float, float]:
    cursor = await latest_cursor(transport, runtime_id, session_id)
    started = perf_counter()
    await gateway.send(
        SendRequest(
            session_id=session_id,
            request_id=f"gateway-{index}",
            content=[ContentBlock(type="text", data={"text": f"gateway-{index}"})],
        )
    )
    first_event_ms = None
    async for event in gateway.subscribe(session_id, cursor):
        if first_event_ms is None:
            first_event_ms = (perf_counter() - started) * 1000
        if event.type == "turn.completed":
            return first_event_ms, (perf_counter() - started) * 1000
    raise RuntimeError("gateway subscription ended before turn completion")


async def benchmark(node: Path, host_entry: Path, samples: int) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="askai-dsh-benchmark-") as directory:
        root = Path(directory)
        manager = DshRuntimeHostManager(
            DshHostConfig(
                node_executable=node,
                host_entry=host_entry,
                storage_root=root / "sessions",
                log_path=root / "host.log",
            )
        )
        transport = None
        try:
            base_url = await manager.start()
            transport = HttpKernelHostTransport(base_url, timeout_seconds=5)
            gateway = DshAgentKernelGateway(transport)
            runtime = await gateway.create_runtime(
                CreateRuntimeRequest(
                    tenant_id="benchmark",
                    profile_version="deterministic-v1",
                    isolation_key="benchmark:deterministic-v1",
                )
            )
            direct_session = await gateway.create_session(
                CreateSessionRequest(
                    runtime_id=runtime.runtime_id,
                    session_spec=SessionSpec(
                        conversation_id="benchmark-direct",
                        tenant_id="benchmark",
                        user_id="benchmark",
                        profile_version="deterministic-v1",
                    ),
                )
            )
            gateway_session = await gateway.create_session(
                CreateSessionRequest(
                    runtime_id=runtime.runtime_id,
                    session_spec=SessionSpec(
                        conversation_id="benchmark-gateway",
                        tenant_id="benchmark",
                        user_id="benchmark",
                        profile_version="deterministic-v1",
                    ),
                )
            )

            for index in range(2):
                await direct_round(transport, runtime.runtime_id, direct_session.session_id, -index)
                await gateway_round(gateway, transport, runtime.runtime_id, gateway_session.session_id, -index)
            direct_rounds = [
                await direct_round(transport, runtime.runtime_id, direct_session.session_id, index)
                for index in range(samples)
            ]
            gateway_rounds = [
                await gateway_round(gateway, transport, runtime.runtime_id, gateway_session.session_id, index)
                for index in range(samples)
            ]
            direct_first = [value[0] for value in direct_rounds]
            gateway_first = [value[0] for value in gateway_rounds]
            direct = [value[1] for value in direct_rounds]
            gateway_values = [value[1] for value in gateway_rounds]
            direct_total = sum(direct)
            gateway_total = sum(gateway_values)
            direct_first_p95 = percentile(direct_first, 0.95)
            gateway_first_p95 = percentile(gateway_first, 0.95)
            return {
                "samples": samples,
                "first_event_ms": {
                    "direct_dsh_host_p95": round(direct_first_p95, 3),
                    "askai_gateway_p95": round(gateway_first_p95, 3),
                    "gateway_increment_p95": round(gateway_first_p95 - direct_first_p95, 3),
                },
                "direct_dsh_host_turn_completion_ms": {
                    "median": round(statistics.median(direct), 3),
                    "p95": round(percentile(direct, 0.95), 3),
                },
                "askai_gateway_turn_completion_ms": {
                    "median": round(statistics.median(gateway_values), 3),
                    "p95": round(percentile(gateway_values, 0.95), 3),
                },
                "throughput_ratio": round(direct_total / gateway_total, 4),
                "passes_latency_gate": gateway_first_p95 - direct_first_p95
                <= max(50, direct_first_p95 * 0.05),
                "passes_throughput_gate": direct_total / gateway_total >= 0.9,
            }
        finally:
            if transport is not None:
                await transport.close()
            await manager.stop()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--node", required=True, type=Path)
    parser.add_argument("--host-entry", required=True, type=Path)
    parser.add_argument("--samples", type=int, default=20)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(benchmark(args.node, args.host_entry, args.samples)), indent=2))


if __name__ == "__main__":
    main()
