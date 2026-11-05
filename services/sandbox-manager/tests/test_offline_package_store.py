from pathlib import Path

import pytest

from app.offline_package_store import OfflinePackageStore
from app.offline_collections import record


def test_export_import_reuses_package_files(tmp_path: Path) -> None:
    source = OfflinePackageStore(tmp_path / "source")
    (source.root / "pip" / "example-1.0-py3-none-any.whl").write_bytes(b"wheel-data")
    (source.root / "npm" / "cache-entry").write_bytes(b"npm-data")
    source.set_offline(True)
    archive = tmp_path / "packages.zip"
    source.export_to(archive)

    target = OfflinePackageStore(tmp_path / "target")
    result = target.import_archive(archive)

    assert result["counts"]["pip"] == 1
    assert result["counts"]["npm"] == 1
    assert (target.root / "pip" / "example-1.0-py3-none-any.whl").read_bytes() == b"wheel-data"
    assert target.offline is False


def test_import_rejects_modified_package(tmp_path: Path) -> None:
    source = OfflinePackageStore(tmp_path / "source")
    (source.root / "pip" / "example.whl").write_bytes(b"original")
    archive = tmp_path / "packages.zip"
    source.export_to(archive)
    import zipfile
    modified = tmp_path / "modified.zip"
    with zipfile.ZipFile(archive) as source_zip, zipfile.ZipFile(modified, "w") as target_zip:
        for item in source_zip.infolist():
            data = b"modified" if item.filename == "pip/example.whl" else source_zip.read(item.filename)
            target_zip.writestr(item.filename, data)

    target = OfflinePackageStore(tmp_path / "target")
    with pytest.raises(ValueError, match="checksum"):
        target.import_archive(modified)
    assert not (target.root / "pip" / "example.whl").exists()


def test_offline_mode_updates_plugin_package_manager_config(tmp_path: Path) -> None:
    store = OfflinePackageStore(tmp_path / "packages")
    assert "offline=false" in (store.root / ".npmrc").read_text()
    store.set_offline(True)
    config = (store.root / ".npmrc").read_text()
    assert "offline=true" in config
    assert "store-dir=/offline-packages/pnpm" in config


def test_export_selected_preparation_record(tmp_path: Path) -> None:
    source = OfflinePackageStore(tmp_path / "source")
    skill = tmp_path / "skill"
    skill.mkdir()
    (skill / "requirements.txt").write_text("example==1.0\n", encoding="utf-8")
    (source.root / "pip" / "example.whl").write_bytes(b"example")
    record_id = "a" * 32
    record(source.root, digest="b" * 64, record_id=record_id, source="global",
           base_image_id="sha256:test", skill_root=skill)
    (source.root / "pip" / "unrelated.whl").write_bytes(b"unrelated")
    archive = tmp_path / "selected.zip"
    source.export_to(archive, {record_id})

    target = OfflinePackageStore(tmp_path / "target")
    inventory = target.import_archive(archive)
    assert (target.root / "pip" / "example.whl").is_file()
    assert not (target.root / "pip" / "unrelated.whl").exists()
    assert inventory["collections"][0]["declared"]["pip"] == ["example==1.0"]
