from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Dict

from app.core.db import get_db
from app.core.product_edition import billing_enabled, member_limit

logger = logging.getLogger(__name__)

ORGANIZATION_COLLECTION = "organizations"
BILLING_ORDER_COLLECTION = "billing_orders"
USER_COLLECTION = "end_users"

PLAN_CATALOG: dict[str, dict[str, Any]] = {
    "free": {
        "plan_code": "free",
        "tier": "free",
        "name": "免费版",
        "description": "注册后默认套餐，个人空间赠送 100 万 Token，企业空间默认 0 平台额度。",
        "amount_cents": 0,
        "currency": "CNY",
        "period": "none",
        "user_limit": 5,
        "total_points": 1_000_000,
        "is_own_model": False,
        "payable": False,
    },
    "personal_plus_monthly": {
        "plan_code": "personal_plus_monthly",
        "tier": "plus",
        "name": "个人 Plus 版",
        "description": "个人空间升级套餐，平台共享 Token 提升至 2000 万，限 1 人，支持配置自有模型。",
        "amount_cents": 2_000,
        "currency": "CNY",
        "period": "month",
        "user_limit": 1,
        "total_points": 20_000_000,
        "is_own_model": True,
        "payable": True,
        "requires_single_member": True,
        "source": "frontend",
    },
    "org_pro_monthly": {
        "plan_code": "org_pro_monthly",
        "tier": "pro",
        "name": "专业团队版",
        "description": "企业/团队套餐，成员上限提升至 50 人，并支持团队自有模型配置。",
        "amount_cents": 4_900,
        "currency": "CNY",
        "period": "month",
        "user_limit": 50,
        "total_points": None,
        "is_own_model": True,
        "payable": True,
        "source": "frontend_admin",
    },
    "enterprise_custom": {
        "plan_code": "enterprise_custom",
        "tier": "enterprise",
        "name": "企业定制版",
        "description": "线下定制额度、成员数、自有模型或私有化部署方案。",
        "amount_cents": 0,
        "currency": "CNY",
        "period": "custom",
        "user_limit": None,
        "total_points": None,
        "is_own_model": True,
        "payable": False,
    },
}


class ModelConfigError(ValueError):
    pass


def _now() -> datetime:
    return datetime.utcnow()


def list_billing_plans() -> list[dict[str, Any]]:
    return [dict(plan) for plan in PLAN_CATALOG.values()]


def get_billing_plan(plan_code: str) -> dict[str, Any]:
    plan = PLAN_CATALOG.get(str(plan_code or "").strip())
    if not plan:
        raise ValueError("未知套餐")
    return dict(plan)


async def validate_plan_purchase(main_id: str, plan_code: str) -> tuple[dict[str, Any], dict[str, Any]]:
    db = get_db()
    plan = get_billing_plan(plan_code)
    if not plan.get("payable"):
        raise ValueError("该套餐不支持在线支付")

    org = await get_or_create_organization(main_id)
    if not billing_enabled(org):
        raise ValueError("社区版无需订阅，在线计费已关闭")
    current_members = await db[USER_COLLECTION].count_documents({"main_id": main_id})
    if plan.get("requires_single_member") and current_members > 1:
        raise ValueError("升级个人 Plus 失败：组织中已有其他成员，请升级为专业团队版。")

    current_tier = str(org.get("tier") or "free")
    target_tier = str(plan.get("tier") or "")
    if current_tier == target_tier:
        raise ValueError("当前组织已是该套餐")
    if current_tier in {"pro", "enterprise"} and target_tier == "plus":
        raise ValueError("当前套餐不能降级为个人 Plus")
    return plan, org


def _format_amount(amount_cents: int, currency: str = "CNY") -> str:
    if currency == "CNY":
        return f"¥{amount_cents / 100:.2f}"
    return f"{amount_cents / 100:.2f} {currency}"


def _format_order(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "orderNo": doc.get("order_no"),
        "mainId": doc.get("main_id"),
        "source": doc.get("source"),
        "planCode": doc.get("plan_code"),
        "planName": doc.get("plan_name"),
        "targetTier": doc.get("target_tier"),
        "amountCents": int(doc.get("amount_cents") or 0),
        "amountText": _format_amount(int(doc.get("amount_cents") or 0), str(doc.get("currency") or "CNY")),
        "currency": doc.get("currency") or "CNY",
        "status": doc.get("status") or "created",
        "paymentMethod": doc.get("payment_method") or "wechat_native",
        "paymentUrl": doc.get("payment_url") or "",
        "createdAt": doc.get("created_at").isoformat() if isinstance(doc.get("created_at"), datetime) else "",
        "paidAt": doc.get("paid_at").isoformat() if isinstance(doc.get("paid_at"), datetime) else "",
        "appliedAt": doc.get("applied_at").isoformat() if isinstance(doc.get("applied_at"), datetime) else "",
    }


async def create_billing_order(
    *,
    main_id: str,
    buyer_user_id: str,
    plan_code: str,
    source: str,
    payment_method: str = "wechat_native",
) -> dict[str, Any]:
    db = get_db()
    plan, org = await validate_plan_purchase(main_id, plan_code)
    order_no = f"pay_{_now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:10]}"
    amount_cents = int(plan.get("amount_cents") or 0)
    now = _now()
    order = {
        "order_no": order_no,
        "main_id": main_id,
        "org_name": org.get("org_name") or "",
        "buyer_user_id": str(buyer_user_id or ""),
        "source": source,
        "plan_code": plan["plan_code"],
        "plan_name": plan["name"],
        "target_tier": plan["tier"],
        "amount_cents": amount_cents,
        "currency": plan.get("currency") or "CNY",
        "status": "pending",
        "payment_method": payment_method,
        # Real WeChat Native integration should replace this with code_url.
        "payment_url": f"askai-pay://wechat/native/{order_no}",
        "provider_payload": {},
        "created_at": now,
        "updated_at": now,
    }
    await db[BILLING_ORDER_COLLECTION].insert_one(order)
    return _format_order(order)


async def get_billing_order(main_id: str, order_no: str) -> dict[str, Any] | None:
    db = get_db()
    order = await db[BILLING_ORDER_COLLECTION].find_one({"main_id": main_id, "order_no": order_no})
    if not order:
        return None
    return _format_order(order)


async def apply_plan_to_organization(main_id: str, plan_code: str, *, order_no: str = "") -> dict[str, Any]:
    db = get_db()
    plan, _ = await validate_plan_purchase(main_id, plan_code)
    updates: dict[str, Any] = {
        "tier": plan["tier"],
        "user_limit": plan["user_limit"],
        "is_own_model": bool(plan.get("is_own_model")),
        "updated_at": _now(),
        "last_paid_order_no": order_no,
    }
    if plan.get("total_points") is not None:
        updates["total_points"] = int(plan["total_points"])
    await db[ORGANIZATION_COLLECTION].update_one({"main_id": main_id}, {"$set": updates})
    updated = await get_or_create_organization(main_id)
    return updated


async def mark_order_paid_and_apply(main_id: str, order_no: str, *, payment_trace_id: str = "") -> dict[str, Any]:
    db = get_db()
    order = await db[BILLING_ORDER_COLLECTION].find_one({"main_id": main_id, "order_no": order_no})
    if not order:
        raise ValueError("支付订单不存在")
    if order.get("status") == "applied":
        return _format_order(order)
    if order.get("status") not in {"pending", "paid"}:
        raise ValueError("当前订单状态不能确认支付")

    now = _now()
    if order.get("status") == "pending":
        await db[BILLING_ORDER_COLLECTION].update_one(
            {"_id": order["_id"], "status": "pending"},
            {
                "$set": {
                    "status": "paid",
                    "paid_at": now,
                    "payment_trace_id": payment_trace_id or f"devpay_{uuid.uuid4().hex[:12]}",
                    "updated_at": now,
                }
            },
        )

    await apply_plan_to_organization(main_id, str(order.get("plan_code") or ""), order_no=order_no)
    await db[BILLING_ORDER_COLLECTION].update_one(
        {"_id": order["_id"]},
        {"$set": {"status": "applied", "applied_at": _now(), "updated_at": _now()}},
    )
    updated = await db[BILLING_ORDER_COLLECTION].find_one({"_id": order["_id"]})
    return _format_order(updated or order)


async def init_organization_quota(main_id: str, org_name: str, owner_id: str, *, total_points: int = 1000000) -> Dict[str, Any]:
    """
    初始化组织空间额度。
    个人空间默认赠送 1,000,000 点数；企业空间可传入 0，要求管理员配置自有模型。
    """
    db = get_db()
    quota = max(int(total_points or 0), 0)
    org_doc = {
        "main_id": main_id,
        "org_name": org_name or "个人空间",
        "tier": "free",
        "user_limit": 5,
        "total_points": quota,
        "used_points": 0,
        "owner_user_id": str(owner_id),
        "is_own_model": False,
        "created_at": _now(),
        "updated_at": _now(),
    }
    # 使用 upsert 确保防重
    await db[ORGANIZATION_COLLECTION].update_one(
        {"main_id": main_id},
        {"$setOnInsert": org_doc},
        upsert=True,
    )
    return org_doc


async def get_or_create_organization(main_id: str, default_org_name: str = "个人空间", owner_id: str = "") -> Dict[str, Any]:
    """
    获取或自动兜底创建组织信息。
    """
    db = get_db()
    org = await db[ORGANIZATION_COLLECTION].find_one({"main_id": main_id})
    if not org:
        org = {
            "main_id": main_id,
            "org_name": default_org_name,
            "tier": "free",
            "user_limit": 5,
            "total_points": 1000000,
            "used_points": 0,
            "owner_user_id": str(owner_id),
            "is_own_model": False,
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
