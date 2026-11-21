"""Select package registries for isolated Skill dependency builds."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class DependencySource:
    name: str
    pip_index: str
    npm_registry: str
    apt_mirror: str

    def environment(self) -> list[str]:
        values = [f"MOVO_DEPENDENCY_SOURCE={self.name}"]
        if self.pip_index:
            values.append(f"PIP_INDEX_URL={self.pip_index}")
        if self.npm_registry:
            values.append(f"npm_config_registry={self.npm_registry}")
        if self.apt_mirror:
            values.append(f"MOVO_APT_MIRROR={self.apt_mirror}")
        return values


GLOBAL = DependencySource("global", "https://pypi.org/simple", "https://registry.npmjs.org", "")
CHINA = DependencySource("cn", "https://mirrors.aliyun.com/pypi/simple", "https://registry.npmmirror.com", "https://mirrors.aliyun.com")


def source_attempts() -> list[DependencySource]:
    preferred = os.environ.get("MOVO_DEPENDENCY_MIRROR", "global").strip().lower()
    ordered = [CHINA, GLOBAL] if preferred == "cn" else [GLOBAL, CHINA]
    custom_pip = os.environ.get("MOVO_PIP_INDEX_URL", "").strip()
    custom_npm = os.environ.get("MOVO_NPM_REGISTRY", "").strip()
    custom_apt = os.environ.get("MOVO_APT_MIRROR", "").strip()
    if any((custom_pip, custom_npm, custom_apt)):
        first = ordered[0]
        ordered[0] = DependencySource(
            "custom", custom_pip or first.pip_index,
            custom_npm or first.npm_registry, custom_apt or first.apt_mirror,
        )
    return ordered if ordered[0] != ordered[1] else ordered[:1]


def build_attempts() -> list[DependencySource]:
    """Try the alternate registry before repeating transient failures."""
    sources = source_attempts()
    try:
        extra = int(os.environ.get("MOVO_SKILL_DEPENDENCY_RETRIES", "1"))
    except ValueError:
        extra = 1
    extra = max(0, min(extra, 2))
    return sources + [sources[index % len(sources)] for index in range(extra)]


def retryable_failure(detail: str) -> bool:
    text = detail.lower()
    return any(fragment in text for fragment in (
        "timeoutexpired", "timed out", "readtimeout", "connecttimeout",
        "connection refused", "connection reset", "temporary failure in name resolution",
        "name or service not known", "could not resolve", "network is unreachable",
        "eai_again", "econnreset", "econnrefused", "enotfound", "etimedout",
        "502 bad gateway", "503 service unavailable", "504 gateway timeout",
    ))
