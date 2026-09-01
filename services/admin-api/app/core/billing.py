from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.core.db import get_db
from app.core.product_edition import billing_enabled

ORGANIZATION_COLLECTION = "organizations"
BILLING_ORDER_COLLECTION = "billing_orders"
USER_COLLECTION = "end_users"

PLAN_CATALOG: dict[str, dict[str, Any]] = {
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


def _now() -> datetime:
    return datetime.now(timezone.utc)


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
    org = await db[ORGANIZATION_COLLECTION].find_one({"main_id": main_id})
    if not org:
        raise ValueError("Organization not found")
    if not billing_enabled(org):
        raise ValueError("社区版无需订阅，在线计费已关闭")
    if str(org.get("tier") or "free") == str(plan.get("tier") or ""):
        raise ValueError("当前组织已是该套餐")
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
        "amount_cents": int(plan.get("amount_cents") or 0),
        "currency": plan.get("currency") or "CNY",
        "status": "pending",
        "payment_method": payment_method,
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
    return _format_order(order) if order else None


async def list_billing_orders(main_id: str, *, limit: int = 10) -> list[dict[str, Any]]:
    db = get_db()
    cursor = (
        db[BILLING_ORDER_COLLECTION]
        .find({"main_id": main_id})
        .sort("created_at", -1)
        .limit(max(1, min(int(limit or 10), 50)))
    )
    rows = await cursor.to_list(length=max(1, min(int(limit or 10), 50)))
    return [_format_order(row) for row in rows]


async def apply_plan_to_organization(main_id: str, plan_code: str, *, order_no: str = "") -> dict[str, Any]:
    db = get_db()
    plan, _ = await validate_plan_purchase(main_id, plan_code)
    updates: dict[str, Any] = {
        "tier": plan["tier"],
        "user_limit": plan["user_limit"],
        "is_own_model": bool(plan.get("is_own_model")),
        "last_paid_order_no": order_no,
        "updated_at": _now(),
    }
    if plan.get("total_points") is not None:
        updates["total_points"] = int(plan["total_points"])
    await db[ORGANIZATION_COLLECTION].update_one({"main_id": main_id}, {"$set": updates})
    updated = await db[ORGANIZATION_COLLECTION].find_one({"main_id": main_id})
    return updated or {}


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
