from __future__ import annotations

import re
from dataclasses import dataclass

from .errors import SkillHubError


PART = re.compile(r"^[a-z0-9][a-z0-9_-]{0,127}$", re.IGNORECASE)
VERSION = re.compile(r"^[0-9a-z][0-9a-z._+-]{0,31}$", re.IGNORECASE)


@dataclass(frozen=True)
class SkillHubCoordinate:
    slug: str
    namespace: str = ""
    version: str = ""

    @property
    def canonical(self) -> str:
        return f"@{self.namespace}/{self.slug}" if self.namespace else self.slug


def parse_skillhub_coordinate(raw: str, version: str = "") -> SkillHubCoordinate:
    value = str(raw or "").strip()
    if not value or ".." in value or "\\" in value or "\x00" in value:
        raise SkillHubError("invalid_coordinate", "Invalid SkillHub coordinate", coordinate=value)
    without_at = value[1:] if value.startswith("@") else value
    parts = without_at.split("/")
    if len(parts) == 1:
        namespace, slug = "", parts[0]
    elif len(parts) == 2:
        namespace, slug = parts
    else:
        raise SkillHubError("invalid_coordinate", "Invalid SkillHub coordinate", coordinate=value)
    if not PART.fullmatch(slug) or (namespace and not PART.fullmatch(namespace)):
        raise SkillHubError("invalid_coordinate", "Invalid SkillHub coordinate", coordinate=value)
    requested_version = str(version or "").strip().removeprefix("v")
    if requested_version and not VERSION.fullmatch(requested_version):
        raise SkillHubError("invalid_version", "Invalid SkillHub version", version=requested_version)
    return SkillHubCoordinate(
        slug=slug.lower(), namespace=namespace.lower(), version=requested_version,
    )
