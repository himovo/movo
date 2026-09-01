from __future__ import annotations

from datetime import datetime, timezone

from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

from app.api.deps import get_current_admin_user
from app.api.time_utils import utc_iso
from app.core.db import get_db
from app.repositories.org_user_repository import (
    count_accounts_by_group_code,
    create_account,
    create_account_group,
    delete_account,
    delete_account_group,
    find_account_by_id,
    find_account_by_username,
    find_group_by_code,
    find_group_by_id,
    list_account_groups,
    list_accounts,
    update_account,
    update_account_group,
)

router = APIRouter()


def _as_time(value: datetime | None) -> str:
    return utc_iso(value)


def _format_group(doc: dict) -> dict[str, object]:
    return {
        "id": str(doc["_id"]),
        "mainId": doc.get("main_id", ""),
        "name": doc.get("name", ""),
        "code": doc.get("code", ""),
        "description": doc.get("description", ""),
        "accountCount": doc.get("account_count", 0),
        "updatedAt": _as_time(doc.get("updated_at")),
    }


def _format_account(doc: dict, group_name_map: dict[str, str]) -> dict[str, object]:
    group_code = doc.get("group_code", "")
    return {
        "id": str(doc["_id"]),
        "mainId": doc.get("main_id", ""),
        "username": doc.get("username", ""),
        "displayName": doc.get("display_name", ""),
        "email": doc.get("email", ""),
        "phone": doc.get("phone", ""),
        "groupCode": group_code,
        "groupName": group_name_map.get(group_code, group_code),
        "roleName": doc.get("role_name", ""),
        "status": doc.get("status", "active"),
        "isProtected": bool(doc.get("is_protected", False)),
        "updatedAt": _as_time(doc.get("updated_at")),
    }


class AccountGroupCreatePayload(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    description: str = Field(default="", max_length=200)


class AccountGroupUpdatePayload(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    description: str = Field(default="", max_length=200)


class AccountCreatePayload(BaseModel):
    username: str = Field(min_length=2, max_length=64, pattern=r"^[a-zA-Z0-9._\-]+$")
    displayName: str = Field(min_length=1, max_length=64)
    email: str = Field(default="", max_length=120)
    phone: str = Field(default="", max_length=32)
    groupCode: str = Field(min_length=2, max_length=64)
    roleName: str = Field(min_length=1, max_length=64)
    status: str = Field(default="active", pattern=r"^(active|disabled)$")
    initialPassword: str = Field(min_length=6, max_length=128)


class AccountUpdatePayload(BaseModel):
    displayName: str = Field(min_length=1, max_length=64)
    email: str = Field(default="", max_length=120)
    phone: str = Field(default="", max_length=32)
    groupCode: str = Field(min_length=2, max_length=64)
    roleName: str = Field(min_length=1, max_length=64)
    status: str = Field(default="active", pattern=r"^(active|disabled)$")


@router.get("/account-groups")
async def get_account_groups(current_user: dict = Depends(get_current_admin_user)) -> list[dict[str, object]]:
    main_id = str(current_user.get("main_id", "default"))
    groups = await list_account_groups(main_id)
    result: list[dict[str, object]] = []
    for group in groups:
        count = await count_accounts_by_group_code(group.get("code", ""), main_id)
        group["account_count"] = count
        result.append(_format_group(group))
    return result


@router.post("/account-groups", status_code=status.HTTP_201_CREATED)
async def post_account_group(
    payload: AccountGroupCreatePayload,
    current_user: dict = Depends(get_current_admin_user),
) -> dict[str, object]:
    main_id = str(current_user.get("main_id", "default"))
    try:
        created = await create_account_group({**payload.model_dump(), "main_id": main_id, "status": "active"})
    except DuplicateKeyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="账号组创建失败，请重试") from exc
    created["account_count"] = 0
    return _format_group(created)


@router.put("/account-groups/{group_id}")
async def put_account_group(
    group_id: str,
    payload: AccountGroupUpdatePayload,
    current_user: dict = Depends(get_current_admin_user),
) -> dict[str, object]:
    main_id = str(current_user.get("main_id", "default"))
    try:
        ok = await update_account_group(group_id, {**payload.model_dump(), "main_id": main_id, "status": "active"})
    except InvalidId as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="账号组ID无效") from exc
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="账号组不存在")
    updated = await find_group_by_id(group_id, main_id)
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="账号组不存在")
    updated["account_count"] = await count_accounts_by_group_code(updated.get("code", ""), main_id)
    return _format_group(updated)


@router.delete("/account-groups/{group_id}")
async def remove_account_group(
    group_id: str,
    current_user: dict = Depends(get_current_admin_user),
) -> dict[str, bool]:
    main_id = str(current_user.get("main_id", "default"))
    try:
        ok = await delete_account_group(group_id, main_id)
    except InvalidId as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="账号组ID无效") from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="账号组不存在")
    return {"success": True}


@router.get("/accounts")
async def get_accounts(current_user: dict = Depends(get_current_admin_user)) -> list[dict[str, object]]:
    main_id = str(current_user.get("main_id", "default"))
    groups = await list_account_groups(main_id)
    group_name_map = {item.get("code", ""): item.get("name", "") for item in groups}
    accounts = await list_accounts(main_id)
    return [_format_account(item, group_name_map) for item in accounts]


@router.post("/accounts", status_code=status.HTTP_201_CREATED)
async def post_account(
    payload: AccountCreatePayload,
    current_user: dict = Depends(get_current_admin_user),
) -> dict[str, object]:
    main_id = str(current_user.get("main_id", "default"))
    group = await find_group_by_code(payload.groupCode, main_id)
    if group is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="账号组不存在")
    exists = await find_account_by_username(payload.username, main_id)
    if exists is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="登录账号已存在")
    account_payload = {
        "username": payload.username,
        "display_name": payload.displayName,
        "email": payload.email,
        "phone": payload.phone,
        "group_code": payload.groupCode,
        "role_name": payload.roleName,
        "status": payload.status,
        "password": payload.initialPassword,
        "main_id": main_id,
    }
    try:
        created = await create_account(account_payload)
    except DuplicateKeyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="登录账号已存在") from exc

    return _format_account(created, {group.get("code", ""): group.get("name", "")})


@router.put("/accounts/{account_id}")
async def put_account(
    account_id: str,
    payload: AccountUpdatePayload,
    current_user: dict = Depends(get_current_admin_user),
) -> dict[str, object]:
    main_id = str(current_user.get("main_id", "default"))
    group = await find_group_by_code(payload.groupCode, main_id)
    if group is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="账号组不存在")
    account_payload = {
        "display_name": payload.displayName,
        "email": payload.email,
        "phone": payload.phone,
        "group_code": payload.groupCode,
        "role_name": payload.roleName,
        "status": payload.status,
        "main_id": main_id,
    }
    try:
        ok = await update_account(account_id, account_payload)
    except InvalidId as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="账号ID无效") from exc
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="账号不存在")
    updated = await find_account_by_id(account_id, main_id)
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="账号不存在")
    return _format_account(updated, {group.get("code", ""): group.get("name", "")})


@router.delete("/accounts/{account_id}")
async def remove_account(
    account_id: str,
    current_user: dict = Depends(get_current_admin_user),
) -> dict[str, bool]:
    main_id = str(current_user.get("main_id", "default"))
    try:
        ok = await delete_account(account_id, main_id)
    except InvalidId as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="账号ID无效") from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="账号不存在")
    return {"success": True}


# ==========================================
# 组织订阅计费与后台升级 API 路由
# ==========================================

@router.get("/billing")
async def get_org_billing(current_user: dict = Depends(get_current_admin_user)) -> dict[str, object]:
    main_id = str(current_user.get("main_id", "default"))
    db = get_db()
    
    org = await db["organizations"].find_one({"main_id": main_id})
    if not org:
        now = datetime.now(timezone.utc)
        org = {
            "main_id": main_id,
            "org_name": current_user.get("org_name") or "组织空间",
            "tier": "free",
            "user_limit": 5,
            "total_points": 1000000,
            "used_points": 0,
            "owner_user_id": str(current_user.get("_id") or ""),
            "is_own_model": False,
            "created_at": now,
            "updated_at": now,
        }
        await db["organizations"].insert_one(org)
        
    current_members = await db["end_users"].count_documents({"main_id": main_id})
    
    from app.core.product_edition import billing_enabled, is_community_organization, member_limit

    return {
        "code": 0,
        "data": {
            "mainId": org.get("main_id"),
            "orgName": org.get("org_name"),
            "edition": "community" if is_community_organization(org) else str(org.get("edition") or "cloud"),
            "tier": org.get("tier", "free"),
            "billingEnabled": billing_enabled(org),
            "userLimit": member_limit(org),
            "currentMembersCount": current_members,
            "totalPoints": org.get("total_points", 1000000),
            "usedPoints": org.get("used_points", 0),
            "remainingPoints": max(0, org.get("total_points", 1000000) - org.get("used_points", 0)),
            "isOwnModel": bool(org.get("is_own_model", False)),
        }
    }


class UpgradePayload(BaseModel):
    tier: str = Field(..., pattern=r"^(pro|enterprise)$")


class BillingOrderPayload(BaseModel):
    planCode: str = Field(..., min_length=2, max_length=64)
    paymentMethod: str = Field(default="wechat_native", pattern=r"^(wechat_native|wechat_jsapi|wechat_h5|dev_mock)$")


@router.post("/upgrade")
async def upgrade_org_billing(
    payload: UpgradePayload,
    current_user: dict = Depends(get_current_admin_user)
) -> dict[str, object]:
    main_id = str(current_user.get("main_id", "default"))

    tier = payload.tier
    if tier == "pro":
        from app.core.billing import create_billing_order

        try:
            order = await create_billing_order(
                main_id=main_id,
                buyer_user_id=str(current_user.get("_id") or ""),
                plan_code="org_pro_monthly",
                source="admin_legacy_upgrade",
                payment_method="wechat_native",
            )
        except ValueError as exc:
            return {"code": 1, "message": str(exc)}
        return {
            "code": 0,
            "message": "Payment order created",
            "data": {"order": order},
        }
    elif tier == "enterprise":
        return {"code": 0, "message": "Enterprise upgrade request submitted. Our sales team will reach out to you."}
    return {"code": 1, "message": "Invalid tier"}


@router.get("/billing/plans")
async def get_org_billing_plans(current_user: dict = Depends(get_current_admin_user)) -> dict[str, object]:
    from app.core.billing import list_billing_plans
    from app.core.product_edition import billing_enabled

    main_id = str(current_user.get("main_id", "default"))
    org = await get_db()["organizations"].find_one({"main_id": main_id})

    return {"code": 0, "data": {"plans": list_billing_plans() if billing_enabled(org) else []}}


@router.post("/billing/orders")
async def create_org_billing_order(
    payload: BillingOrderPayload,
    current_user: dict = Depends(get_current_admin_user),
) -> dict[str, object]:
    main_id = str(current_user.get("main_id", "default"))
    from app.core.billing import create_billing_order

    try:
        order = await create_billing_order(
            main_id=main_id,
            buyer_user_id=str(current_user.get("_id") or ""),
            plan_code=payload.planCode,
            source="admin",
            payment_method=payload.paymentMethod,
        )
    except ValueError as exc:
        return {"code": 1, "message": str(exc)}
    return {"code": 0, "message": "Payment order created", "data": {"order": order}}


@router.get("/billing/orders/{order_no}")
async def get_org_billing_order(
    order_no: str,
    current_user: dict = Depends(get_current_admin_user),
) -> dict[str, object]:
    main_id = str(current_user.get("main_id", "default"))
    from app.core.billing import get_billing_order

    order = await get_billing_order(main_id, order_no)
    if not order:
        return {"code": 1, "message": "Payment order not found"}
    return {"code": 0, "data": {"order": order}}


@router.get("/billing/orders")
async def list_org_billing_orders(current_user: dict = Depends(get_current_admin_user)) -> dict[str, object]:
    main_id = str(current_user.get("main_id", "default"))
    from app.core.billing import list_billing_orders
    from app.core.product_edition import billing_enabled

    org = await get_db()["organizations"].find_one({"main_id": main_id})
    if not billing_enabled(org):
        return {"code": 0, "data": {"orders": []}}

    return {"code": 0, "data": {"orders": await list_billing_orders(main_id)}}


@router.post("/billing/orders/{order_no}/confirm-dev")
async def confirm_org_billing_order_dev(
    order_no: str,
    current_user: dict = Depends(get_current_admin_user),
) -> dict[str, object]:
    main_id = str(current_user.get("main_id", "default"))
    from app.core.billing import mark_order_paid_and_apply

    try:
        order = await mark_order_paid_and_apply(main_id, order_no)
    except ValueError as exc:
        return {"code": 1, "message": str(exc)}
    return {"code": 0, "message": "Payment confirmed and plan applied", "data": {"order": order}}
