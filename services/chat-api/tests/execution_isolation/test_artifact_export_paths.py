from pathlib import Path

import pytest

from app.enterprise_capabilities.data.script_engine.artifact_export import export_script_artifacts


class Storage:
    def upload_bytes_with_path(self, content, user_id, file_name, content_type):
        assert content == b"sandbox output"
        assert user_id == "user-a"
        return "signed-url", f"user-a/{file_name}"

    def sign_url(self, object_path):
        return "signed-url"


def test_container_output_path_is_mapped_to_job_workspace(tmp_path: Path):
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    (output_dir / "result.txt").write_bytes(b"sandbox output")
    result = export_script_artifacts(
        raw_artifacts=[{"path": "/job/out/result.txt"}],
        output_dir=output_dir,
        user_id="user-a",
        uploader=Storage(),
        sandbox_output_dir=Path("/job/out"),
    )
    assert result["documents"][0]["object_path"] == "user-a/result.txt"


def test_generated_html_is_delivered_as_a_document(tmp_path: Path):
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    (output_dir / "report.html").write_bytes(b"sandbox output")
    result = export_script_artifacts(
        raw_artifacts=[{"path": "/job/out/report.html"}],
        output_dir=output_dir,
        user_id="user-a",
        uploader=Storage(),
        sandbox_output_dir=Path("/job/out"),
    )
    assert result["documents"][0]["type"] == "html"
    assert result["documents"][0]["object_path"] == "user-a/report.html"


def test_generated_python_is_delivered_without_a_document_format_allowlist(tmp_path: Path):
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    (output_dir / "result.py").write_bytes(b"sandbox output")
    result = export_script_artifacts(
        raw_artifacts=[{"path": "/job/out/result.py"}],
        output_dir=output_dir,
        user_id="user-a",
        uploader=Storage(),
        sandbox_output_dir=Path("/job/out"),
    )
    assert result["documents"][0]["object_path"] == "user-a/result.py"


@pytest.mark.parametrize("path", ["/job/out/../secret.txt", "/job/other/secret.txt"])
def test_container_output_path_cannot_escape_job_output(tmp_path: Path, path: str):
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    with pytest.raises(ValueError, match="must stay under output_dir"):
        export_script_artifacts(
            raw_artifacts=[{"path": path}],
            output_dir=output_dir,
            user_id="user-a",
            uploader=Storage(),
            sandbox_output_dir=Path("/job/out"),
        )
