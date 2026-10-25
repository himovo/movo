from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

from app.services.pdf_text_recovery import supplement_pdf_chunks


def _reader(monkeypatch, text: str, *, images: bool = False) -> None:
    page = SimpleNamespace(extract_text=lambda: text, images=[object()] if images else [])
    monkeypatch.setitem(sys.modules, "pypdf", SimpleNamespace(PdfReader=lambda _: SimpleNamespace(pages=[page])))


def test_short_native_page_without_docling_chunk_is_recovered(monkeypatch):
    _reader(monkeypatch, "修改后重新登录。")
    chunks, quality = supplement_pdf_chunks(Path("sample.pdf"), [])
    assert chunks[0]["pageNo"] == 1
    assert chunks[0]["text"] == "修改后重新登录。"
    assert quality["recoveredPages"] == [1]
    assert quality["reviewPages"] == []
    assert quality["pages"][0]["finalNativeCoverage"] == 1.0


def test_image_page_supplements_native_text_with_ocr(monkeypatch):
    _reader(monkeypatch, "操作步骤见图。", images=True)
    from app.services import pdf_page_ocr

    monkeypatch.setattr(pdf_page_ocr, "extract_page_ocr_text", lambda *_: "操作步骤见图。\n点击修改密码并保存设置")
    chunks, quality = supplement_pdf_chunks(Path("sample.pdf"), [])
    assert "点击修改密码并保存设置" in chunks[0]["text"]
    assert quality["pages"][0]["ocrAttempted"] is True
    assert quality["reviewPages"] == []


def test_unreadable_image_page_keeps_internal_diagnostic(monkeypatch):
    _reader(monkeypatch, "", images=True)
    from app.services import pdf_page_ocr

    monkeypatch.setattr(pdf_page_ocr, "extract_page_ocr_text", lambda *_: "")
    chunks, quality = supplement_pdf_chunks(Path("sample.pdf"), [])
    assert chunks == []
    assert quality["reviewPages"] == [1]


def test_short_native_clause_is_recovered_on_existing_text_page(monkeypatch):
    body = "常规规定文字内容覆盖本页其他段落。" * 12
    _reader(monkeypatch, body + "\n严禁申领")
    chunks, quality = supplement_pdf_chunks(Path("sample.pdf"), [{"text": body, "pageNo": 1}])
    assert any("严禁申领" in chunk["text"] for chunk in chunks[1:])
    assert quality["pages"][0]["nativeChars"] > 80


def test_image_text_is_recovered_even_when_page_has_other_chunks(monkeypatch):
    _reader(monkeypatch, "页眉与说明文字。", images=True)
    from app.services import pdf_page_ocr

    monkeypatch.setattr(pdf_page_ocr, "extract_page_ocr_text", lambda *_: "页眉与说明文字。\n图片中的办理条件")
    chunks, quality = supplement_pdf_chunks(Path("sample.pdf"), [{"text": "页眉与说明文字。", "pageNo": 1}])
    assert any("图片中的办理条件" in chunk["text"] for chunk in chunks[1:])
    assert quality["pages"][0]["ocrAttempted"] is True


def test_page_ocr_discards_low_confidence_and_keyboard_noise(monkeypatch):
    from PIL import Image
    from app.services import pdf_page_ocr

    class _Pdf:
        def __getitem__(self, _index):
            return SimpleNamespace(render=lambda **_: SimpleNamespace(
                to_pil=lambda: Image.new("RGB", (10, 10)),
            ))

        def close(self):
            pass

    monkeypatch.setitem(sys.modules, "pypdfium2", SimpleNamespace(PdfDocument=lambda _: _Pdf()))
    monkeypatch.setattr(pdf_page_ocr, "_ocr_engine", lambda: lambda _: SimpleNamespace(
        txts=["W", "Alt", "&@柳月青", "新密码", "点击修改密码并保存"],
        scores=[0.99, 0.99, 0.85, 0.98, 0.99],
    ))
    assert pdf_page_ocr.extract_page_ocr_text(Path("sample.pdf"), 1) == "新密码\n点击修改密码并保存"
