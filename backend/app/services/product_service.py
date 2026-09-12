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

Рода при этом не смешиваются, и это не придирка. Штука и килограмм —
разные меры, и одна кривая на обе врёт крупно: шоколад, купленный раз как
«90 г за 89 ₽» (989 ₽/кг) и раз как «1 шт за 89 ₽» (89 ₽/шт), показывал
падение цены на 91%, которого не было. Поэтому у товара столько кривых,
сколько мер в нём встретилось, и подписаны они каждая своей.

Мостом между ними служит размер упаковки в позиции чека: «2 шт × 0,9 л»
считается как 1,8 л и попадает на объёмную кривую. Размер не указан —
покупка остаётся на штучной кривой и в объёмную не идёт: придумывать вес
за человека нельзя, у развесного товара он каждый раз свой.
"""
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date as date_, timedelta
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, selectinload

from app.models.product import Product
from app.models.store import Store
from app.models.transaction import Transaction, TransactionItem
from app.models.unit import Unit
from app.schemas.product import (
    PricePoint,
    PriceSeries,
    ProductCreate,
    ProductPriceHistory,
    ProductRead,
    ProductUpdate,
)
from app.services.currency_service import get_base_currency
from app.services.transaction_service import counted_only


def measured_quantity(
    quantity: Decimal | None,
    unit_factor: Decimal | None,
    pack_size: Decimal | None = None,
    pack_factor: Decimal | None = None,
) -> Decimal | None:
    """Сколько это в базовой мере: 500 мл → 0,5 л, «2 шт × 0,9 л» → 1,8 л.

    Размер упаковки — второй множитель и появляется только когда он задан.
    «2 шт» без размера остаются двумя штуками: перевести их в литры не во
    что, и подставить прошлый размер значило бы придумать его.
    """
    if quantity is None or quantity <= 0:
        return None
    factor = unit_factor if unit_factor and unit_factor > 0 else Decimal("1")
    base = quantity * factor
    if pack_size is not None and pack_size > 0:
        pack = pack_factor if pack_factor and pack_factor > 0 else Decimal("1")
        base = base * pack_size * pack
    return base if base > 0 else None


def measured_kind(unit_kind, pack_unit_kind):
    """В какой мере выражена покупка.

    Размер упаковки перебивает единицу количества: «2 шт × 0,9 л» — это про
    литры, а штуки в нём лишь счёт упаковок.
    """
    return pack_unit_kind if pack_unit_kind is not None else unit_kind


def price_per_base_unit(
    amount: Decimal | None,
    quantity: Decimal | None,
    unit_factor: Decimal | None,
    pack_size: Decimal | None = None,
    pack_factor: Decimal | None = None,
) -> Decimal | None:
    """Цена за базовую единицу — то, что делает литры сравнимыми с
    миллилитрами.

    None означает «посчитать нельзя», и это не ошибка: позиция без цены или
    без количества — воспоминание, а не измерение, и в график она просто не
    попадает.
    """
    base = measured_quantity(quantity, unit_factor, pack_size, pack_factor)
    if amount is None or base is None:
        return None
    return amount / base


def amount_in_base(
    amount: Decimal | None,
    currency: str | None,
    exchange_rate: Decimal | None,
    base: str,
) -> Decimal | None:
    """Сумма позиции чека в валюте установки, по курсу дня покупки.

    Цена — событие: сколько отдали в тот день. События переводятся один раз,
    курсом своего дня, и после этого сравнимы между собой — на этом и стоит
    кривая цены. Без перевода покупка за евро легла бы на рублёвую кривую
    своим числом, и «сыр подешевел втрое» означало бы только то, что в тот
    раз платили не рублями.

    Тем же и отличается от единиц измерения, где линии разводятся по видам:
    килограммы с литрами несравнимы в принципе, а валюты сравнимы — на то и
    курс.

    None — курса на тот день нет. Такая покупка на кривую не попадает, как
    не попадает покупка без количества: выдумать курс хуже, чем пропустить
    точку.
    """
    if amount is None:
        return None
    if not currency or currency.upper() == base:
        return amount
    if exchange_rate is None:
        return None
    return amount * exchange_rate


@dataclass
class ProductStats:
    """Что известно о товаре из чеков."""

    purchases: int = 0
    last_bought: object = None
    last_price: Decimal | None = None
    # В какой мере выражена последняя цена. Без этого «89» у товара,
    # записанного в граммах, но купленного однажды штукой, подписывалось бы
    # как «₽ / кг» — то есть числом за килограмм назывался бы ценник за
    # упаковку.
    last_price_kind: object = None
    # Количество и единица последней покупки — подставляются в новую
    # позицию. Хлеб берут по одной штуке, молоко по литру, и вводить одно и
    # то же в каждом чеке незачем.
    last_quantity: Decimal | None = None
    last_unit_id: int | None = None
    # Размер упаковки последней покупки — тоже для подстановки.
    last_pack_size: Decimal | None = None
    last_pack_unit_id: int | None = None
    # Размеры упаковок в базовой мере, по порядку покупок. Нужны только
    # чтобы решить, можно ли подставлять размер: см. pack_size_stable.
    pack_sizes: list[Decimal] = field(default_factory=list)
    spent_total: Decimal = Decimal("0")
    spent_year: Decimal = Decimal("0")

    @property
    def pack_size_stable(self) -> bool:
        """Можно ли подставлять размер упаковки в новую позицию.

        Только когда последние два известных размера совпали. У молока в
        литровых пакетах они совпадают всегда, и человек перестаёт вводить
        «0,9 л» в каждом чеке. У сыра, расфасованного в магазине, они не
        совпадают никогда — и подставлять там нечего: вес каждой упаковки
        свой, а подставленный прошлый выглядел бы как записанный с ценника.
        Одного известного размера недостаточно: по одной покупке постоянную
        фасовку от развесной не отличить, а придуманный вес портит кривую
        цены молча.
        """
        return len(self.pack_sizes) >= 2 and self.pack_sizes[-1] == self.pack_sizes[-2]


async def _product_stats(session: AsyncSession) -> dict[int, ProductStats]:
    """Сколько раз товар покупали, когда в последний раз, почём и на сколько.

    Одним запросом на весь список: в справочнике на пару сотен строк
    отдельный запрос на каждую превратил бы открытие страницы в минуту
    ожидания.
    """
    pack_unit = aliased(Unit)
    rows = (
        await session.execute(
            select(
                TransactionItem.product_id,
                Transaction.date,
                TransactionItem.amount,
                # Валюта покупки и её курс на тот день — см. amount_in_base.
                Transaction.currency,
                Transaction.exchange_rate,
                TransactionItem.quantity,
                TransactionItem.unit_id,
                Unit.factor,
                Unit.kind,
                TransactionItem.pack_size,
                TransactionItem.pack_unit_id,
                pack_unit.factor,
                pack_unit.kind,
            )
            .join(Transaction, Transaction.id == TransactionItem.transaction_id)
            .outerjoin(Unit, Unit.id == TransactionItem.unit_id)
            .outerjoin(pack_unit, pack_unit.id == TransactionItem.pack_unit_id)
            .where(TransactionItem.product_id.is_not(None), counted_only())
            .order_by(Transaction.date)
        )
    ).all()

    # Скользящий год, а не календарный: в январе календарный показывал бы
    # траты за две недели и выглядел бы падением там, где его нет.
    year_ago = date_.today() - timedelta(days=365)
    base = (await get_base_currency(session)).upper()

    stats: dict[int, ProductStats] = defaultdict(ProductStats)
    for (
        product_id,
        tx_date,
        raw_amount,
        currency,
        exchange_rate,
        quantity,
        unit_id,
        factor,
        unit_kind,
        pack_size,
        pack_unit_id,
        pack_factor,
        pack_kind,
    ) in rows:
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
        # Размер упаковки запоминается так же, как количество: пустой не
        # стирает прошлый, потому что «не переписал вес с ценника» — это не
        # «упаковки больше нет».
        if pack_size is not None:
            item.last_pack_size = pack_size
            item.last_pack_unit_id = pack_unit_id
            normalised = pack_size * (pack_factor if pack_factor and pack_factor > 0 else Decimal("1"))
            item.pack_sizes.append(normalised)
        # Сумма приводится к валюте установки по курсу дня покупки: и
        # цена, и потраченное за год складываются из покупок, а сложить их
        # можно только приведёнными (см. amount_in_base).
        amount = amount_in_base(raw_amount, currency, exchange_rate, base)
        price = price_per_base_unit(amount, quantity, factor, pack_size, pack_factor)
        if price is not None:
            item.last_price = price
            item.last_price_kind = measured_kind(unit_kind, pack_kind)
        # Сумма позиции бывает не заполнена: в чеке её могли не разносить
        # по строкам вовсе. Такая покупка считается фактом покупки, но
        # деньгами не считается — придумывать их за человека нельзя. Сюда
        # же попадает покупка в чужой валюте без курса на её день.
        if amount is not None:
            item.spent_total += amount
            if tx_date >= year_ago:
                item.spent_year += amount
    return dict(stats)


def _to_read(
    product: Product, stats: ProductStats | None, base_units: dict[str, str] | None = None
) -> ProductRead:
    stats = stats or ProductStats()
    # Подпись берётся по мере ПОСЛЕДНЕЙ покупки, а не по единице товара.
    # Товар записан в граммах, а куплен однажды штукой — и цена за упаковку
    # подписывалась бы как «₽ / кг». Пока покупок нет, берётся единица
    # справочника: там она про то же самое.
    base_name = None
    kind = stats.last_price_kind
    if kind is None and product.unit is not None:
        kind = product.unit.kind
    if kind is not None and base_units:
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
        # Размер упаковки подставляется только когда он устоялся — см.
        # ProductStats.pack_size_stable.
        last_pack_size=stats.last_pack_size if stats.pack_size_stable else None,
        last_pack_unit_id=stats.last_pack_unit_id if stats.pack_size_stable else None,
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

    pack_unit = aliased(Unit)
    rows = (
        await session.execute(
            select(
                Transaction.id,
                Transaction.date,
                TransactionItem.amount,
                # Валюта покупки и её курс на тот день — см. amount_in_base.
                Transaction.currency,
                Transaction.exchange_rate,
                TransactionItem.quantity,
                Unit.name,
                Unit.factor,
                Unit.kind,
                TransactionItem.pack_size,
                pack_unit.name,
                pack_unit.factor,
                pack_unit.kind,
                Store.name,
            )
            .join(Transaction, Transaction.id == TransactionItem.transaction_id)
            .outerjoin(Unit, Unit.id == TransactionItem.unit_id)
            .outerjoin(pack_unit, pack_unit.id == TransactionItem.pack_unit_id)
            .outerjoin(Store, Store.id == Transaction.store_id)
            .where(TransactionItem.product_id == product_id, counted_only())
            .order_by(Transaction.date, Transaction.id)
        )
    ).all()

    # По одной кривой на меру. Складывать штуки с килограммами нельзя: это
    # разные величины, и общий график из них показывал обвал цены там, где
    # человек просто записал покупку иначе.
    base = (await get_base_currency(session)).upper()
    by_kind: dict[object, list[PricePoint]] = defaultdict(list)
    unmeasured = 0
    for (
        transaction_id,
        tx_date,
        raw_amount,
        currency,
        exchange_rate,
        quantity,
        unit_name,
        factor,
        unit_kind,
        pack_size,
        pack_unit_name,
        pack_factor,
        pack_kind,
        store_name,
    ) in rows:
        amount = amount_in_base(raw_amount, currency, exchange_rate, base)
        price = price_per_base_unit(amount, quantity, factor, pack_size, pack_factor)
        if price is None:
            # Позиция без цены или количества — воспоминание, а не
            # измерение. Сюда же попадает покупка в чужой валюте, курса на
            # день которой нет: сравнивать её не с чем.
            unmeasured += 1
            continue
        by_kind[measured_kind(unit_kind, pack_kind)].append(
            PricePoint(
                date=tx_date,
                price_per_base_unit=price,
                quantity=quantity,
                unit_name=unit_name,
                pack_size=pack_size,
                pack_unit_name=pack_unit_name,
                amount=amount,
                store_name=store_name,
                transaction_id=transaction_id,
            )
        )

    base_names = await _base_unit_names(session)
    series: list[PriceSeries] = []
    for kind, points in by_kind.items():
        prices = [point.price_per_base_unit for point in points]
        change_percent = None
        if len(prices) >= 2 and prices[0] > 0:
            change_percent = float(round((prices[-1] - prices[0]) / prices[0] * 100, 1))
        key = str(kind.value if hasattr(kind, "value") else kind) if kind is not None else None
        series.append(
            PriceSeries(
                unit_kind=key,
                base_unit_name=base_names.get(key) if key is not None else None,
                points=points,
                min_price=min(prices),
                max_price=max(prices),
                last_price=prices[-1],
                change_percent=change_percent,
            )
        )

    # Сначала та мера, в которой покупок больше: ею человек и пользуется, а
    # вторая — след того раза, когда записал по-другому.
    series.sort(key=lambda item: (-len(item.points), item.base_unit_name or ""))

    return ProductPriceHistory(
        product_id=product.id,
        product_name=product.name,
        series=series,
        unmeasured=unmeasured,
    )


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

