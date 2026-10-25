from pathlib import Path
import pytest
from openpyxl import Workbook
from zipfile import ZipFile

from app.services.document_parsing_service import parse_document
from app.services.pdf_text_recovery import supplement_pdf_chunks
from app.services.pdf_text_recovery import _missing_lines
from app.services.spreadsheet_ingest import normalized_workbook_path


SAMPLES = Path("/Users/jack/Downloads/测试文档")


def test_workbook_repair_preserves_original_and_other_entries(tmp_path):
    source = tmp_path / "source.xlsx"
    workbook = Workbook()
    workbook.active.title = "示例"
    workbook.active.append(["月份", "收入"])
    workbook.save(source)
    with ZipFile(source) as archive:
        entries = {item.filename: archive.read(item) for item in archive.infolist()}
    entries["xl/workbook.xml"] = entries["xl/workbook.xml"].replace(b'state="visible"', b'state="show"')
    with ZipFile(source, "w") as archive:
        for name, value in entries.items():
            archive.writestr(name, value)
    before = source.read_bytes()
    repaired, sheets = normalized_workbook_path(source, tmp_path)
    assert sheets == ["示例"]
    assert repaired != source
    assert source.read_bytes() == before
    assert parse_document(source, source.name).raw_chunks[0]["text"].startswith("工作表：示例")


def test_invalid_sheet_state_is_repaired_without_touching_source():
    path = SAMPLES / "北交所上市企业列表.xlsx"
    if not path.exists():
        pytest.skip("local document QA sample unavailable")
    before = path.read_bytes()
    parsed = parse_document(path, path.name)
    assert parsed.raw["normalizedSheetStates"] == ["sheet1"]
    assert parsed.raw_chunks
    assert path.read_bytes() == before


def test_sheet_name_and_headers_are_searchable():
    path = SAMPLES / "门店销售数据表.xlsx"
    if not path.exists():
        pytest.skip("local document QA sample unavailable")
    parsed = parse_document(path, path.name)
    summary = parsed.raw_chunks[0]["text"]
    assert "工作表：Sheet1" in summary
    assert all(name in summary for name in ("一月收入", "二月收入", "三月收入"))


def test_pdf_page_three_missing_text_is_recovered():
    path = SAMPLES / "火山引擎AI 一体机核心介绍v1.0.pdf"
    if not path.exists():
        pytest.skip("local document QA sample unavailable")
    parsed_page = [{"text": "火山引擎 AI 一体机 Serving Kit 竞争力", "pageNo": 3}]
    chunks, quality = supplement_pdf_chunks(path, parsed_page)
    assert 3 in quality["recoveredPages"]
    assert any("综合性价比提升50%+" in chunk["text"].replace(" ", "") for chunk in chunks)


def test_attendance_pdf_page_one_hr_duty_is_recovered():
    path = SAMPLES / "员工考勤及假期管理规定.pdf"
    if not path.exists():
        pytest.skip("local document QA sample unavailable")
    chunks, quality = supplement_pdf_chunks(path, [
        {"text": "3.1 人力资源部：", "pageNo": 1},
        {"text": "4.1 考勤班次", "pageNo": 1},
    ])
    assert 1 in quality["recoveredPages"]
    assert any("负责按月汇总公司考勤记录并抽查" in chunk["text"] for chunk in chunks)


def test_workwear_pdf_recovers_local_omissions_on_otherwise_readable_page():
    path = SAMPLES / "工装挂历制度.pdf"
    if not path.exists():
        pytest.skip("local document QA sample unavailable")
    from pypdf import PdfReader

    page = PdfReader(str(path)).pages[1].extract_text() or ""
    omitted = ("5.3.2", "每年 3、9 月", "72.22%")
    partial = "\n".join(line for line in page.splitlines() if not any(term in line for term in omitted))
    chunks, quality = supplement_pdf_chunks(path, [{"text": partial, "pageNo": 2}])
    recovered = "\n".join(item["text"] for item in chunks if item.get("metadata", {}).get("sourceKind") == "native_text_recovery")
    assert 2 in quality["recoveredPages"]
    assert "实习期间等非正式用" in recovered
    assert "每年 3、9 月" in recovered
    assert "72.22%" in recovered


def test_short_percentage_omission_is_not_lost_inside_readable_page():
    assert _missing_lines("综合性能\n25%+\n其他说明", "综合性能\n其他说明") == ["25%+"]


def test_pdf_parse_pipeline_preserves_recovered_text(monkeypatch):
    path = SAMPLES / "火山引擎AI 一体机核心介绍v1.0.pdf"
    if not path.exists():
        pytest.skip("local document QA sample unavailable")
    from app.services import document_parsing_service as parsing

    class _Document:
        def export_to_markdown(self):
            return "火山引擎 AI 一体机 Serving Kit 竞争力"

        def export_to_dict(self):
            return {"parser": "docling"}

    class _Converter:
        def convert(self, _path):
            return type("Result", (), {"document": _Document()})()

    monkeypatch.setattr(parsing, "_build_docling_converter", lambda *_args, **_kwargs: _Converter())
    monkeypatch.setattr(parsing, "chunk_docling_document", lambda *_args, **_kwargs: [{
        "chunkId": "raw_000001", "ordinal": 0, "pageNo": 3,
        "text": "火山引擎 AI 一体机 Serving Kit 竞争力", "contentType": "text",
    }])
    parsed = parsing.parse_document(path, path.name)
    rag = parsing.build_rag_chunks(parsed.raw_chunks)
    assert 3 in parsed.raw["movoParseQuality"]["recoveredPages"]
    assert any("综合性价比提升50%+" in chunk["text"].replace(" ", "") for chunk in rag)
