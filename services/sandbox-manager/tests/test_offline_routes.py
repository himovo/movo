from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.offline_package_store import OfflinePackageStore


def test_admin_package_transfer_uses_raw_stream(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MOVO_SANDBOX_MANAGER_TOKEN", "test-token")
    monkeypatch.setenv("MOVO_OFFLINE_PACKAGE_ROOT", str(tmp_path / "packages"))
    store = OfflinePackageStore()
    (store.root / "pip" / "example.whl").write_bytes(b"wheel")
    source = tmp_path / "source.zip"
    store.export_to(source)
    (store.root / "pip" / "example.whl").unlink()

    client = TestClient(app)
    response = client.post("/v1/offline-packages/import", content=source.read_bytes(),
                           headers={"Authorization": "Bearer test-token", "Content-Type": "application/octet-stream"})
    assert response.status_code == 200
    assert (store.root / "pip" / "example.whl").read_bytes() == b"wheel"


def test_package_transfer_requires_manager_token(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MOVO_SANDBOX_MANAGER_TOKEN", "test-token")
    monkeypatch.setenv("MOVO_OFFLINE_PACKAGE_ROOT", str(tmp_path / "packages"))
    response = TestClient(app).get("/v1/offline-packages")
    assert response.status_code == 401


def test_package_transfer_rejects_invalid_archive(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MOVO_SANDBOX_MANAGER_TOKEN", "test-token")
    monkeypatch.setenv("MOVO_OFFLINE_PACKAGE_ROOT", str(tmp_path / "packages"))
    response = TestClient(app).post("/v1/offline-packages/import", content=b"not-a-zip",
                                    headers={"Authorization": "Bearer test-token"})
    assert response.status_code == 400


def test_plugin_archive_requires_matching_digest(monkeypatch, tmp_path: Path) -> None:
    import hashlib
    monkeypatch.setenv("MOVO_SANDBOX_MANAGER_TOKEN", "test-token")
    monkeypatch.setenv("MOVO_OFFLINE_PACKAGE_ROOT", str(tmp_path / "packages"))
    digest = hashlib.sha256(b"plugin").hexdigest()
    client = TestClient(app)
    headers = {"Authorization": "Bearer test-token", "Content-Type": "application/octet-stream"}
    assert client.post(f"/v1/offline-packages/plugin-archives/{digest}", content=b"wrong", headers=headers).status_code == 400
    response = client.post(f"/v1/offline-packages/plugin-archives/{digest}", content=b"plugin", headers=headers)
    assert response.status_code == 200
    assert (tmp_path / "packages" / "plugin-archives" / f"{digest}.tgz").read_bytes() == b"plugin"
