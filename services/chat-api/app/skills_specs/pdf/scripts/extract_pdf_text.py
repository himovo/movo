#!/usr/bin/env python3
"""
Extract main text from a PDF using pdfplumber with a pypdf fallback.

Usage:
  python extract_pdf_text.py /path/to/file.pdf > output.txt
  python extract_pdf_text.py /path/to/file.pdf --max-pages 20 --layout
"""

from __future__ import annotations

import argparse
import sys
from typing import Optional


def _extract_with_pdfplumber(path: str, max_pages: Optional[int], layout: bool) -> str:
    try:
        import pdfplumber
    except ImportError:
        print("Warning: pdfplumber not installed.", file=sys.stderr)
        return ""

    texts = []
    try:
        with pdfplumber.open(path) as pdf:
            pages = pdf.pages
            if max_pages is not None:
                pages = pages[:max_pages]
            for page in pages:
                if layout:
                    text = page.extract_text(x_tolerance=2, y_tolerance=2, layout=True) or ""
                else:
                    text = page.extract_text() or ""
                if text:
                    texts.append(text)
    except Exception as e:
        print(f"Warning: pdfplumber failed: {e}", file=sys.stderr)
        return ""
    return "\n\n".join(texts).strip()


def _extract_with_pypdf(path: str, max_pages: Optional[int]) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        print("Warning: pypdf not installed.", file=sys.stderr)
        return ""

    try:
        reader = PdfReader(path)
        texts = []
        pages = reader.pages
        if max_pages is not None:
            pages = pages[:max_pages]
        for page in pages:
            text = page.extract_text() or ""
            if text:
                texts.append(text)
        return "\n\n".join(texts).strip()
    except Exception as e:
        print(f"Warning: pypdf failed: {e}", file=sys.stderr)
        return ""


def extract_text(path: str, max_pages: Optional[int], layout: bool) -> str:
    try:
        text = _extract_with_pdfplumber(path, max_pages, layout)
        if text:
            return text
    except Exception:
        pass
    try:
        text = _extract_with_pypdf(path, max_pages)
        if text:
            return text
    except Exception:
        pass
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract text from a PDF.")
    parser.add_argument("pdf_path", help="Path to the PDF file.")
    parser.add_argument("--max-pages", type=int, default=None, help="Limit pages to extract.")
    parser.add_argument("--layout", action="store_true", help="Use layout-aware extraction.")
    args = parser.parse_args()

    text = extract_text(args.pdf_path, args.max_pages, args.layout)
    if not text:
        print("No text extracted.", file=sys.stderr)
        return 2
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
