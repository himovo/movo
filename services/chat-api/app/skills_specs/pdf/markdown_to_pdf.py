from __future__ import annotations

# Thin wrappers to expose PDF generation capability in skills_specs/pdf
# This reuses the existing implementation in app.tools.pdf.

from app.tools.pdf import generate_pdf_file, render_pdf_from_markdown

__all__ = ["generate_pdf_file", "render_pdf_from_markdown"]
