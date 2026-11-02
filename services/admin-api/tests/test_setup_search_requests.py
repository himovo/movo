from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest

from app.api.routes import setup
from app.services.setup_external_search import setup_provider_catalog


@pytest.mark.parametrize("provider", [row["id"] for row in setup_provider_catalog()])
def test_setup_accepts_every_advertised_search_provider(provider):
    request = setup.SetupExternalSearchRequest(provider=provider, apiKey="test-secret")
    assert request.provider == provider


def test_setup_rejects_unknown_search_provider():
    with pytest.raises(ValidationError):
        setup.SetupExternalSearchRequest(provider="unknown", apiKey="test-secret")


def test_deepseek_search_test_reaches_provider_service(monkeypatch):
    received = []
    async def ensure_open(): pass
    async def test_search(payload):
        received.append(payload)
        return [{"title": "Example", "url": "https://example.com"}]
    monkeypatch.setattr(setup, "_ensure_setup_open", ensure_open)
    monkeypatch.setattr(setup, "test_setup_search", test_search)
    app = FastAPI()
    app.include_router(setup.router, prefix="/setup")
    payload = {"provider": "deepseek", "apiKey": "test-secret", "endpoint": "https://api.deepseek.com/v1/tools/search", "query": "test"}
    with TestClient(app) as client:
        response = client.post('/setup/search/test', json=payload)
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert received[0]["provider"] == "deepseek"
    assert received[0]["endpoint"] == payload["endpoint"]


def test_setup_initialization_accepts_deepseek_search():
    request = setup.SetupInitRequest(
        orgName="Test Organization", adminUsername="admin", adminPassword="test-password-only",
        employeeUsername="employee", employeePassword="test-password-only", employeeName="Test User",
        orgTotalTokens=1000, defaultUserTokens=100,
        model={"providerId": "test", "displayName": "Test Model", "modelName": "test-model", "baseUrl": "https://example.com/v1", "apiKey": "test-secret"},
        externalSearch={"provider": "deepseek", "apiKey": "test-secret"},
    )
    assert request.externalSearch.provider == "deepseek"
