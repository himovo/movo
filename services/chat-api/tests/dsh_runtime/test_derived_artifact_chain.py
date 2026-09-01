from __future__ import annotations

import asyncio

from app.enterprise_capabilities.artifacts.resource_result import own_parsed_document_images
from app.enterprise_capabilities.browser.artifact_guard import reject_internal_artifact_target
from app.enterprise_capabilities.browser.service import browser_task
from app.enterprise_capabilities.data.script import run_script
from app.enterprise_capabilities.runtime.adapters import document_extract_resources, image_extract_facts
from app.enterprise_capabilities.runtime.contracts import CapabilityExecutionContext


def _context() -> CapabilityExecutionContext:
    return CapabilityExecutionContext(
        tenant_id="tenant-a",
        user_id="user-a",
        conversation_id="conversation-a",
        kernel_session_id="session-a",
        profile_version="profile-a",
        action_id="action-a",
        turn_context={},
    )


class _Storage:
    def read_bytes(self, object_path: str) -> bytes:
        assert object_path == "document-parser/2026/08/image_001.png"
        return b"derived-image"

    def upload_bytes_with_path(self, *, content, user_id, file_name, content_type):
        assert content == b"derived-image"
        assert user_id == "user-a"
        return "/askai-api/api/files/user-a/derived/image_001.png", "user-a/derived/image_001.png"


def test_document_resource_can_flow_directly_into_image_facts(monkeypatch) -> None:
    captured: dict = {}

    async def fake_extract_resources(*, node, output_spec, user_text):
        captured["parser_input"] = output_spec["input_artifacts"]["documents"][0]
        image = {
            "filename": "image_001.png",
            "content_type": "image/png",
            "object_path": "document-parser/2026/08/image_001.png",
            "signed_url": "/askai-api/api/files/document-parser/2026/08/image_001.png",
            "local_path": "/askai-api/api/files/document-parser/2026/08/image_001.png",
        }
        return {
            "resource_bundle": {"requested_types": ["images"], "source": "runtime_graph_parse"},
            "images": [image],
            "urls": [],
            "attachments": [],
        }

    async def fake_extract_image_facts(*, node, output_spec, user_text):
        captured["vision_input"] = output_spec["input_artifacts"]["images"][0]
        return {"images": [{"image_index": 1, "facts": ["three warehouses"]}]}

    monkeypatch.setattr(
        "app.enterprise_capabilities.runtime.adapters.runtime_parse_service.extract_resources",
        fake_extract_resources,
    )
    monkeypatch.setattr(
        "app.enterprise_capabilities.runtime.adapters.runtime_parse_service.extract_image_facts",
        fake_extract_image_facts,
    )
    monkeypatch.setattr(
        "app.enterprise_capabilities.artifacts.resource_result.AliyunOSSUploader",
        _Storage,
    )

    extracted = asyncio.run(document_extract_resources(
        {
            "artifacts": [{"object_path": "user-a/uploads/report.docx"}],
            "resource_types": ["images"],
        },
        _context(),
    ))
    image = extracted["images"][0]
    assert captured["parser_input"] == {"object_path": "user-a/uploads/report.docx"}
    assert image["object_path"] == "user-a/derived/image_001.png"
    assert "signed_url" not in image
    assert "local_path" not in image

    facts = asyncio.run(image_extract_facts({"images": [image]}, _context()))
    assert facts["success"] is True
    assert captured["vision_input"]["object_path"] == "user-a/derived/image_001.png"


def test_document_parse_embedded_images_use_the_same_owned_contract() -> None:
    projected = own_parsed_document_images(
        {
            "parsed_documents": [{
                "filename": "report.docx",
                "embedded_images": [{
                    "filename": "image_001.png",
                    "object_path": "document-parser/2026/08/image_001.png",
                    "signed_url": "/askai-api/api/files/document-parser/2026/08/image_001.png",
                }],
            }]
        },
        user_id="user-a",
        uploader=_Storage(),
    )
    image = projected["parsed_documents"][0]["embedded_images"][0]
    assert image["object_path"] == "user-a/derived/image_001.png"
    assert "signed_url" not in image


class _ScriptStorage:
    def upload_bytes_with_path(self, content, user_id, file_name, content_type=None):
        assert content.startswith(b"\x89PNG")
        assert user_id == "user-a"
        return "/askai-api/api/files/user-a/generated/chart.png", "user-a/generated/chart.png"

    def sign_url(self, object_path):
        return f"/askai-api/api/files/{object_path}"


def test_ordinary_script_auto_exports_generated_image(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.enterprise_capabilities.data.script_engine.artifact_export.AliyunOSSUploader",
        _ScriptStorage,
    )
    result = asyncio.run(run_script(
        {
            "code": (
                "payload = bytes.fromhex('89504e470d0a1a0a')\n"
                "with open(output_dir + '/chart.png', 'wb') as stream:\n"
                "    stream.write(payload)\n"
                "print('saved')"
            ),
            "delivery_scope": "final",
        },
        _context(),
    ))
    assert result["plugin_result"]["data"]["stdout"] == ["saved"]
    assert result["documents"] == []
    assert result["images"][0]["object_path"] == "user-a/generated/chart.png"
    assert result["exported_file"]["images"] == result["images"]


def test_browser_rejects_internal_artifact_routes_but_allows_public_pages() -> None:
    for value in (
        "/askai-api/api/files/user-a/image.png",
        "http://127.0.0.1:8000/api/files/user-a/image.png",
    ):
        try:
            reject_internal_artifact_target(value)
        except ValueError as exc:
            assert "object_path" in str(exc)
        else:
            raise AssertionError("internal artifacts must not be dispatched to Browser Agent")
    reject_internal_artifact_target("https://www.baidu.com/s?wd=AskBot")


def test_browser_service_rejects_artifact_before_dispatch_or_connection_check() -> None:
    try:
        asyncio.run(browser_task(
            {
                "objective": "inspect the image",
                "operation": "read",
                "target_url": "/askai-api/api/files/user-a/image.png",
            },
            _context(),
        ))
    except ValueError as exc:
        assert "image tool" in str(exc)
    else:
        raise AssertionError("internal artifacts must fail before Browser Agent dispatch")
