from __future__ import annotations

import json
import re
from typing import Optional
from urllib.parse import unquote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from app.services.documents import document_service
from app.api.principal import require_end_user_principal
from app.services.local_file_signing import verify_local_file_signature

router = APIRouter()


class DocumentRenderRequest(BaseModel):
    user_id: str = Field(..., description="User ID from login")
    content: str = Field(..., description="Markdown content to render")
    format: str = Field(..., description="Document format: pdf, docx, md, or markdown")
    filename: Optional[str] = Field(None, description="Optional filename")
    title: Optional[str] = Field(None, description="Optional document title")


class DocumentSignRequest(BaseModel):
    user_id: str = Field(..., description="User ID from login")
    object_path: str = Field(..., description="OSS object path")
    expires: Optional[int] = Field(None, description="Signed URL expiration in seconds")


class ApiResponse(BaseModel):
    code: int = 0
    message: Optional[str] = None
    data: Optional[object] = None


@router.post(
    "/documents/render",
    response_model=ApiResponse,
    dependencies=[Depends(require_end_user_principal)],
)
async def render_document(payload: DocumentRenderRequest) -> ApiResponse:
    fmt = payload.format.lower()
    if fmt not in {"pdf", "docx", "md", "markdown"}:
        raise HTTPException(status_code=400, detail="Unsupported document format")
    result = await document_service.render(
        payload.content,
        user_id=str(payload.user_id),
        format=fmt,
        filename=payload.filename,
        title=payload.title,
    )
    return ApiResponse(code=0, message="success", data=result)


@router.post(
    "/documents/sign",
    response_model=ApiResponse,
    dependencies=[Depends(require_end_user_principal)],
)
async def sign_document(payload: DocumentSignRequest) -> ApiResponse:
    from app.utils.object_storage import ObjectStorageClient

    uploader = ObjectStorageClient()
    object_path = unquote(payload.object_path)
    signed = uploader.sign_url(object_path, payload.expires)
    return ApiResponse(code=0, message="success", data={"url": signed})


class DocumentFetchRequest(BaseModel):
    user_id: str = Field(..., description="User ID from login")
    object_path: str = Field(..., description="OSS object path")


class PresentationPptxRenderRequest(BaseModel):
    user_id: str = Field(..., description="User ID from login")
    blueprint_object_path: str = Field(..., description="blueprint JSON artifact path in OSS")
    filename: Optional[str] = Field(None, description="Optional filename")
    title: Optional[str] = Field(None, description="Optional document title")


class SaveBlueprintRequest(BaseModel):
    user_id: str = Field(..., description="User ID from login")
    blueprint_object_path: str = Field(..., description="Original blueprint path to overwrite")
    blueprint: dict = Field(..., description="Updated blueprint JSON")


@router.post(
    "/documents/save-blueprint",
    response_model=ApiResponse,
    dependencies=[Depends(require_end_user_principal)],
)
async def save_blueprint(payload: SaveBlueprintRequest) -> ApiResponse:
    """Save an edited blueprint back to the configured storage backend."""
    import json
    from app.utils.object_storage import ObjectStorageClient

    uploader = ObjectStorageClient()
    content = json.dumps(payload.blueprint, ensure_ascii=False, indent=2).encode("utf-8")
    object_path = payload.blueprint_object_path
    uploader.write_bytes(object_path, content, content_type="application/json; charset=utf-8")
    signed_url = uploader.sign_url(object_path)
    return ApiResponse(code=0, message="success", data={
        "object_path": object_path,
        "url": signed_url,
    })


@router.post(
    "/documents/render-presentation-pptx",
    response_model=ApiResponse,
    dependencies=[Depends(require_end_user_principal)],
)
async def render_presentation_pptx(payload: PresentationPptxRenderRequest) -> ApiResponse:
    result = await document_service.render_presentation_pptx(
        user_id=str(payload.user_id),
        blueprint_object_path=str(payload.blueprint_object_path or ""),
        filename=payload.filename,
        title=payload.title,
    )
    return ApiResponse(code=0, message="success", data=result)


@router.get("/icons/{icon_name}.svg")
async def get_icon_svg(icon_name: str, color: Optional[str] = None, size: int = 96) -> Response:
    """Serve a Tabler icon SVG by name, pre-processed for Fabric.js compatibility.

    Tabler icons put fill/stroke on the <svg> root, but Fabric.js SVG parser
    doesn't inherit parent attributes onto child elements. This endpoint injects
    fill/stroke directly onto each <path>, <circle>, <line>, <polyline>, <rect>
    so Fabric renders them correctly as stroked vector shapes.
    """
    from app.services.presentation.icon_library import resolve_icon_name, load_inline_svg_map

    resolved = resolve_icon_name(icon_name, fallback="sparkles")
    svg_map = load_inline_svg_map()
    svg = svg_map.get(resolved, "")
    if not svg:
        raise HTTPException(status_code=404, detail="Icon not found")

    # Determine stroke color
    stroke_color = "currentColor"
    if color:
        stroke_color = color if color.startswith("#") else f"#{color}"
    svg = svg.replace("currentColor", stroke_color)

    # Inject fill/stroke/linecap/linejoin onto every child shape element.
    # Browsers rendering SVG inside <img> do NOT inherit attrs from <svg> root.
    shape_tags = ("path", "circle", "line", "polyline", "polygon", "rect", "ellipse")
    inject_attrs = {
        "fill": "none",
        "stroke": stroke_color,
        "stroke-width": "2",
        "stroke-linecap": "round",
        "stroke-linejoin": "round",
    }
    for tag in shape_tags:
        for attr, val in inject_attrs.items():
            svg = re.sub(
                rf"<{tag}\b(?![^>]*\b{attr}=)",
                f'<{tag} {attr}="{val}"',
                svg,
            )

    # Keep SVG at native 24x24 — the consumer (Fabric / browser) scales via
    # the viewBox.  Do NOT change width/height here; earlier versions set them
    # to `size` which broke Fabric's scale calculation.

    return Response(content=svg, media_type="image/svg+xml",
                    headers={"Cache-Control": "public, max-age=86400"})


class RenderChartSvgRequest(BaseModel):
    chart_type: str = Field(..., description="bar, line, or pie")
    chart_data: dict = Field(default_factory=dict)
    width: int = Field(640)
    height: int = Field(360)
    theme: dict = Field(default_factory=dict)


@router.post(
    "/documents/render-chart-svg",
    dependencies=[Depends(require_end_user_principal)],
)
async def render_chart_svg_endpoint(payload: RenderChartSvgRequest) -> Response:
    """Render a chart as SVG for the presentation editor."""
    from app.services.presentation.chart_svg_renderer import render_chart_svg

    w = max(100, min(payload.width, 1600))
    h = max(80, min(payload.height, 900))
    svg = render_chart_svg(
        chart_type=payload.chart_type,
        payload=payload.chart_data,
        theme=payload.theme,
        width=w,
        height=h,
    )
    if not svg:
        raise HTTPException(status_code=400, detail="Unsupported chart type")
    # Fix for Fabric.js: use fixed pixel size instead of 100%
    svg = svg.replace('width="100%"', f'width="{w}"').replace('height="100%"', f'height="{h}"')
    # Make background transparent so chart overlays correctly on canvas
    svg = re.sub(
        r'<rect x="0" y="0" width="\d+" height="\d+" rx="\d+" fill="[^"]*"/>',
        '',
        svg,
        count=1,
    )
    return Response(content=svg, media_type="image/svg+xml",
                    headers={"Cache-Control": "public, max-age=300"})


class DocumentRefreshMarkdownRequest(BaseModel):
    user_id: str = Field(..., description="User ID from login")
    content: str = Field("", description="Markdown content")


@router.post(
    "/documents/refresh-markdown-urls",
    dependencies=[Depends(require_end_user_principal)],
)
async def refresh_markdown_urls(payload: DocumentRefreshMarkdownRequest):
    from app.utils.object_storage import ObjectStorageClient

    uploader = ObjectStorageClient()
    refreshed = uploader.refresh_markdown_urls(payload.content or "")
    return StreamingResponse(
        iter([refreshed.encode("utf-8")]),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": "inline"},
    )


@router.post(
    "/documents/fetch",
    dependencies=[Depends(require_end_user_principal)],
)
async def fetch_document(payload: DocumentFetchRequest):
    from app.utils.object_storage import ObjectStorageClient

    uploader = ObjectStorageClient()
    object_path = unquote(payload.object_path)
    content_type = uploader.guess_content_type(object_path)
    content_bytes = uploader.read_bytes(object_path)
    is_markdown_doc = object_path.lower().endswith(".md") or "markdown" in content_type.lower()
    is_text_doc = content_type.lower().startswith("text/")

    if (is_markdown_doc or is_text_doc) and content_bytes:
        try:
            text = content_bytes.decode("utf-8", errors="ignore")
            refreshed = uploader.refresh_markdown_urls(text)
            content_bytes = refreshed.encode("utf-8")
            if is_markdown_doc:
                content_type = "text/markdown; charset=utf-8"
        except Exception:
            pass
    elif _is_presentation_blueprint_path(object_path) and content_bytes:
        try:
            payload_json = json.loads(content_bytes.decode("utf-8", errors="strict"))
            refreshed_json, refreshed_count = uploader.refresh_json_urls(payload_json)
            if refreshed_count > 0:
                content_bytes = json.dumps(refreshed_json, ensure_ascii=False).encode("utf-8")
            content_type = "application/json; charset=utf-8"
        except Exception:
            pass

    return StreamingResponse(
        iter([content_bytes]),
        media_type=content_type,
        headers={"Content-Disposition": "inline"},
    )


def _is_presentation_blueprint_path(object_path: str) -> bool:
    filename = str(object_path or "").rsplit("/", 1)[-1].lower()
    return filename.startswith("presentation_blueprint") and filename.endswith(".json")


@router.get("/files/{object_path:path}")
async def get_stored_file(
    object_path: str,
    expires: int = Query(...),
    signature: str = Query(..., min_length=32, max_length=128),
):
    from app.core.config import get_settings
    from app.utils.object_storage import ObjectStorageClient

    if str(get_settings().STORAGE_BACKEND or "oss").strip().lower() != "local":
        raise HTTPException(status_code=404, detail="File proxy is only available for local storage")
    uploader = ObjectStorageClient()
    path = unquote(object_path)
    if not verify_local_file_signature(
        path,
        expires_at=expires,
        signature=signature,
        secret=str(get_settings().END_USER_AUTH_SECRET or ""),
    ):
        raise HTTPException(status_code=403, detail="Invalid or expired file URL")
    file_path = uploader.local_file_path(path)
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    media_type = uploader.guess_content_type(path)
    return FileResponse(file_path, media_type=media_type)
