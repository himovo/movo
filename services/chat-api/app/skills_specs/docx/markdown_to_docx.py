from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from app.tools.docx import generate_docx_file


def _resolve_template() -> Optional[str]:
    base = Path(__file__).resolve().parent
    candidates = [
        base / "templates" / "report_template.docx",
        base / "templates" / "report.docx",
    ]
    for path in candidates:
        if path.exists():
            return str(path)
    return None


def render_from_markdown(
    markdown: str,
    filename: str = "report.docx",
    *,
    return_metadata: bool = False,
    cover_title: Optional[str] = None,
    skip_cover: bool = False,
    skip_toc: bool = False,
) -> str | Dict[str, Any]:
    template = _resolve_template()
    return generate_docx_file(
        markdown,
        filename=filename,
        template_path=template,
        return_metadata=return_metadata,
        cover_title=cover_title,
        skip_cover=skip_cover,
        skip_toc=skip_toc,
    )


__all__ = ["render_from_markdown"]
