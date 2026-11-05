"""Distribution-owned admission for server-side execution capabilities."""

from app.product.extensions import get_product_extension


async def execution_is_allowed(*, main_id: str, user_id: str, capability: str) -> bool:
    policy = get_product_extension().execution_access_policy
    if policy is None:
        return True
    return bool(await policy.allows(main_id=main_id, user_id=user_id, capability=capability))
