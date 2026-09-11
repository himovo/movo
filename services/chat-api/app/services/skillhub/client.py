from __future__ import annotations

from collections.abc import Callable

import httpx

from app.core.config import get_settings
from app.services.skill_packages.validator import MAX_ARCHIVE_BYTES

from .coordinate import SkillHubCoordinate
from .errors import SkillHubError


class SkillHubClient:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
        client_factory: Callable[..., httpx.AsyncClient] = httpx.AsyncClient,
    ) -> None:
        settings = get_settings()
        self._base_url = str(base_url or settings.SKILLHUB_API_BASE_URL).rstrip("/")
        self._timeout = float(timeout_seconds or settings.SKILLHUB_DOWNLOAD_TIMEOUT_SECONDS)
        self._client_factory = client_factory

    async def download(self, coordinate: SkillHubCoordinate) -> bytes:
        params = {"slug": coordinate.slug, "source": "dsh"}
        if coordinate.version:
            params["version"] = coordinate.version
        timeout = httpx.Timeout(self._timeout, connect=min(10.0, self._timeout))
        try:
            async with self._client_factory(timeout=timeout, follow_redirects=True) as client:
                async with client.stream(
                    "GET", f"{self._base_url}/api/v1/download", params=params,
                ) as response:
                    self._raise_for_status(response, coordinate)
                    try:
                        declared = int(response.headers.get("content-length") or 0)
                    except ValueError:
                        declared = 0
                    if declared > MAX_ARCHIVE_BYTES:
                        raise SkillHubError(
                            "archive_too_large", "SkillHub package exceeds the install size limit",
                            limitBytes=MAX_ARCHIVE_BYTES,
                        )
                    chunks: list[bytes] = []
                    total = 0
                    async for chunk in response.aiter_bytes():
                        total += len(chunk)
                        if total > MAX_ARCHIVE_BYTES:
                            raise SkillHubError(
                                "archive_too_large", "SkillHub package exceeds the install size limit",
                                limitBytes=MAX_ARCHIVE_BYTES,
                            )
                        chunks.append(chunk)
        except SkillHubError:
            raise
        except httpx.TimeoutException as exc:
            raise SkillHubError("download_timeout", "SkillHub package download timed out") from exc
        except httpx.HTTPError as exc:
            raise SkillHubError("download_failed", "Could not download the SkillHub package") from exc
        content = b"".join(chunks)
        if not content.startswith(b"PK"):
            raise SkillHubError("invalid_download", "SkillHub did not return a ZIP package")
        return content

    @staticmethod
    def _raise_for_status(response: httpx.Response, coordinate: SkillHubCoordinate) -> None:
        status = response.status_code
        if status < 400:
            return
        if status == 404:
            raise SkillHubError(
                "skill_not_found", "SkillHub Skill was not found", coordinate=coordinate.canonical,
            )
        if status == 429:
            raise SkillHubError("rate_limited", "SkillHub is temporarily rate limited")
        if status in {401, 403}:
            raise SkillHubError("download_forbidden", "SkillHub refused this package download")
        raise SkillHubError(
            "skillhub_unavailable", "SkillHub is temporarily unavailable", status=status,
        )
