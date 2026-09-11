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
from dataclasses import dataclass
from datetime import date as date_, timedelta
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

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


@dataclass
class ProductStats:
    """Что известно о товаре из чеков."""

    purchases: int = 0
    last_bought: object = None
    last_price: Decimal | None = None
    # Количество и единица последней покупки — подставляются в новую
    # позицию. Хлеб берут по одной штуке, молоко по литру, и вводить одно и
    # то же в каждом чеке незачем.
    last_quantity: Decimal | None = None
    last_unit_id: int | None = None
    spent_total: Decimal = Decimal("0")
    spent_year: Decimal = Decimal("0")


async def _product_stats(session: AsyncSession) -> dict[int, ProductStats]:
    """Сколько раз товар покупали, когда в последний раз, почём и на сколько.

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
                TransactionItem.unit_id,
                Unit.factor,
            )
            .join(Transaction, Transaction.id == TransactionItem.transaction_id)
            .outerjoin(Unit, Unit.id == TransactionItem.unit_id)
            .where(TransactionItem.product_id.is_not(None), counted_only())
            .order_by(Transaction.date)
        )
    ).all()

    # Скользящий год, а не календарный: в январе календарный показывал бы
    # траты за две недели и выглядел бы падением там, где его нет.
    year_ago = date_.today() - timedelta(days=365)

    stats: dict[int, ProductStats] = defaultdict(ProductStats)
    for product_id, tx_date, amount, quantity, unit_id, factor in rows:
        item = stats[product_id]
        item.purchases += 1
        # Запрос отсортирован по дате, поэтому последняя строка и есть
        # последняя покупка — отдельного max() не нужно.
        item.last_bought = tx_date
        # Количество последней покупки. Хлеб берут по одной штуке, молоко —
        # по литру: подставить прошлое число избавляет от ввода того же
        # самого в каждом чеке. Пустое не запоминается: «не помню, сколько
        # было» не должно стирать то, что помнили раньше.
        if quantity is not None:
            item.last_quantity = quantity
        if unit_id is not None:
            item.last_unit_id = unit_id
        price = price_per_base_unit(amount, quantity, factor)
        if price is not None:
            item.last_price = price
        # Сумма позиции бывает не заполнена: в чеке её могли не разносить
        # по строкам вовсе. Такая покупка считается фактом покупки, но
        # деньгами не считается — придумывать их за человека нельзя.
        if amount is not None:
            item.spent_total += amount
            if tx_date >= year_ago:
                item.spent_year += amount
    return dict(stats)


def _to_read(
    product: Product, stats: ProductStats | None, base_units: dict[str, str] | None = None
) -> ProductRead:
    stats = stats or ProductStats()
    # Подпись берётся по виду единицы самого товара: «кг» для сыра, «л» для
    # сока. Товар без единицы цены за базовую меру и не имеет.
    base_name = None
    if product.unit is not None and base_units:
        kind = product.unit.kind
        base_name = base_units.get(str(kind.value if hasattr(kind, "value") else kind))
    return ProductRead(
        id=product.id,
        name=product.name,
        unit_id=product.unit_id,
        unit_name=product.unit.name if product.unit else None,
        barcode=product.barcode,
        notes=product.notes,
        is_archived=product.is_archived,
        purchases=stats.purchases,
        last_quantity=stats.last_quantity,
        last_unit_id=stats.last_unit_id,
        last_bought=stats.last_bought,
        last_price_per_base_unit=stats.last_price,
        spent_total=stats.spent_total,
        spent_year=stats.spent_year,
        base_unit_name=base_name,
    )


async def _base_unit_names(session: AsyncSession) -> dict[str, str]:
    """Имя базовой меры для каждого вида: MASS → «кг», VOLUME → «л».

    Нужно только для подписи. Вид без базовой единицы в словарь не
    попадает, и цена у его товаров показывается без «за что» — это хуже,
    чем с подписью, но лучше, чем выдуманная.
    """
    rows = (await session.execute(select(Unit.kind, Unit.name).where(Unit.is_base.is_(True)))).all()
    return {str(kind.value if hasattr(kind, "value") else kind): name for kind, name in rows}


async def list_products(session: AsyncSession, include_archived: bool = False) -> list[ProductRead]:
    stmt = (
        select(Product)
        .options(selectinload(Product.unit))
        .order_by(Product.name)
    )
    if not include_archived:
        stmt = stmt.where(Product.is_archived.is_(False))
    products = (await session.execute(stmt)).scalars().all()
    stats = await _product_stats(session)
    base_units = await _base_unit_names(session)
    return [_to_read(product, stats.get(product.id), base_units) for product in products]


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
    await session.refresh(product, ["unit"])
    return _to_read(product, None)


async def update_product(session: AsyncSession, product_id: int, payload: ProductUpdate) -> ProductRead:
    product = await session.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(product, field, value)
    await session.commit()
    await session.refresh(product, ["unit"])
    stats = await _product_stats(session)
    return _to_read(product, stats.get(product.id), await _base_unit_names(session))


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
        .options(selectinload(Product.unit))
        .where(
            Product.is_archived.is_(False),
            func.lower(Product.name).like(pattern) | (Product.barcode == query.strip()),
        )
        .order_by(Product.name)
        .limit(limit)
    )
    products = (await session.execute(stmt)).scalars().all()
    stats = await _product_stats(session)
    return [_to_read(product, stats.get(product.id), await _base_unit_names(session)) for product in products]


async def find_product_by_name(session: AsyncSession, name: str) -> Product | None:
    """Товар справочника с ровно таким названием, без учёта регистра.

    Нужен, чтобы позиция, набранная руками, всё-таки склеилась с товаром.
    Человек вписывает «Хлеб бородинский» в третий чек, подсказку не
    нажимает — и в справочнике остаётся один товар, а в кривой цены одна
    точка из трёх: история цен смотрит только на позиции с product_id.

    Совпадение только точное. «Молоко» и «Молоко 3,2%» — разные товары, и
    склейка по вхождению испортила бы ровно то, ради чего справочник
    заведён: цену за базовую меру у двух разных вещей.

    Архивные не ищутся: товар отправляют в архив как раз для того, чтобы он
    перестал подставляться сам.
    """
    cleaned = name.strip()
    if not cleaned:
        return None
    stmt = select(Product).where(
        func.lower(Product.name) == cleaned.lower(), Product.is_archived.is_(False)
    )
    return (await session.execute(stmt)).scalars().first()

