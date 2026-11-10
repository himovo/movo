import json
from pathlib import Path

from app.dsh_runtime.plugin_management.offline_package_capture import imported_archive, imported_plugin_record


def test_imported_plugin_archive_resolves_exact_version(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MOVO_OFFLINE_PACKAGE_ROOT", str(tmp_path))
    collections = tmp_path / "collections"
    archives = tmp_path / "plugin-archives"
    collections.mkdir()
    archives.mkdir()
    digest = "a" * 64
    (archives / f"{digest}.tgz").write_bytes(b"package")
    (collections / "plugin-record.json").write_text(json.dumps({
        "name": "@example/plugin", "version": "1.2.3", "archiveDigest": digest,
        "dshVersion": "0.2.1-alpha.1",
    }), encoding="utf-8")

    assert imported_archive("@example/plugin@1.2.3") == str(archives / f"{digest}.tgz")
    assert imported_plugin_record("@example/plugin@1.2.3") == (
        str(archives / f"{digest}.tgz"), "0.2.1-alpha.1")
    assert imported_archive("@example/plugin@1.2.4") == ""
    assert imported_archive("../plugin@1.2.3") == ""
