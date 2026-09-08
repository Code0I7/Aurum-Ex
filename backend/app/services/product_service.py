"""Справочник товаров и динамика цен.

У справочника две задачи.

**Подстановка.** Выбрал товар — подставилась его категория и единица, и
человек перестал выбирать из списка в полторы сотни подкатегорий, который
всё равно не помнит наизусть. В исходной таблице это тоже задумывалось —
там даже был заведён именованный диапазон «Продукты», — но колонку так и не
заполнили, и возможности не существовало.

**История цен.** Десять чеков со словом «хлеб» — десять несвязанных строк.
Десять позиций, указывающих на одну строку справочника, — кривая цены.
Разница между «динамика цен работает» и «не работает» ровно в этом, и
поэтому справочник должен существовать раньше, чем позиции чека станут
осмысленными.

Цена приводится к базовой единице своего рода: сумма, делённая на
количество, умноженное на коэффициент единицы. Без этого «1,5 л сока за
120 ₽» и «500 мл сока за 55 ₽» несравнимы, и в исходной таблице колонки
количества пустовали в 89% записей — единицы там были подписями без
арифметики.
"""
from collections import defaultdict
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.category import Category
from app.models.product import Product
from app.models.store import Store
from app.models.transaction import Transaction, TransactionItem
from app.models.unit import Unit
from app.schemas.product import (
    PricePoint,
    ProductCreate,
    ProductPriceHistory,
    ProductRead,
    ProductUpdate,
)
from app.services.transaction_service import counted_only


def price_per_base_unit(
    amount: Decimal | None,
    quantity: Decimal | None,
    unit_factor: Decimal | None,
) -> Decimal | None:
    """Цена за базовую единицу — то, что делает литры сравнимыми с
    миллилитрами.

    None означает «посчитать нельзя», и это не ошибка: позиция без цены или
    без количества — воспоминание, а не измерение, и в график она просто не
    попадает.
    """
    if amount is None or quantity is None or quantity <= 0:
        return None
    factor = unit_factor if unit_factor and unit_factor > 0 else Decimal("1")
    return amount / (quantity * factor)


async def _product_stats(session: AsyncSession) -> dict[int, tuple[int, object, Decimal | None]]:
    """Сколько раз товар покупали, когда в последний раз и почём.

    Одним запросом на весь список: в справочнике на пару сотен строк
    отдельный запрос на каждую превратил бы открытие страницы в минуту
    ожидания.
    """
    rows = (
        await session.execute(
            select(
                TransactionItem.product_id,
                Transaction.date,
                TransactionItem.amount,
                TransactionItem.quantity,
                Unit.factor,
            )
            .join(Transaction, Transaction.id == TransactionItem.transaction_id)
            .outerjoin(Unit, Unit.id == TransactionItem.unit_id)
            .where(TransactionItem.product_id.is_not(None), counted_only())
            .order_by(Transaction.date)
        )
    ).all()

    counts: dict[int, int] = defaultdict(int)
    last_date: dict[int, object] = {}
    last_price: dict[int, Decimal | None] = {}
    for product_id, tx_date, amount, quantity, factor in rows:
        counts[product_id] += 1
        # Запрос отсортирован по дате, поэтому последняя строка и есть
        # последняя покупка — отдельного max() не нужно.
        last_date[product_id] = tx_date
        price = price_per_base_unit(amount, quantity, factor)
        if price is not None:
            last_price[product_id] = price
    return {
        product_id: (counts[product_id], last_date.get(product_id), last_price.get(product_id))
        for product_id in counts
    }


def _to_read(product: Product, stats: tuple[int, object, Decimal | None] | None) -> ProductRead:
    purchases, last_bought, last_price = stats or (0, None, None)
    return ProductRead(
        id=product.id,
        name=product.name,
        category_id=product.category_id,
        category_name=product.category.name if product.category else None,
        unit_id=product.unit_id,
        unit_name=product.unit.name if product.unit else None,
        barcode=product.barcode,
        notes=product.notes,
        is_archived=product.is_archived,
        purchases=purchases,
        last_bought=last_bought,
        last_price_per_base_unit=last_price,
    )


async def list_products(session: AsyncSession, include_archived: bool = False) -> list[ProductRead]:
    stmt = (
        select(Product)
        .options(selectinload(Product.category), selectinload(Product.unit))
        .order_by(Product.name)
    )
    if not include_archived:
        stmt = stmt.where(Product.is_archived.is_(False))
    products = (await session.execute(stmt)).scalars().all()
    stats = await _product_stats(session)
    return [_to_read(product, stats.get(product.id)) for product in products]


async def create_product(session: AsyncSession, payload: ProductCreate) -> ProductRead:
    existing = (
        await session.execute(select(Product).where(func.lower(Product.name) == payload.name.strip().lower()))
    ).scalar_one_or_none()
    if existing is not None:
        # Два «Хлеб чёрный» разорвали бы кривую цены надвое, и ни одна из
        # половин не была бы правдой.
        raise HTTPException(status_code=400, detail="A product with this name already exists")

    product = Product(**payload.model_dump())
    session.add(product)
    await session.commit()
    await session.refresh(product, ["category", "unit"])
    return _to_read(product, None)


async def update_product(session: AsyncSession, product_id: int, payload: ProductUpdate) -> ProductRead:
    product = await session.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(product, field, value)
    await session.commit()
    await session.refresh(product, ["category", "unit"])
    stats = await _product_stats(session)
    return _to_read(product, stats.get(product.id))


async def delete_product(session: AsyncSession, product_id: int) -> None:
    """Удаляет товар из справочника.

    Позиции чеков остаются: связь SET NULL, и название в них хранится своё.
    Покупка была, и стирать её вместе со строкой справочника нельзя — но
    кривая цены после этого распадётся, поэтому обычно товар архивируют, а
    не удаляют.
    """
    product = await session.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    await session.delete(product)
    await session.commit()


async def get_price_history(session: AsyncSession, product_id: int) -> ProductPriceHistory:
    product = await session.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    rows = (
        await session.execute(
            select(
                Transaction.id,
                Transaction.date,
                TransactionItem.amount,
                TransactionItem.quantity,
                Unit.name,
                Unit.factor,
                Unit.kind,
                Store.name,
            )
            .join(Transaction, Transaction.id == TransactionItem.transaction_id)
            .outerjoin(Unit, Unit.id == TransactionItem.unit_id)
            .outerjoin(Store, Store.id == Transaction.store_id)
            .where(TransactionItem.product_id == product_id, counted_only())
            .order_by(Transaction.date, Transaction.id)
        )
    ).all()

    points: list[PricePoint] = []
    base_unit_name: str | None = None
    for transaction_id, tx_date, amount, quantity, unit_name, factor, unit_kind, store_name in rows:
        price = price_per_base_unit(amount, quantity, factor)
        if price is None:
            # Позиция без цены или количества — воспоминание, а не измерение.
            continue
        if base_unit_name is None and unit_kind is not None:
            base_unit_name = await _base_unit_name(session, unit_kind)
        points.append(
            PricePoint(
                date=tx_date,
                price_per_base_unit=price,
                quantity=quantity,
                unit_name=unit_name,
                amount=amount,
                store_name=store_name,
                transaction_id=transaction_id,
            )
        )

    prices = [point.price_per_base_unit for point in points]
    change_percent = None
    if len(prices) >= 2 and prices[0] > 0:
        change_percent = float(round((prices[-1] - prices[0]) / prices[0] * 100, 1))

    return ProductPriceHistory(
        product_id=product.id,
        product_name=product.name,
        base_unit_name=base_unit_name,
        points=points,
        min_price=min(prices) if prices else None,
        max_price=max(prices) if prices else None,
        last_price=prices[-1] if prices else None,
        change_percent=change_percent,
    )


async def _base_unit_name(session: AsyncSession, unit_kind) -> str | None:
    """Название базовой единицы для рода — грамм, миллилитр, штука.

    Нужно только для подписи оси: «₽ за грамм» понятнее, чем «₽ за базовую
    единицу».
    """
    return (
        await session.execute(
            select(Unit.name).where(Unit.kind == unit_kind, Unit.is_base.is_(True)).limit(1)
        )
    ).scalar_one_or_none()


async def suggest_products(session: AsyncSession, query: str, limit: int = 10) -> list[ProductRead]:
    """Подсказка при вводе позиции.

    Ищет и по названию, и по штрихкоду: если товар отсканировали телефоном,
    в поле окажется код, а не слово.
    """
    pattern = f"%{query.strip().lower()}%"
    stmt = (
        select(Product)
        .options(selectinload(Product.category), selectinload(Product.unit))
        .where(
            Product.is_archived.is_(False),
            func.lower(Product.name).like(pattern) | (Product.barcode == query.strip()),
        )
        .order_by(Product.name)
        .limit(limit)
    )
    products = (await session.execute(stmt)).scalars().all()
    stats = await _product_stats(session)
    return [_to_read(product, stats.get(product.id)) for product in products]


async def resolve_item_category(session: AsyncSession, category_id: int | None) -> int | None:
    """Проверяет, что категория позиции существует.

    Молча проглотить несуществующую значило бы записать позицию, которая
    нигде не показывается: связь SET NULL, и ошибки бы не случилось.
    """
    if category_id is None:
        return None
    exists = await session.get(Category, category_id)
    if exists is None:
        raise HTTPException(status_code=400, detail="Item category not found")
    return category_id
