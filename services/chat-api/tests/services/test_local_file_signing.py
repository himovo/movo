from urllib.parse import parse_qs, urlparse

from app.services.local_file_signing import sign_local_file_url, verify_local_file_signature


def test_signed_local_file_url_round_trip(monkeypatch) -> None:
    monkeypatch.setattr("app.services.local_file_signing.time.time", lambda: 1_000)
    url = sign_local_file_url(
        "/askai-api/api/files/user/report.pdf",
        "user/report.pdf",
        secret="test-secret",
        ttl_seconds=60,
    )
    query = parse_qs(urlparse(url).query)

    assert query["expires"] == ["1060"]
    assert verify_local_file_signature(
        "user/report.pdf",
        expires_at=1060,
        signature=query["signature"][0],
        secret="test-secret",
        now=1059,
    )


def test_signed_local_file_url_rejects_tampering_and_expiry(monkeypatch) -> None:
    monkeypatch.setattr("app.services.local_file_signing.time.time", lambda: 1_000)
    url = sign_local_file_url(
        "/api/files/user/report.pdf",
        "user/report.pdf",
        secret="test-secret",
        ttl_seconds=60,
    )
    query = parse_qs(urlparse(url).query)
    signature = query["signature"][0]

    assert not verify_local_file_signature(
        "other/report.pdf",
        expires_at=1060,
        signature=signature,
        secret="test-secret",
        now=1050,
    )
    assert not verify_local_file_signature(
        "user/report.pdf",
        expires_at=1060,
        signature=signature,
        secret="test-secret",
        now=1061,
    )
