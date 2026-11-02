from app.api.endpoints.desktop_release import desktop_release


def test_desktop_release_uses_build_identity(monkeypatch):
    monkeypatch.setenv("MOVO_SOURCE_REVISION", "revision-a")
    monkeypatch.setenv("MOVO_SOURCE_VERSION", "v2.1.0")
    assert desktop_release() == {"source_revision": "revision-a", "source_version": "v2.1.0"}
