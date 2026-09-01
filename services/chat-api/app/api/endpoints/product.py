from fastapi import APIRouter

from app.product.extensions import get_product_extension


router = APIRouter(tags=["product"])


@router.get("/product/capabilities")
async def product_capabilities() -> dict[str, object]:
    return get_product_extension().capability_payload()
