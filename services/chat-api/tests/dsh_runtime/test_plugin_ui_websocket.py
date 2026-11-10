import asyncio
from types import SimpleNamespace

import websockets

from app.dsh_runtime.plugin_ui.websocket import proxy_plugin_stream


def test_plugin_ui_stream_relays_messages():
    async def scenario():
        async def echo(socket):
            async for message in socket:
                await socket.send(message)

        class Browser:
            def __init__(self):
                self.received = asyncio.Event()
                self.messages = []
                self.accepted = False

            async def accept(self):
                self.accepted = True

            async def receive(self):
                if not self.accepted:
                    raise AssertionError("stream was not accepted")
                if not self.messages:
                    self.messages.append("sent")
                    return {"type": "websocket.receive", "text": "hello"}
                await self.received.wait()
                return {"type": "websocket.disconnect"}

            async def send_text(self, text):
                self.messages.append(text)
                self.received.set()

            async def close(self, code=1000):
                pass

        async with websockets.serve(echo, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]

            async def authorize(*_args, **_kwargs):
                return {}

            async def runtime(*_args, **_kwargs):
                return SimpleNamespace(runtime_id="runtime")

            service = SimpleNamespace(
                _authorized_plugin=authorize,
                _coordinator=SimpleNamespace(ensure_runtime=runtime),
                _runtime_host_url=f"http://127.0.0.1:{port}",
                _host_headers=lambda: {},
            )
            grant = SimpleNamespace(tenant_id="tenant", user_id="user", plugin_id="plugin",
                                    plugin_version="1", profile_version="profile")
            browser = Browser()
            await asyncio.wait_for(proxy_plugin_stream(service, grant, browser), timeout=3)
            assert browser.messages == ["sent", "hello"]

    asyncio.run(scenario())
