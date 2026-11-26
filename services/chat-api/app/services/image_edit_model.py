"""Resolve an image's original model without silently selecting another one."""

from typing import Any

from app.services.image_generation import _service


class ImageEditModelError(ValueError):
    pass


async def resolve_edit_model(model_id: str, *, tenant_id: str, user_id: str) -> dict[str, Any]:
    if not model_id:
        raise ImageEditModelError("image_edit_model_required")
    try:
        config, _ = await _service._resolve_image_model_config(
            output_spec={"main_id": tenant_id, "image_model_id": model_id}, user_id=user_id,
        )
    except (ValueError, PermissionError) as exc:
        raise ImageEditModelError("image_edit_model_unavailable") from exc
    if not config or str(config.get("id") or "") != model_id:
        raise ImageEditModelError("image_edit_model_unavailable")
    return config
