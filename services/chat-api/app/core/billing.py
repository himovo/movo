from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict

from app.core.db import get_db
from app.core.product_edition import member_limit

logger = logging.getLogger(__name__)

ORGANIZATION_COLLECTION = "organizations"
USER_COLLECTION = "end_users"


class ModelConfigError(ValueError):
    pass


def _now() -> datetime:
    return datetime.utcnow()


async def get_or_create_organization(main_id: str, default_org_name: str = "个人空间", owner_id: str = "") -> Dict[str, Any]:
    """
    获取或自动兜底创建组织信息。
    """
    db = get_db()
    org = await db[ORGANIZATION_COLLECTION].find_one({"main_id": main_id})
    if not org:
        from app.product.extensions import get_product_extension

        defaults = dict(get_product_extension().organization_defaults)
        org = {
            "main_id": main_id,
            "org_name": default_org_name,
            "owner_user_id": str(owner_id),
            **defaults,
            "created_at": _now(),
            "updated_at": _now(),
        }
        await db[ORGANIZATION_COLLECTION].insert_one(org)
    return org


async def check_quota_before_request(main_id: str, config: Dict[str, Any]) -> None:
    """
    在 LLM 请求发起前，检查当前组织是否仍有可用额度。
    若模型配置中 main_id 是 'default' (使用的是平台默认提供的共享模型)，才需要强制进行点数扣减检验。
    若当前组织已升级并启用了自有模型 (is_own_model = True)，或模型属于用户自有，不予拦截。
    """
    if not main_id or main_id == "default":
        return

    # 只有当使用的是平台默认提供的共享模型时，才受平台额度限制
    is_shared_model = str(config.get("main_id") or "default").strip() == "default"

    org = await get_or_create_organization(main_id)

    # 如果是共享模型，并且没有开启自有模型特权，则强校验点数
    if is_shared_model and not org.get("is_own_model", False):
        used = org.get("used_points", 0)
        total = org.get("total_points", 1000000)
        if used >= total:
            raise ModelConfigError(
                f"您的组织/空间额度已耗尽 (当前已使用: {used}/{total} Tokens)。"
                "企业空间请进入管理后台配置自己的模型密钥，或联系管理员进行额度充值。"
            )


async def deduct_points_after_request(main_id: str, total_tokens: int) -> None:
    """
    当请求产生 Token 消费后，异步将其累计扣减。
    如果该组织是免费版（或者未开启 is_own_model），就计入系统账单；
    """
    if not main_id or main_id == "default" or total_tokens <= 0:
        return

    db = get_db()
    org = await get_or_create_organization(main_id)

    # 只有在使用系统默认模型，或者未启用自有模型时才累计额度点数消耗
    if org.get("tier") == "free" or not org.get("is_own_model", False):
        await db[ORGANIZATION_COLLECTION].update_one(
            {"main_id": main_id},
            {
                "$inc": {"used_points": total_tokens},
                "$set": {"updated_at": _now()}
            }
        )
        logger.info(
            "organization token points deducted",
            extra={"main_id": main_id, "tokens_deducted": total_tokens}
        )


async def check_member_limit(main_id: str) -> None:
    """
    添加成员时，前置校验当前组织的成员总数是否超限。
    """
    db = get_db()
    org = await get_or_create_organization(main_id)
    limit = member_limit(org)

    if limit is None:
        return

    # 统计 end_users 中本 main_id 的成员总数
    from app.api.endpoints.auth import USER_COLLECTION
    current_count = await db[USER_COLLECTION].count_documents({"main_id": main_id})

    if current_count >= limit:
        tier_label = "个人免费版"
        if org.get("tier") == "plus":
            tier_label = "个人 Plus 版"
        elif org.get("tier") == "pro":
            tier_label = "专业团队版"
        raise ValueError(
            f"当前组织属于 {tier_label}，最大成员数限制为 {limit} 人。已达上限，无法添加新成员。"
        )
