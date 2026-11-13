from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import asyncio

from app.dsh_runtime import personal_output_delivery as delivery
from app.dsh_runtime.presented_output_selection import selected_paths
from app.execution_isolation.personal_space import conversation_space_key


def _present(*paths: str) -> dict:
    return {
        "source": {"native_event_type": "deliverables/presented"},
        "payload": {"files": [{"path": path} for path in paths]},
    }


def test_only_explicitly_presented_files_are_selected(tmp_path: Path) -> None:
    conversation = tmp_path / "conversation"
    conversation.mkdir()
    final = conversation / "report.html"
    final.write_text("final")
    (conversation / "probe.html").write_text("probe")
    (conversation / "notes.txt").write_text("notes")

    events = [_present("report.html"), _present("report.html")]
    assert selected_paths(events, conversation, "chat") == [final]
    assert selected_paths([], conversation, "chat") == []


def test_multiple_declared_formats_preserve_order(tmp_path: Path) -> None:
    conversation = tmp_path / "conversation"
    conversation.mkdir()
    html = conversation / "report.html"
    pdf = conversation / "report.pdf"
    html.write_text("html")
    pdf.write_bytes(b"pdf")
    ignored = {"source": {"native_event_type": "tool/result"},
               "payload": {"files": [{"path": "draft.txt"}]}}
    assert selected_paths([ignored, _present("report.html", "report.pdf")], conversation, "chat") == [html, pdf]


def test_presented_paths_must_stay_inside_conversation(tmp_path: Path) -> None:
    conversation = tmp_path / "conversation"
    conversation.mkdir()
    final = conversation / "final.pdf"
    final.write_bytes(b"final")
    outside = tmp_path / "outside.pdf"
    outside.write_bytes(b"outside")
    try:
        (conversation / "link.pdf").symlink_to(outside)
    except OSError:
        pass
    key = conversation_space_key("chat")
    runtime_path = f"/job/home/conversations/{key}/final.pdf"
    events = [
        _present("../outside.pdf", str(outside), "link.pdf", "missing.pdf"),
        _present(runtime_path),
    ]
    assert selected_paths(events, conversation, "chat") == [final]


def test_delivery_uses_only_persisted_present_events(tmp_path: Path, monkeypatch) -> None:
    final = tmp_path / "final.html"
    final.write_text("final")
    (tmp_path / "probe.html").write_text("probe")

    class Cursor:
        def sort(self, *_args):
            return self

        async def __aiter__(self):
            yield {"kernel_event": _present("final.html")}

    class Collection:
        def find(self, query, _projection):
            assert query["message_id"] == "message"
            assert query["kernel_event.source.native_event_type"] == "deliverables/presented"
            return Cursor()

    class Storage:
        def upload_bytes_with_path(self, *, content, user_id, file_name, content_type):
            assert content == b"final"
            return "signed", f"user/{file_name}"

        def sign_url(self, _path):
            return "signed"

    monkeypatch.setattr(delivery, "_conversation_root", lambda _binding: tmp_path)
    monkeypatch.setattr(delivery, "get_db", lambda: SimpleNamespace(kernel_event_inbox=Collection()))
    monkeypatch.setattr(delivery, "AliyunOSSUploader", Storage)
    binding = {"execution_location": "server", "tenant_id": "tenant", "user_id": "user", "conversation_id": "chat"}
    documents = asyncio.run(delivery.deliver_personal_outputs(binding, "message"))
    assert [item["filename"] for item in documents] == ["final.html"]
