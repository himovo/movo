from __future__ import annotations

from typing import Any, Protocol

from app.services.skill_packages import SkillPackageError, SkillPackageInstaller, validate_skill_package

from .client import SkillHubClient
from .coordinate import parse_skillhub_coordinate
from .errors import SkillHubError


class PackageDownloader(Protocol):
    async def download(self, coordinate) -> bytes: ...


class SkillHubInstallService:
    def __init__(
        self,
        downloader: PackageDownloader | None = None,
        installer: SkillPackageInstaller | None = None,
    ) -> None:
        self._downloader = downloader or SkillHubClient()
        self._installer = installer or SkillPackageInstaller()

    async def install_personal(
        self,
        *,
        coordinate: str,
        version: str = "",
        tenant_id: str,
        user_id: str,
    ) -> dict[str, Any]:
        target = parse_skillhub_coordinate(coordinate, version)
        archive = await self._downloader.download(target)
        try:
            package = validate_skill_package(archive)
        except SkillPackageError as exc:
            raise SkillHubError(
                "invalid_skill_package", "The downloaded SkillHub package failed validation",
                validation=exc.detail(), coordinate=target.canonical,
            ) from exc
        source = {
            "kind": "skillhub",
            "coordinate": target.canonical,
            "namespace": target.namespace,
            "slug": target.slug,
            "requestedVersion": target.version,
        }
        result = await self._installer.install(
            package,
            scope="personal",
            main_id=tenant_id,
            user_id=user_id,
            package_source=source,
        )
        return {
            **result,
            "success": True,
            "installed": True,
            "scope": "personal",
            "availability": "next_turn",
        }
