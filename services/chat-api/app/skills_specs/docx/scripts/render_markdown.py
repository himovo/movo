from __future__ import annotations

import argparse
from pathlib import Path

from app.tools.docx import generate_docx_file


def main() -> None:
    parser = argparse.ArgumentParser(description="Render markdown to DOCX using default project formatting.")
    parser.add_argument("input", help="Path to markdown file")
    parser.add_argument("output", nargs="?", default="report.docx", help="Output .docx filename")
    args = parser.parse_args()

    md_path = Path(args.input).expanduser().resolve()
    if not md_path.exists():
        raise SystemExit(f"Input not found: {md_path}")

    content = md_path.read_text(encoding="utf-8")
    output = generate_docx_file(content, filename=args.output)
    print(output)


if __name__ == "__main__":
    main()
