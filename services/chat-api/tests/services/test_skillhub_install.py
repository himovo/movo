from __future__ import annotations

import asyncio
import io
import zipfile

import httpx
import pytest

from app.services.skillhub import (
    SkillHubClient,
    SkillHubError,
    SkillHubInstallService,
    parse_skillhub_coordinate,
)


def skill_zip(*, name: str = "birdwatching", version: str = "1.0.0") -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as bundle:
        bundle.writestr(
            "SKILL.md",
            f"---\nname: {name}\ndescription: Observe birds\nversion: {version}\n---\nFollow the field guide.\n",
        )
    return output.getvalue()


def test_coordinate_preserves_namespace_but_resolves_public_slug() -> None:
    target = parse_skillhub_coordinate(
        "@user_a730098d/shanghai-ocean-university-hengsha-birdwatching", "v2.1.5",
    )
    assert target.namespace == "user_a730098d"
    assert target.slug == "shanghai-ocean-university-hengsha-birdwatching"
    assert target.version == "2.1.5"
    assert target.canonical == "@user_a730098d/shanghai-ocean-university-hengsha-birdwatching"


@pytest.mark.parametrize("coordinate", ["", "@owner/", "owner/a/b", "../skill", "https://skillhub.cn/a"])
def test_coordinate_rejects_non_skillhub_identifiers(coordinate: str) -> None:
    with pytest.raises(SkillHubError) as caught:
        parse_skillhub_coordinate(coordinate)
    assert caught.value.code == "invalid_coordinate"


def test_client_uses_fixed_download_endpoint_and_bounds_download() -> None:
    observed: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed.append(request)
        return httpx.Response(200, content=skill_zip(), headers={"content-type": "application/zip"})

    transport = httpx.MockTransport(handler)
    client = SkillHubClient(
        base_url="https://api.skillhub.test",
        client_factory=lambda **kwargs: httpx.AsyncClient(transport=transport, **kwargs),
    )
    content = asyncio.run(client.download(parse_skillhub_coordinate("@owner/birdwatching", "1.0.0")))
    assert content.startswith(b"PK")
    assert observed[0].url.path == "/api/v1/download"
    assert observed[0].url.params["slug"] == "birdwatching"
    assert observed[0].url.params["version"] == "1.0.0"
    assert observed[0].url.params["source"] == "dsh"
    assert "owner" not in str(observed[0].url)


class Downloader:
    def __init__(self, content: bytes) -> None:
        self.content = content
        self.coordinates = []

    async def download(self, coordinate):
        self.coordinates.append(coordinate)
        return self.content


class Installer:
    def __init__(self) -> None:
        self.calls = []

    async def install(self, package, **kwargs):
        self.calls.append((package, kwargs))
        return {
            "id": "skill-1", "name": package.display_name, "slug": package.name,
            "version": package.version, "type": package.package_kind, "enabled": True,
            "duplicate": False, "updated": False, "fileCount": len(package.files),
            "warnings": [], "childCount": len(package.children), "children": [],
            "source": kwargs["package_source"],
        }


def test_service_reuses_package_validation_and_personal_installer() -> None:
    downloader = Downloader(skill_zip(name="birdwatching"))
    installer = Installer()
    result = asyncio.run(SkillHubInstallService(downloader, installer).install_personal(
        coordinate="@owner/birdwatching", tenant_id="tenant-a", user_id="user-a",
    ))
    assert result["success"] is True
    assert result["scope"] == "personal"
    assert result["availability"] == "next_turn"
    _, call = installer.calls[0]
    assert call["scope"] == "personal"
    assert call["main_id"] == "tenant-a"
    assert call["user_id"] == "user-a"
    assert call["package_source"]["coordinate"] == "@owner/birdwatching"


def test_service_reports_downloaded_package_validation_details() -> None:
    service = SkillHubInstallService(Downloader(b"PK invalid"), Installer())
    with pytest.raises(SkillHubError) as caught:
        asyncio.run(service.install_personal(
            coordinate="broken", tenant_id="tenant-a", user_id="user-a",
        ))
    assert caught.value.code == "invalid_skill_package"
    assert caught.value.details["validation"]["code"] == "invalid_zip"
