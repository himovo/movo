from app.services.document_parsing_service import _clean_chunk_text
from app.services.rag_chunk_optimizer import RagChunkOptions, build_rag_chunks


def test_short_semantic_lines_survive_parsing_and_index_chunking():
    assert _clean_chunk_text("适用范围\n禁止\n5 天") == "适用范围\n禁止\n5 天"
    chunks = build_rag_chunks([{"chunkId": "raw_1", "text": "禁止", "contentType": "text"}])
    assert [chunk["text"] for chunk in chunks] == ["禁止"]


def test_separator_only_lines_remain_excluded():
    assert _clean_chunk_text("适用范围\n---\n其他说明") == "适用范围\n其他说明"
    assert build_rag_chunks([{"chunkId": "raw_1", "text": "---", "contentType": "text"}]) == []


def test_oversized_table_row_is_split_without_losing_its_end():
    text = "表格行 8\n" + "适用条件说明" * 250
    chunks = build_rag_chunks(
        [{"chunkId": "raw_1", "text": text, "contentType": "table_row"}],
        RagChunkOptions(max_tokens=300),
    )
    assert len(chunks) > 1
    assert all(chunk["metadata"]["tokenEstimate"] <= 300 for chunk in chunks)
    assert all(chunk["text"].startswith("表格行 8\n") for chunk in chunks)
    assert "".join(chunk["text"].removeprefix("表格行 8\n") for chunk in chunks) == text.split("\n", 1)[1]
