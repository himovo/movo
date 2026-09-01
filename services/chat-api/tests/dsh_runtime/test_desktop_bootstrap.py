from __future__ import annotations

import asyncio
from dataclasses import dataclass

from app.dsh_runtime.desktop_bootstrap import DesktopRuntimeBootstrapService


@dataclass
class Snapshot:
    profile_version: str = "rp-desktop"
    model_instance_id: str = "model-a"


class Publisher:
    def __init__(self) -> None:
        self.call = None

    async def publish_model_profile(self, **kwargs):
        self.call = kwargs
        return Snapshot()


class Resolver:
    def __init__(self) -> None:
        self.call = None

    async def resolve(self, profile_version, *, tenant_id=None):
        self.call = (profile_version, tenant_id)
        return {"modelName": "deepseek", "accessToken": "short-lived"}


def test_desktop_bootstrap_publishes_user_scoped_immutable_profile() -> None:
    async def run() -> None:
        publisher = Publisher()
        resolver = Resolver()
        result = await DesktopRuntimeBootstrapService(publisher, resolver).prepare(
            tenant_id="tenant-a", user_id="user-a", model_instance_id="model-a"
        )
        assert publisher.call == {
            "tenant_id": "tenant-a", "actor_id": "user-a", "user_id": "user-a",
            "model_instance_id": "model-a", "activate": False,
        }
        assert resolver.call == ("rp-desktop", "tenant-a")
        assert result.profile_version == "rp-desktop"
        assert result.model_profile["accessToken"] == "short-lived"

    asyncio.run(run())
