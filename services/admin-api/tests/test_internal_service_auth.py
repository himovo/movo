from app.core.internal_service_auth import resolve_backend_service_token


def test_canonical_internal_service_token_wins(monkeypatch):
    monkeypatch.setenv("ADMIN_BACKEND_SERVICE_TOKEN", "canonical-token")

    assert resolve_backend_service_token("stale-alias") == "canonical-token"


def test_prefixed_alias_remains_compatible(monkeypatch):
    monkeypatch.delenv("ADMIN_BACKEND_SERVICE_TOKEN", raising=False)

    assert resolve_backend_service_token("legacy-token") == "legacy-token"
