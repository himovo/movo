#!/usr/bin/env python3
"""Paid/live validation of two admin-managed models through the real DSH Host."""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import secrets
import socket
import sys
import tempfile
from pathlib import Path

import uvicorn
from fastapi import FastAPI

CHAT_API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CHAT_API_ROOT))

from app.api.endpoints.dsh_model_gateway import router as model_gateway_router
from app.core.config import get_settings
from app.core.db import close_db, get_db
from app.dsh_runtime import DshAgentKernelGateway, DshHostConfig, DshRuntimeHostManager, HttpKernelHostTransport
from app.dsh_runtime.contracts import ContentBlock, CreateRuntimeRequest, CreateSessionRequest, SendRequest, SessionSpec
from app.dsh_runtime.model_gateway.token import ModelGatewayTokenService
from app.dsh_runtime.profile import InMemoryRuntimeProfileStore, ModelProfileCompiler, MongoModelCatalog, RuntimeProfileResolver
from app.llm.configured_models import get_model_config


def reserve_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        return int(server.getsockname()[1])


async def wait_for_server(server: uvicorn.Server) -> None:
    for _ in range(200):
        if server.started:
            return
        await asyncio.sleep(0.025)
    raise RuntimeError("live Model Gateway did not start")


async def collect_turn(gateway: DshAgentKernelGateway, session_id: str) -> list[object]:
    events = []
    async for event in gateway.subscribe(session_id):
        events.append(event)
        if event.type == "turn.completed":
            return events
    raise RuntimeError("DSH event stream ended before turn completion")


async def select_profiles():
    db = get_db()
    rows = await db.admin_model_instances.find(
        {"status": "active", "capabilities": "chat"}
    ).sort([("is_default", -1), ("priority", 1)]).to_list(length=200)
    for tenant_id in dict.fromkeys(str(row.get("main_id") or "") for row in rows):
        tenant_rows = [row for row in rows if str(row.get("main_id") or "") == tenant_id]
        if tenant_id and len(tenant_rows) >= 2:
            compiler = ModelProfileCompiler(MongoModelCatalog())
            try:
                default_profile = await compiler.compile(tenant_id=tenant_id)
                await get_model_config(default_profile.model_instance_id, tenant_id)
            except Exception:
                continue
            for explicit_row in tenant_rows:
                explicit_id = str(explicit_row.get("_id") or "")
                if explicit_id == default_profile.model_instance_id:
                    continue
                try:
                    await get_model_config(explicit_id, tenant_id)
                    explicit_profile = await compiler.compile(
                        tenant_id=tenant_id,
                        model_instance_id=explicit_id,
                    )
                except Exception:
                    continue
                return tenant_id, default_profile, explicit_profile
    raise RuntimeError("live validation requires one tenant with two active chat models")


async def validate(node: Path, host_entry: Path) -> dict[str, object]:
    tenant_id, default_profile, explicit_profile = await select_profiles()
    store = InMemoryRuntimeProfileStore()
    await store.publish(default_profile, actor_id="dsh-live-validation")
    await store.publish(explicit_profile, actor_id="dsh-live-validation")

    port = reserve_port()
    app = FastAPI()
    app.include_router(model_gateway_router)
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", access_log=False)
    )
    server_task = asyncio.create_task(server.serve())
    await wait_for_server(server)

    from app.runtime.runtime_services import token_usage_dispatcher

    await token_usage_dispatcher.start()
    settings = get_settings()
    signing_secret = str(
        settings.DSH_MODEL_GATEWAY_SIGNING_SECRET
        or settings.ASKAI_ADMIN_JWT_SECRET
        or ""
    )
    if len(signing_secret) < 16:
        signing_secret = secrets.token_urlsafe(32)
        settings.DSH_MODEL_GATEWAY_SIGNING_SECRET = signing_secret
    resolver = RuntimeProfileResolver(
        store,
        ModelGatewayTokenService(signing_secret),
        gateway_url=f"http://127.0.0.1:{port}/internal/dsh/model/generate",
    )
    with tempfile.TemporaryDirectory(prefix="askai-dsh-live-model-") as directory:
        host = DshRuntimeHostManager(
            DshHostConfig(
                node_executable=node,
                host_entry=host_entry,
                storage_root=Path(directory) / "sessions",
                log_path=Path(directory) / "host.log",
            )
        )
        transport = None
        try:
            host_url = await host.start()
            transport = HttpKernelHostTransport(host_url, timeout_seconds=120)
            gateway = DshAgentKernelGateway(transport, poll_interval_seconds=0.01, profile_resolver=resolver)
            results = []
            for index, profile in enumerate((default_profile, explicit_profile), start=1):
                runtime = await gateway.create_runtime(
                    CreateRuntimeRequest(
                        tenant_id=tenant_id,
                        profile_version=profile.profile_version,
                        isolation_key=f"live-validation:{profile.profile_version}",
                    )
                )
                session = await gateway.create_session(
                    CreateSessionRequest(
                        runtime_id=runtime.runtime_id,
                        session_spec=SessionSpec(
                            conversation_id=f"live-validation-{index}",
                            tenant_id=tenant_id,
                            user_id="live-validation",
                            profile_version=profile.profile_version,
                        ),
                    )
                )
                await gateway.send(
                    SendRequest(
                        session_id=session.session_id,
                        request_id=f"live-validation-{index}",
                        content=[ContentBlock(type="text", data={"text": "请只回复 ASKAI_DSH_OK"})],
                    )
                )
                events = await asyncio.wait_for(collect_turn(gateway, session.session_id), timeout=120)
                failures = [event for event in events if event.type == "model.request.failed"]
                completed = [event for event in events if event.type == "agent.message.completed"]
                if failures or not completed:
                    code = failures[-1].payload.get("code") if failures else "missing_assistant_message"
                    raise RuntimeError(f"live DSH model validation failed: {code}")
                results.append({
                    "profile_bound": session.profile_version == profile.profile_version,
                    "model_bound": session.model_instance_id == profile.model_instance_id,
                    "assistant_completed": True,
                })
            return {"live_models": 2, "results": results, "usage_stage": "dsh_agent_turn"}
        finally:
            if transport is not None:
                await transport.close()
            await host.stop()
            await token_usage_dispatcher.stop()
            server.should_exit = True
            await server_task
            close_db()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm-live-call", action="store_true")
    parser.add_argument("--node", type=Path, default=Path(shutil.which("node") or "node"))
    parser.add_argument(
        "--host-entry",
        type=Path,
        default=CHAT_API_ROOT / "dsh" / "runtime-host" / "src" / "host.mjs",
    )
    args = parser.parse_args()
    if not args.confirm_live_call:
        raise SystemExit("refusing paid provider calls without --confirm-live-call")
    print(json.dumps(asyncio.run(validate(args.node, args.host_entry)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
