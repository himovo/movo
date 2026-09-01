import asyncio

from app.enterprise_capabilities.content.writer_engine.pipeline import WriterEnginePipeline


def test_explicit_chinese_target_wins_even_when_source_is_misdetected_as_chinese():
    pipeline = WriterEnginePipeline.__new__(WriterEnginePipeline)

    target = asyncio.run(
        pipeline._detect_target_language(
            "请下载这个文件，然后翻译为中文。",
            source_language="Chinese",
        )
    )

    assert target == "Chinese"


def test_explicit_english_target_is_extracted_without_llm():
    pipeline = WriterEnginePipeline.__new__(WriterEnginePipeline)

    target = asyncio.run(
        pipeline._detect_target_language(
            "把这份报告翻译成英文版本",
            source_language="Chinese",
        )
    )

    assert target == "English"


def test_source_language_ignores_chinese_embedded_image_placeholders():
    markdown = (
        "## Page 1\n\n"
        "【内嵌图片：第 1 页，图片 1】\n\n"
        "March Quarter 2026 Results\n\n"
        "This presentation contains financial results and forward-looking statements."
    )

    assert WriterEnginePipeline._detect_source_language(markdown) == "English"
