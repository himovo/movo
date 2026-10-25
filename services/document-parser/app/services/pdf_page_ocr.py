"""OCR a PDF page when Docling produced no chunk anchored to that page."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import re


@lru_cache(maxsize=1)
def _ocr_engine():
    from rapidocr import RapidOCR

    return RapidOCR()


def extract_page_ocr_text(path: Path, page_no: int) -> str:
    import numpy as np
    from pypdfium2 import PdfDocument

    pdf = PdfDocument(str(path))
    try:
        image = pdf[page_no - 1].render(scale=2).to_pil().convert("RGB")
        result = _ocr_engine()(np.asarray(image))
        texts = list(getattr(result, "txts", None) or ())
        scores = list(getattr(result, "scores", None) or ())
        lines: list[str] = []
        for index, item in enumerate(texts):
            line = str(item).strip()
            score = float(scores[index]) if index < len(scores) else 0.0
            meaningful = re.findall(r"[\w\u3400-\u9fff]", line)
            if score < 0.9 or len(meaningful) < 2:
                continue
            if len(meaningful) < 5 and not re.search(r"[\u3400-\u9fff\d]", line):
                continue
            lines.append(line)
        return "\n".join(lines)
    finally:
        pdf.close()


__all__ = ["extract_page_ocr_text"]
