from __future__ import annotations

from typing import Any

from bson import ObjectId
from bson.errors import InvalidId

from app.core.db import get_db
from app.services.secret_codec import decrypt_admin_secret


INSTANCE_COLLECTION = "admin_model_instances"
PROVIDER_COLLECTION = "admin_model_providers"


class ModelCenterConfigError(RuntimeError):
    pass


def resolve_model_instance(main_id: str, instance_id: str, capability: str) -> dict[str, str]:
    if not main_id:
        raise ModelCenterConfigError("模型配置缺少租户标识")
    if not instance_id:
        raise ModelCenterConfigError(f"知识库尚未选择 {capability} 模型")
    try:
        object_id = ObjectId(instance_id)
    except (InvalidId, TypeError) as exc:
        raise ModelCenterConfigError(f"{capability} 模型实例 ID 无效") from exc
    db = get_db()
    instance = db[INSTANCE_COLLECTION].find_one({"_id": object_id, "main_id": main_id, "status": "active"})
    if not instance:
        raise ModelCenterConfigError(f"未找到可用的 {capability} 模型配置")
    capabilities = {str(item) for item in instance.get("capabilities") or []}
    if capability not in capabilities:
        raise ModelCenterConfigError(f"所选模型不具备 {capability} 能力")
    provider = db[PROVIDER_COLLECTION].find_one({"_id": instance.get("provider_id")}) or {}
    api_key = decrypt_admin_secret(str(instance.get("api_key_encrypted") or ""))
    if not api_key:
        raise ModelCenterConfigError(f"{capability} 模型 API Key 无法解密或为空")
    return {
        "providerType": str(provider.get("provider_type") or "openai_compatible"),
        "providerCode": str(provider.get("code") or ""),
        "baseUrl": str(instance.get("base_url") or provider.get("default_base_url") or "").rstrip("/"),
        "apiVersion": str(instance.get("api_version") or ""),
        "apiKey": api_key,
        "modelName": str(instance.get("model_name") or ""),
    }
