"""Check a plugin's declared DSH release train before recording installation."""

from __future__ import annotations

import re
from typing import Any


_VERSION = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?$")


def _parts(value: str) -> tuple[int, int, int, tuple[tuple[int, int | str], ...]] | None:
    match = _VERSION.fullmatch(value)
    if not match:
        return None
    prerelease = tuple(
        (0, int(part)) if part.isdigit() else (1, part)
        for part in (match.group(4) or "").split(".") if part
    )
    return int(match.group(1)), int(match.group(2)), int(match.group(3)), prerelease


def _matches_release(current: str, declared: str) -> bool:
    target = declared.removesuffix("+")
    actual_parts, target_parts = _parts(current), _parts(target)
    if actual_parts is None or target_parts is None:
        return False
    if actual_parts[:2] != target_parts[:2]:
        return False
    actual_order = (actual_parts[2], bool(not actual_parts[3]), actual_parts[3])
    target_order = (target_parts[2], bool(not target_parts[3]), target_parts[3])
    # The release map records verified DSH builds, not an exhaustive allowlist.
    # A newer build in the same minor line may proceed to runtime validation.
    return actual_order >= target_order


def incompatible_release(manifest: dict[str, Any], dsh_version: str) -> str:
    compatibility = manifest.get("compatibility") or {}
    releases = compatibility.get("dshReleases") if isinstance(compatibility, dict) else None
    if not isinstance(releases, dict) or not releases:
        return ""
    if releases.get(dsh_version) == "incompatible":
        return (f"incompatible-version: {manifest.get('name', 'plugin')}@{manifest.get('version', '?')} "
                f"explicitly excludes current DSH {dsh_version}")
    supported = [release for release, status in releases.items()
                 if isinstance(release, str) and status == "compatible"]
    if any(_matches_release(dsh_version, release) for release in supported):
        return ""
    return (f"incompatible-version: {manifest.get('name', 'plugin')}@{manifest.get('version', '?')} "
            f"supports DSH releases {', '.join(supported) or 'none'}; current DSH {dsh_version}")
