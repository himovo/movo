from app.offline_collections import description, record_plugin


def test_declared_python_ranges_are_preserved_without_accepting_remote_sources(tmp_path):
    (tmp_path / "requirements.txt").write_text(
        "pillow>=10.0.0\nimageio==2.31.0\nunsafe @ https://example.test/pkg.whl\n",
        encoding="utf-8",
    )
    assert description(tmp_path)["pip"] == ["pillow>=10.0.0", "imageio==2.31.0"]


def test_plugin_collection_records_source_dsh_version(tmp_path):
    row = record_plugin(tmp_path, name="example-plugin", version="1.2.3",
                        dsh_version="0.2.1-alpha.1")
    assert row["name"] == "example-plugin"
    assert row["version"] == "1.2.3"
    assert row["dshVersion"] == "0.2.1-alpha.1"
