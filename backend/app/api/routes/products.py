"""Справочник товаров и динамика цен.

Отдельный ресурс, а не раздел справочников (`/directories`): у товара, в
отличие от банка или магазина, есть собственная история — кривая цены, — и
адрес `/products/{id}/prices` должен существовать.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.schemas.product import (
    ProductCreate,
    ProductPriceHistory,
    ProductRead,
    ProductUpdate,
)
from app.services.product_service import (
    create_product,
    delete_product,
    get_price_history,
    list_products,
    suggest_products,
    update_product,
)

router = APIRouter(prefix="/products", tags=["products"])


@router.get("", response_model=list[ProductRead])
async def read_products(
    include_archived: bool = False, session: AsyncSession = Depends(get_session)
) -> list[ProductRead]:
    return await list_products(session, include_archived)


@router.get("/suggest", response_model=list[ProductRead])
async def read_product_suggestions(
    q: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(default=10, ge=1, le=50),
    session: AsyncSession = Depends(get_session),
) -> list[ProductRead]:
    """Подсказка при вводе позиции чека — по названию или штрихкоду."""
    return await suggest_products(session, q, limit)


@router.get("/{product_id}/prices", response_model=ProductPriceHistory)
async def read_price_history(
    product_id: int, session: AsyncSession = Depends(get_session)
) -> ProductPriceHistory:
    return await get_price_history(session, product_id)


@router.post("", response_model=ProductRead, status_code=201)
async def create_product_route(
    payload: ProductCreate, session: AsyncSession = Depends(get_session)
) -> ProductRead:
    return await create_product(session, payload)


@router.patch("/{product_id}", response_model=ProductRead)
async def update_product_route(
    product_id: int, payload: ProductUpdate, session: AsyncSession = Depends(get_session)
) -> ProductRead:
    return await update_product(session, product_id, payload)


@router.delete("/{product_id}", status_code=204)
async def delete_product_route(product_id: int, session: AsyncSession = Depends(get_session)) -> None:
    """Удаляет товар. Позиции чеков остаются — покупка была, — но кривая цены
    после этого распадётся, поэтому обычно товар архивируют."""
    await delete_product(session, product_id)
