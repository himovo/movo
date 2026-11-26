"""Edit only images already attached to an authorized conversation message."""

from urllib.parse import urlsplit, unquote

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.principal import ApiPrincipal, require_end_user_principal
from app.core.db import get_db
from app.dsh_runtime.session_access import SessionReadAuthorizer, SessionReadDeniedError
from app.dsh_runtime.projected_documents import projected_documents
from app.services.image_editing import edit_image_asset
from app.services.image_edit_model import ImageEditModelError

router = APIRouter()


class ImageEditRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)
    object_path: str = ""
    source_url: str = Field(default="", max_length=10000)
    image_model_id: str = Field(default="", max_length=200)


def url_identity(value: str) -> tuple[str, str]:
    parsed = urlsplit(value)
    return parsed.netloc.lower(), unquote(parsed.path)


def source_document(message: dict, request: ImageEditRequest) -> dict | None:
    documents = [*(message.get("documents") or []), *(message.get("images") or []),
                 *projected_documents(message.get("execution_events") or [], [])]
    for document in documents:
        path = str(document.get("object_path") or "")
        if not path:
            continue
        mime = str(document.get("content_type") or "")
        if not mime.startswith("image/") and path.lower().rsplit(".", 1)[-1] not in {"png", "jpg", "jpeg", "webp", "gif", "avif"}:
            continue
        if request.object_path and path == request.object_path:
            return document
        if not request.object_path and request.source_url and any(
            url_identity(request.source_url) == url_identity(str(document.get(key) or ""))
            for key in ("url", "signed_url") if document.get(key)
        ):
            return document
    return None


@router.post("/sessions/{session_id}/messages/{message_id}/image-edits")
async def edit_message_image(session_id: str, message_id: str, payload: ImageEditRequest,
    principal: ApiPrincipal = Depends(require_end_user_principal)):
    db = get_db()
    authorizer = SessionReadAuthorizer(db)
    try:
        lease = await authorizer.authorize_read(session_id, tenant_id=principal.main_id, user_id=principal.user_id)
        if str((lease.session.get("active_run") or {}).get("message_id") or "") == message_id:
            raise HTTPException(status_code=409, detail="image_message_running")
        scope = {"main_id": principal.main_id, "session_id": ObjectId(session_id), "message_id": message_id}
        message = await db.chat_messages.find_one(scope)
        source = source_document(message or {}, payload)
        if not source:
            raise HTTPException(status_code=404, detail="image_source_unavailable")
        if not payload.prompt.strip():
            raise HTTPException(status_code=422, detail="image_edit_prompt_required")
        source_model_id = str(source.get("image_model_id") or "")
        if source_model_id and payload.image_model_id and source_model_id != payload.image_model_id:
            raise HTTPException(status_code=409, detail="image_edit_model_mismatch")
        model_id = source_model_id or payload.image_model_id
        if not model_id:
            raise HTTPException(status_code=422, detail="image_edit_model_required")
        try:
            result = await edit_image_asset(object_path=source["object_path"], prompt=payload.prompt.strip(),
                tenant_id=principal.main_id, user_id=principal.user_id, image_model_id=model_id)
        except ImageEditModelError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="image_edit_unavailable") from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail="image_edit_failed") from exc
        await authorizer.authorize_read(session_id, tenant_id=principal.main_id, user_id=principal.user_id)
        updated = await db.chat_messages.update_one(scope, {"$addToSet": {"documents": result}})
        if not updated.matched_count:
            raise HTTPException(status_code=404, detail="image_source_unavailable")
        return result
    except (SessionReadDeniedError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="image_source_unavailable") from exc
