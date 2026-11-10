"""Forward an authorized plugin UI stream without exposing the DSH operator cookie."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from urllib.parse import quote

import websockets
from websockets.asyncio.client import connect
from fastapi import HTTPException, WebSocket, WebSocketDisconnect


async def proxy_plugin_stream(service, grant, browser: WebSocket) -> None:
    try:
        await service._authorized_plugin(grant.tenant_id, grant.user_id,
                                         grant.plugin_id, grant.plugin_version,
                                         require_surface=False)
        runtime = await service._coordinator.ensure_runtime(
            tenant_id=grant.tenant_id, profile_version=grant.profile_version,
        )
    except HTTPException:
        await browser.close(code=1008)
        return
    base = service._runtime_host_url.replace("http://", "ws://", 1).replace("https://", "wss://", 1)
    target = (f"{base}/v1/runtimes/{quote(runtime.runtime_id, safe='')}/"
              f"plugin-ui/{quote(grant.plugin_id, safe='')}/api/remote.mux")
    try:
        async with connect(target, additional_headers=service._host_headers(),
                           max_size=8 * 1024 * 1024) as upstream:
            await browser.accept()

            async def to_host() -> None:
                try:
                    while True:
                        message = await browser.receive()
                        if message["type"] == "websocket.disconnect":
                            return
                        if message.get("text") is not None:
                            await upstream.send(message["text"])
                        elif message.get("bytes") is not None:
                            await upstream.send(message["bytes"])
                except WebSocketDisconnect:
                    return

            async def to_browser() -> None:
                async for message in upstream:
                    if isinstance(message, str):
                        await browser.send_text(message)
                    else:
                        await browser.send_bytes(message)

            tasks = [asyncio.create_task(to_host()), asyncio.create_task(to_browser())]
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
    except (OSError, websockets.WebSocketException):
        with suppress(RuntimeError):
            await browser.close(code=1011)
    else:
        with suppress(RuntimeError):
            await browser.close()
