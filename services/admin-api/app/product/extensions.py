from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
import importlib
import os
from typing import Mapping, Sequence

from fastapi import APIRouter


@dataclass(frozen=True)
class AdminProductExtension:
    extension_id: str
    edition: str
    organization_defaults: Mapping[str, object] = field(default_factory=dict)
    routers: Sequence[APIRouter] = field(default_factory=tuple)


def community_extension() -> AdminProductExtension:
    return AdminProductExtension(
        extension_id="movo.community",
        edition="community",
        organization_defaults={
            "edition": "community",
            "tier": "community",
            "billing_enabled": False,
            "user_limit": None,
            "total_points": 0,
            "used_points": 0,
            "is_own_model": True,
        },
    )


@lru_cache(maxsize=1)
def get_admin_product_extension() -> AdminProductExtension:
    module_name = os.getenv("MOVO_ADMIN_PRODUCT_EXTENSION_MODULE", "").strip()
    if not module_name:
        return community_extension()
    module = importlib.import_module(module_name)
    factory = getattr(module, "create_admin_product_extension", None)
    if not callable(factory):
        raise RuntimeError(
            f"Admin product extension module {module_name!r} must export create_admin_product_extension()"
        )
    extension = factory()
    if not isinstance(extension, AdminProductExtension):
        raise RuntimeError(f"Invalid admin product extension returned by {module_name!r}")
    if extension.edition.strip().lower() == "community":
        raise RuntimeError("Private admin extensions cannot identify as the community edition")
    return extension
