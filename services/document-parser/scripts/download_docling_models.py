from __future__ import annotations

import os
from pathlib import Path

from docling.models.stages.ocr.rapid_ocr_model import RapidOcrModel
from docling.utils.model_downloader import download_models


def main() -> None:
    output_dir = Path(os.environ.get("DOCLING_ARTIFACTS_PATH", "/opt/docling/models"))
    output_dir.mkdir(parents=True, exist_ok=True)
    download_models(
        output_dir=output_dir,
        progress=True,
        with_layout=True,
        with_tableformer=True,
        with_code_formula=False,
        with_picture_classifier=False,
        with_rapidocr=False,
    )
    RapidOcrModel.download_models(
        backend="onnxruntime",
        local_dir=output_dir / RapidOcrModel._model_repo_folder,
        progress=True,
    )


if __name__ == "__main__":
    main()
