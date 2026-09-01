from __future__ import annotations

import asyncio
from hashlib import sha256
from io import BytesIO

import pytest
from pypdf import PdfReader, PdfWriter

from app.enterprise_capabilities.pdf_editing import pdf_retain_pages, retain_pdf_pages
from app.enterprise_capabilities.runtime import CapabilityExecutionContext, InternalCapabilityCatalog
from app.governance.position_policy import CAPABILITY_KEYS, EffectiveEmployeePolicy


def _source_pdf(page_count: int = 5) -> bytes:
    output = BytesIO()
    writer = PdfWriter()
    for page in range(1, page_count + 1):
        writer.add_blank_page(width=590 + page, height=840 + page)
    writer.write(output)
    return output.getvalue()


def _context() -> CapabilityExecutionContext:
    return CapabilityExecutionContext(
        tenant_id="tenant-a",
        user_id="user-a",
        conversation_id="conversation-a",
        kernel_session_id="session-a",
        profile_version="profile-a",
        action_id="action-a",
    )


def test_retain_pdf_pages_preserves_selected_source_pages_and_order() -> None:
    source = _source_pdf()
    source_hash = sha256(source).hexdigest()

    result = retain_pdf_pages(source, [5, 2, 2])

    assert result.kept_pages == (2, 5)
    assert result.removed_pages == (1, 3, 4)
    assert result.source_page_count == 5
    assert sha256(source).hexdigest() == source_hash
    output = PdfReader(BytesIO(result.file_bytes))
    assert len(output.pages) == 2
    assert float(output.pages[0].mediabox.width) == 592
    assert float(output.pages[1].mediabox.width) == 595


@pytest.mark.parametrize("keep_pages", [[], [0], [6], [1.0], [True]])
def test_retain_pdf_pages_rejects_invalid_page_selections(keep_pages) -> None:
    with pytest.raises(ValueError):
        retain_pdf_pages(_source_pdf(), keep_pages)


def test_retain_pdf_pages_rejects_password_protected_pdf() -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.encrypt("secret")
    output = BytesIO()
    writer.write(output)

    with pytest.raises(ValueError, match="encrypted PDF"):
        retain_pdf_pages(output.getvalue(), [1])


def test_pdf_retain_pages_service_uses_owned_storage_and_returns_final_artifact(monkeypatch) -> None:
    source = _source_pdf(4)
    uploaded: dict[str, object] = {}

    class Storage:
        def read_bytes(self, object_path: str) -> bytes:
            assert object_path == "user-a/uploads/product.pdf"
            return source

        def upload_bytes_with_path(self, content, user_id, file_name, content_type=None):
            uploaded.update(
                content=content,
                user_id=user_id,
                filename=file_name,
                content_type=content_type,
            )
            return "/askai-api/api/files/user-a/derived/customer.pdf", "user-a/derived/customer.pdf"

    monkeypatch.setattr(
        "app.enterprise_capabilities.artifacts.storage.AliyunOSSUploader",
        Storage,
    )
    result = asyncio.run(pdf_retain_pages(
        {
            "artifact": {
                "object_path": "user-a/uploads/product.pdf",
                "filename": "product.pdf",
                "signed_url": "must-not-be-trusted",
            },
            "keep_pages": [1, 4],
            "filename": "customer-version",
        },
        _context(),
    ))

    assert uploaded["user_id"] == "user-a"
    assert uploaded["filename"] == "customer-version.pdf"
    assert uploaded["content_type"] == "application/pdf"
    assert len(PdfReader(BytesIO(uploaded["content"])).pages) == 2
    assert result["artifact"] == {
        "object_path": "user-a/derived/customer.pdf",
        "filename": "customer-version.pdf",
        "content_type": "application/pdf",
        "size": len(uploaded["content"]),
        "lifecycle": "final",
        "visibility": "user",
    }
    assert result["selection"]["kept_pages"] == [1, 4]
    assert result["selection"]["removed_pages"] == [2, 3]
    assert result["selection"]["source_unchanged"] is True


def test_pdf_retain_pages_rejects_cross_user_source_before_storage_read(monkeypatch) -> None:
    class Storage:
        def read_bytes(self, _object_path: str) -> bytes:
            raise AssertionError("cross-user artifacts must fail before storage access")

    monkeypatch.setattr(
        "app.enterprise_capabilities.artifacts.storage.AliyunOSSUploader",
        Storage,
    )
    with pytest.raises(PermissionError):
        asyncio.run(pdf_retain_pages(
            {
                "artifact": {"object_path": "user-b/private/product.pdf", "filename": "product.pdf"},
                "keep_pages": [1],
            },
            _context(),
        ))


def test_pdf_retain_pages_is_a_dsh_tool_governed_by_content_generation() -> None:
    definition = next(
        item for item in InternalCapabilityCatalog().definitions()
        if item.capability_ref == "document.pdf_retain_pages@v1"
    )
    assert definition.tool_name == "pdf_retain_pages"
    assert definition.display_name == "精简 PDF 页面"
    assert "performs no semantic selection" in definition.description
    assert set(definition.input_schema["required"]) == {"artifact", "keep_pages"}

    enabled_policy = EffectiveEmployeePolicy(
        tenant_id="tenant-a",
        user_id="user-a",
        capabilities={**{key: False for key in CAPABILITY_KEYS}, "content_generation": True},
    )
    disabled_policy = EffectiveEmployeePolicy(
        tenant_id="tenant-a",
        user_id="user-a",
        capabilities={key: False for key in CAPABILITY_KEYS},
    )
    assert enabled_policy.allows_internal(definition.capability_ref) is True
    assert disabled_policy.allows_internal(definition.capability_ref) is False
