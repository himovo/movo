from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
import importlib
import os
from typing import Any, Callable, Mapping, Protocol, Sequence

from fastapi import APIRouter


COMMUNITY_FEATURES: dict[str, bool] = {
    "passwordLogin": True,
    "smsLogin": False,
    "emailVerification": False,
    "selfRegistration": False,
    "organizationSelfService": False,
    "billing": False,
    "onlinePayment": False,
}


@dataclass(frozen=True)
class ProductExtension:
    """A distribution-owned extension loaded only when its package is installed."""

    extension_id: str
    edition: str
    features: Mapping[str, bool]
    organization_defaults: Mapping[str, object] = field(default_factory=dict)
    routers: Sequence[APIRouter] = field(default_factory=tuple)
    startup: Sequence[Callable[[], Any]] = field(default_factory=tuple)
    shutdown: Sequence[Callable[[], Any]] = field(default_factory=tuple)

    def capability_payload(self) -> dict[str, object]:
        merged = dict(COMMUNITY_FEATURES)
        merged.update({str(key): bool(value) for key, value in self.features.items()})
        return {
            "edition": self.edition,
            "extensionId": self.extension_id,
            "features": merged,
        }


class ProductExtensionFactory(Protocol):
    def __call__(self) -> ProductExtension: ...


def community_extension() -> ProductExtension:
    return ProductExtension(
        extension_id="movo.community",
        edition="community",
        features=COMMUNITY_FEATURES,
        organization_defaults={
            "edition": "community",
            "tier": "community",
            "billing_enabled": False,
            "user_limit": None,
            "total_points": None,
            "used_points": 0,
            "is_own_model": True,
        },
    )


def _load_factory(module_name: str) -> ProductExtensionFactory:
    module = importlib.import_module(module_name)
    factory = getattr(module, "create_product_extension", None)
    if not callable(factory):
        raise RuntimeError(
            f"Product extension module {module_name!r} must export create_product_extension()"
        )
    return factory


@lru_cache(maxsize=1)
def get_product_extension() -> ProductExtension:
    module_name = os.getenv("MOVO_PRODUCT_EXTENSION_MODULE", "").strip()
    if not module_name:
        return community_extension()
    extension = _load_factory(module_name)()
    if not isinstance(extension, ProductExtension):
        raise RuntimeError(f"Invalid product extension returned by {module_name!r}")
    if extension.edition.strip().lower() == "community":
        raise RuntimeError("Private product extensions cannot identify as the community edition")
    return extension


def reset_product_extension_cache() -> None:
    get_product_extension.cache_clear()
