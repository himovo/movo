from __future__ import annotations

import argparse
from pathlib import Path

import asyncio

from app.tools.pdf import render_pdf_from_markdown


def main() -> None:
    parser = argparse.ArgumentParser(description="Render markdown to PDF using default project formatting.")
    parser.add_argument("input", help="Path to markdown file")
    parser.add_argument("output", nargs="?", default="report.pdf", help="Output .pdf filename")
    parser.add_argument("--user", default="anonymous", help="User id for asset rendering/upload context")
    args = parser.parse_args()

    md_path = Path(args.input).expanduser().resolve()
    if not md_path.exists():
        raise SystemExit(f"Input not found: {md_path}")

    content = md_path.read_text(encoding="utf-8")
    url = asyncio.run(render_pdf_from_markdown(content, args.user, args.output))
    print(url)


if __name__ == "__main__":
    main()
