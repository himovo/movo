from fastapi.testclient import TestClient

from app import main
from app.skill_build_records import SkillBuildRecords


def test_preparation_logs_require_manager_token_and_support_history(tmp_path, monkeypatch):
    digest = "d" * 64
    token = "a" * 64
    monkeypatch.setenv("MOVO_SANDBOX_MANAGER_TOKEN", token)
    store = SkillBuildRecords(tmp_path)
    first = store.create(digest, "sha256:base")
    store.append_attempt(digest, first, source="internal", exit_code=1, output="failed\n")
    store.finish(digest, first, "failed")
    second = store.create(digest, "sha256:base")
    store.finish(digest, second, "ready")

    class Environments:
        records = store

    class Jobs:
        environments = Environments()

    monkeypatch.setattr(main, "jobs", lambda: Jobs())
    client = TestClient(main.app)
    url = f"/v1/skill-environments/{digest}/records"
    assert client.get(url).status_code == 401
    headers = {"Authorization": f"Bearer {token}"}
    listed = client.get(url, headers=headers)
    assert [row["id"] for row in listed.json()["items"]] == [second, first]
    assert all("log" not in row for row in listed.json()["items"])
    assert client.get(f"{url}/{first}", headers=headers).json()["log"].endswith("failed\n")
