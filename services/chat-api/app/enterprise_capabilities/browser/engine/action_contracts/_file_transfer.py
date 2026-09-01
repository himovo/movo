"""browser.file_transfer — upload or download a file."""
from __future__ import annotations

from typing import Any, Dict

from .schema import BrowserActionSpec, ContractResult


_VALID_DIRECTIONS = {"upload", "download"}


def _validate(data: Dict[str, Any]) -> ContractResult:
    if not isinstance(data, dict):
        return ContractResult(ok=False, reason="browser_done.data must be an object", missing=["file"])
    f = data.get("file")
    if not isinstance(f, dict) or not f:
        return ContractResult(
            ok=False,
            reason="file missing — a file_transfer task must describe what was moved",
            missing=["file"],
        )
    direction = str(f.get("direction") or "").strip().lower()
    if direction not in _VALID_DIRECTIONS:
        return ContractResult(
            ok=False,
            reason="file.direction must be 'upload' or 'download'",
            missing=["file.direction"],
        )
    path_or_url = str(f.get("path_or_url") or f.get("url") or f.get("path") or "").strip()
    if not path_or_url:
        return ContractResult(
            ok=False,
            reason="file.path_or_url missing — report where the file ended up (local path for download, server URL for upload)",
            missing=["file.path_or_url"],
        )
    return ContractResult(ok=True)


SPEC = BrowserActionSpec(
    capability_id="browser.file_transfer",
    name_zh="上传/下载",
    name_en="File transfer",
    description_zh="上传文件到网站，或者从网站下载文件（导出报表、上传图片）",
    description_en="Upload a file to the site, or download one from it (export report, upload image)",
    produces=("file",),
    data_schema_hint_zh=(
        '{"file": {"direction": "upload"|"download", '
        '"path_or_url": "<下载目的地的本地路径, 或上传后服务端 URL>", '
        '"filename": "<文件名, 可选>", "size": <字节数, 可选>}}'
    ),
    data_schema_hint_en=(
        '{"file": {"direction": "upload"|"download", '
        '"path_or_url": "<local path for download target, or server URL after upload>", '
        '"filename": "<optional>", "size": <optional bytes>}}'
    ),
    validate=_validate,
)
