from __future__ import annotations

import asyncio
from dataclasses import dataclass

from app.dsh_runtime.desktop_bootstrap import DesktopRuntimeBootstrapService


@dataclass
class Snapshot:
    profile_version: str = "rp-desktop"
    model_instance_id: str = "model-a"
    contract: str = "same"

    def is_execution_compatible_with(self, other) -> bool:
        return self.model_instance_id == other.model_instance_id and self.contract == other.contract


class Publisher:
    def __init__(self) -> None:
        self.call = None
        self.current = Snapshot()
        self.historical = {}

    async def publish_model_profile(self, **kwargs):
        self.call = kwargs
        return self.current

    async def get(self, profile_version):
        if profile_version not in self.historical:
            raise ValueError("Runtime Profile does not exist")
        return self.historical[profile_version]


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


def test_desktop_bootstrap_reuses_semantically_compatible_historical_profile() -> None:
    async def run() -> None:
        publisher = Publisher()
        publisher.current = Snapshot(profile_version="rp-new")
        publisher.historical["rp-old"] = Snapshot(profile_version="rp-old")
        resolver = Resolver()
        result = await DesktopRuntimeBootstrapService(publisher, resolver).prepare(
            tenant_id="tenant-a", user_id="user-a", model_instance_id="model-a",
            requested_profile_version="rp-old",
        )
        assert result.profile_version == "rp-old"
        assert resolver.call == ("rp-old", "tenant-a")

    asyncio.run(run())


def test_desktop_bootstrap_rejects_semantically_changed_historical_profile() -> None:
    async def run() -> None:
        publisher = Publisher()
        publisher.current = Snapshot(profile_version="rp-new", contract="current-policy")
        publisher.historical["rp-old"] = Snapshot(profile_version="rp-old", contract="old-policy")
        resolver = Resolver()
        result = await DesktopRuntimeBootstrapService(publisher, resolver).prepare(
            tenant_id="tenant-a", user_id="user-a", model_instance_id="model-a",
            requested_profile_version="rp-old",
        )
        assert result.profile_version == "rp-new"
        assert resolver.call == ("rp-new", "tenant-a")

    asyncio.run(run())
