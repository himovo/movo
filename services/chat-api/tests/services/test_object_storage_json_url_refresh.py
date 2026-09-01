from __future__ import annotations

from app.utils.oss_uploader import ObjectStorageClient


class FakeStorage(ObjectStorageClient):
    storage_backend = "oss"

    def __init__(self) -> None:
        pass

    def object_path_from_url(self, url: str) -> str:
        if url.startswith("/api/files/"):
            return url.removeprefix("/api/files/")
        if "oss-cn-beijing.aliyuncs.com/" in url:
            return url.split("oss-cn-beijing.aliyuncs.com/", 1)[1].split("?", 1)[0]
        return ""

    def sign_url(self, object_path: str, expires: int | None = None) -> str:
        return f"https://bucket.oss-cn-beijing.aliyuncs.com/{object_path}?Expires=fresh&Signature=fresh"

    def sign_url_from_url(self, url: str, expires: int | None = None) -> str:
        object_path = self.object_path_from_url(url)
        return self.sign_url(object_path, expires=expires) if object_path else ""


class FakeLocalStorage(FakeStorage):
    storage_backend = "local"

    def sign_url(self, object_path: str, expires: int | None = None) -> str:
        return f"/api/files/{object_path}"


def test_refresh_json_urls_renews_nested_signed_oss_urls() -> None:
    expired = "https://bucket.oss-cn-beijing.aliyuncs.com/u/2026/cover.png?Expires=1&Signature=old"
    payload = {
        "deck_id": "deck-1",
        "pages": [
            {
                "page_id": "p1",
                "blocks": [
                    {"id": "img", "type": "image", "content": expired},
                    {"id": "text", "type": "text_box", "content": "keep this text"},
                ],
            }
        ],
    }

    refreshed, count = FakeStorage().refresh_json_urls(payload)

    assert count == 1
    assert refreshed["pages"][0]["blocks"][0]["content"].endswith("Expires=fresh&Signature=fresh")
    assert refreshed["pages"][0]["blocks"][1]["content"] == "keep this text"


def test_refresh_json_urls_keeps_local_file_urls_stable() -> None:
    payload = {
        "pages": [
            {
                "blocks": [
                    {"type": "image", "content": "/api/files/u/2026/cover.png"},
                ],
            }
        ],
    }

    refreshed, count = FakeLocalStorage().refresh_json_urls(payload)

    assert count == 0
    assert refreshed["pages"][0]["blocks"][0]["content"] == "/api/files/u/2026/cover.png"


def test_refresh_json_urls_ignores_plain_text_and_non_json_values() -> None:
    payload = {"content": "plain report text", "count": 3}

    refreshed, count = FakeStorage().refresh_json_urls(payload)

    assert count == 0
    assert refreshed == payload
    assert FakeStorage().refresh_json_urls("not json") == ("not json", 0)
