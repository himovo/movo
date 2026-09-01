from __future__ import annotations

import os
from pathlib import Path

from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.pipeline.standard_pdf_pipeline import StandardPdfPipeline


def main() -> None:
    artifacts_path = Path(os.environ.get("DOCLING_ARTIFACTS_PATH", "/opt/docling/models"))
    if not artifacts_path.is_dir() or not any(artifacts_path.rglob("*")):
        raise RuntimeError(f"Docling model assets are missing: {artifacts_path}")
    StandardPdfPipeline(PdfPipelineOptions(artifacts_path=artifacts_path))
    print(f"Docling offline runtime ready: {artifacts_path}")


if __name__ == "__main__":
    main()
