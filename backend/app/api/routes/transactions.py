from datetime import date as date_
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_session
from app.models.account import Account
from app.models.category import Category
from app.models.enums import CategoryKind, TransactionType
from app.models.tag import Tag
from app.models.transaction import Transaction, TransactionItem, TransactionSplit
from app.models.unit import Unit
from app.schemas.transaction import (
    TransactionBulkCreate,
    TransactionBulkCreateResult,
    TransactionCreate,
    TransactionPage,
    TransactionRead,
    TransactionBlockReorder,
    TransactionReorder,
    SimilarTransaction,
    TransactionSplitInput,
    TransactionUpdate,
    split_rule_violation,
    transfer_rule_violation,
)
from app.models.product import Product
from app.schemas.product import TransactionItemInput
from app.services.category_tree import load_category_tree
from app.services.currency_service import get_base_currency, to_base
from app.services.product_service import find_product_by_name, measured_quantity
from app.services.transaction_service import (
    find_similar_transactions,
    next_day_order,
    running_balances,
)

router = APIRouter(prefix="/transactions", tags=["transactions"])

_EAGER = (
    # Банк подгружается вместе со счётом: AccountRead его показывает, а
    # ленивая загрузка в асинхронной сессии падает (MissingGreenlet), и
    # падает не при чтении списка, а при ответе на создание операции —
    # то есть у любого, кто привязал счёт к банку.
    selectinload(Transaction.account).selectinload(Account.bank),
    selectinload(Transaction.category),
    selectinload(Transaction.tags),
    selectinload(Transaction.splits).selectinload(TransactionSplit.category),
    selectinload(Transaction.items).selectinload(TransactionItem.product),
    selectinload(Transaction.items).selectinload(TransactionItem.unit),
)


async def _resolve_tags(session: AsyncSession, tag_ids: list[int]) -> list[Tag]:
    if not tag_ids:
        return []
    result = await session.execute(select(Tag).where(Tag.id.in_(tag_ids)))
    tags = list(result.scalars().all())
    missing = set(tag_ids) - {tag.id for tag in tags}
    if missing:
        raise HTTPException(status_code=400, detail=f"Unknown tag id(s): {sorted(missing)}")
    return tags

_TYPE_TO_CATEGORY_KIND = {
    TransactionType.INCOME: CategoryKind.INCOME,
    TransactionType.EXPENSE: CategoryKind.EXPENSE,
}


async def _ensure_category_matches_type(
    session: AsyncSession, category_id: int | None, transaction_type: TransactionType
) -> Category | None:
    """A category picked for an income transaction must itself be an income
    category (and likewise for expense) — otherwise the dashboard's spending
    breakdown, which only joins EXPENSE-typed rows, would silently misclassify
    the entry. Returns the fetched category (or None for category_id=None) so
    callers that also need the row itself — _build_splits, below — don't have
    to fetch it a second time."""
    if category_id is None:
        return None
    expected_kind = _TYPE_TO_CATEGORY_KIND.get(transaction_type)
    category = await session.get(Category, category_id)
    if category is None:
        raise HTTPException(status_code=400, detail="Category not found")
    if expected_kind is not None and category.kind != expected_kind:
        raise HTTPException(
            status_code=400,
            detail=f"Category '{category.name}' is a {category.kind.value} category and cannot be used for a {transaction_type.value} transaction",
        )
    return category


async def _item_amount(session: AsyncSession, item: TransactionItemInput) -> Decimal | None:
    """Сумма позиции из цены за базовую меру и количества.

    None, когда считать не из чего: половина позиций в чеках заполняется
    без цены вовсе — «купили хлеб и молоко» помнят и без неё.

    Размер упаковки, если он задан, входит вторым множителем: «2 шт × 0,9 л
    по 100 ₽ за литр» — это 180 ₽, а не 200. Считается тем же
    measured_quantity, которым считается и цена за меру, чтобы сумма и
    кривая цены не разошлись на округлении.
    """
    if item.price is None or item.quantity is None:
        return None

    async def factor_of(unit_id: int | None) -> Decimal | None:
        if unit_id is None:
            return None
        unit = await session.get(Unit, unit_id)
        return unit.factor if unit is not None else None

    base = measured_quantity(
        item.quantity,
        await factor_of(item.unit_id),
        item.pack_size,
        await factor_of(item.pack_unit_id),
    )
    return item.price * base if base is not None else None


async def _build_items(
    session: AsyncSession, items: list[TransactionItemInput]
) -> list[TransactionItem]:
    """Позиции чека — «что лежало в пакете».

    Сходиться с суммой транзакции они не обязаны и намеренно: помнить, что
    купили хлеб и молоко, не помня цен, обычное дело, а сумма транзакции
    остаётся источником истины. Нераспределённый остаток интерфейс
    показывает, а не подгоняет.

    Категории у позиции нет: она здесь была, её можно было задать, и ни
    один отчёт её не читал — деньги считаются по категории операции и по её
    сплитам. Разложить чек по категориям можно сплитами.
    """
    built: list[TransactionItem] = []
    for position, item in enumerate(items):
        product_id = item.product_id
        if product_id is not None and await session.get(Product, product_id) is None:
            raise HTTPException(status_code=400, detail="Product not found")
        if product_id is None:
            # Позиция, набранная текстом, всё же склеивается с товаром, если
            # товар с таким названием уже заведён. Иначе одинаковые строки в
            # разных чеках остаются разными строками, и кривая цены видит
            # одну покупку из трёх — подсказку нажимают не всегда, а
            # название печатают одно и то же.
            #
            # Название позиции при этом остаётся тем, что набрали: в
            # магазине товар мог называться иначе, и это важно помнить.
            match = await find_product_by_name(session, item.name)
            if match is not None:
                product_id = match.id
        built.append(
            TransactionItem(
                product_id=product_id,
                name=item.name,
                quantity=item.quantity,
                unit_id=item.unit_id,
                # Размер упаковки — мост между штуками и мерой: «2 шт ×
                # 0,9 л». Запоминается в позиции, а не в товаре: фасовку
                # ужимают, и прошлые покупки не должны пересчитываться по
                # новому размеру.
                #
                # Половина пары ничего не значит: «340» без единицы — не
                # размер. Такая половина отбрасывается, а не отвергается
                # четырёхсотым: единицу могли удалить из справочника уже
                # после покупки, и ронять из-за этого чтение операции
                # нельзя.
                pack_size=item.pack_size if item.pack_unit_id is not None else None,
                pack_unit_id=item.pack_unit_id if item.pack_size is not None else None,
                price=item.price,
                # Сумма позиции: если не задана, но известны цена и
                # количество, считается сама — заставлять человека
                # перемножать числа, которые он уже ввёл, незачем.
                #
                # Через коэффициент единицы, потому что цена хранится за
                # базовую меру: 500 мл по 73,98 за литр — это 500 × 0,001
                # × 73,98, а не 500 × 73,98.
                amount=item.amount
                if item.amount is not None
                else await _item_amount(session, item),
                note=item.note,
                position=position,
            )
        )
    return built


async def _build_splits(
    session: AsyncSession, splits: list[TransactionSplitInput], transaction_type: TransactionType
) -> list[TransactionSplit]:
    """Разбивка делит сумму одной операции между несколькими категориями:
    в одном чеке ноутбук и клавиатура, в одной покупке продукты и бытовая
    химия.

    Категории могут быть какими угодно и из любых веток.

    Раньше здесь стояло требование общего корня: разбивка задумывалась как
    деление покупки между подкатегориями одного родителя (чек гипермаркета:
    часть в «Сладкое», часть в «Алкоголь»), а разные корни отклонялись —
    считалось, что иначе «потрачено X на продукты, из них столько-то на
    сладкое» перестанет складываться.

    Требование убрано, потому что описывало не жизнь, а удобную половину
    жизни. В одном чеке лежат вещи из разных веток — это норма, а не
    исключение, и приложение заставляло либо врать категорией, либо
    заводить две операции на одну покупку. Отчёты от этого не страдают:
    каждая доля и так учитывается в своей категории и сама сворачивается в
    свой корень; просто корней у одной операции теперь может быть больше
    одного.

    Остаётся то, что действительно обязано выполняться: категория
    подходит виду операции, долей не меньше двух, и в сумме они дают сумму
    операции ровно (см. schemas/transaction.py, split_rule_violation).
    """
    for split in splits:
        await _ensure_category_matches_type(session, split.category_id, transaction_type)
    return [TransactionSplit(category_id=s.category_id, amount=s.amount, note=s.note) for s in splits]


@router.get("", response_model=TransactionPage)
async def list_transactions(
    year: int | None = Query(default=None, ge=2000, le=2100),
    month: int | None = Query(default=None, ge=1, le=12),
    start_date: date_ | None = Query(default=None),
    end_date: date_ | None = Query(default=None),
    account_id: int | None = None,
    category_id: int | None = None,
    tag_id: int | None = None,
    type: TransactionType | None = None,
    # Новые измерения Aurum-Ex. Все необязательные — фильтр по ним имеет
    # смысл, только когда поля заполняют.
    participant_id: int | None = None,
    store_id: int | None = None,
    counterparty_id: int | None = None,
    # Записи, помеченные "не учитывать", по умолчанию видны наравне с
    # остальными: они и заведены ради того, чтобы о покупке помнить.
    # Скрыть их — отдельное решение пользователя.
    include_excluded: bool = True,
    search: str | None = Query(default=None, min_length=1, max_length=255),
    sort: Literal["date_desc", "amount_desc", "amount_asc"] = Query(default="date_desc"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
) -> TransactionPage:
    stmt = select(Transaction).options(*_EAGER)
    count_stmt = select(func.count()).select_from(Transaction)

    if year is not None:
        stmt = stmt.where(func.extract("year", Transaction.date) == year)
        count_stmt = count_stmt.where(func.extract("year", Transaction.date) == year)
    if month is not None:
        stmt = stmt.where(func.extract("month", Transaction.date) == month)
        count_stmt = count_stmt.where(func.extract("month", Transaction.date) == month)
    if start_date is not None:
        stmt = stmt.where(Transaction.date >= start_date)
        count_stmt = count_stmt.where(Transaction.date >= start_date)
    if end_date is not None:
        stmt = stmt.where(Transaction.date <= end_date)
        count_stmt = count_stmt.where(Transaction.date <= end_date)
    if account_id is not None:
        # Обе стороны перевода, а не только счёт-источник. У перевода
        # account_id — откуда ушло, transfer_account_id — куда пришло, и
        # фильтр по одной колонке показывал бы половину выписки: деньги,
        # пришедшие на счёт переводом, из неё выпадали. Именно на этом
        # запутываются пары счетов вроде «карта и рассрочка того же
        # магазина» — половина движений между ними просто не видна.
        account_filter = or_(
            Transaction.account_id == account_id, Transaction.transfer_account_id == account_id
        )
        stmt = stmt.where(account_filter)
        count_stmt = count_stmt.where(account_filter)
    if category_id is not None:
        # A split transaction has category_id=NULL on the row itself — the
        # category lives on its split lines instead, so filtering by exact
        # column match alone would silently drop it from a category filter
        # it genuinely belongs to.
        #
        # Ветка целиком, а не одна категория. Рейтинг и график в отчётах
        # сворачивают потомков (reports_service), и список операций под ними
        # обязан показывать ровно те же операции. Пока фильтр совпадал
        # точно, «Благотворительность» с итогом в графике раскрывалась
        # одной строкой: всё остальное лежало в её подкатегориях, и
        # выглядело это как поломанный диапазон дат.
        tree = await load_category_tree(session)
        branch = tree.subtree_of(category_id)
        category_filter = or_(
            Transaction.category_id.in_(branch), Transaction.splits.any(TransactionSplit.category_id.in_(branch))
        )
        stmt = stmt.where(category_filter)
        count_stmt = count_stmt.where(category_filter)
    if tag_id is not None:
        stmt = stmt.where(Transaction.tags.any(Tag.id == tag_id))
        count_stmt = count_stmt.where(Transaction.tags.any(Tag.id == tag_id))
    if type is not None:
        stmt = stmt.where(Transaction.type == type)
        count_stmt = count_stmt.where(Transaction.type == type)
    if participant_id is not None:
        stmt = stmt.where(Transaction.participant_id == participant_id)
        count_stmt = count_stmt.where(Transaction.participant_id == participant_id)
    if store_id is not None:
        stmt = stmt.where(Transaction.store_id == store_id)
        count_stmt = count_stmt.where(Transaction.store_id == store_id)
    if counterparty_id is not None:
        # Обе стороны, а не только контрагент. У транзита их две: деньги
        # брата, переданные маме, стоят у мамы в counterparty и у брата в
        # transit_party, и фильтр по одной колонке показывал бы половину
        # истории с человеком — ровно ту половину, которой не хватает, когда
        # разговор идёт о долге.
        party_filter = or_(
            Transaction.counterparty_id == counterparty_id,
            Transaction.transit_party_id == counterparty_id,
        )
        stmt = stmt.where(party_filter)
        count_stmt = count_stmt.where(party_filter)
    if not include_excluded:
        stmt = stmt.where(Transaction.is_excluded.is_(False))
        count_stmt = count_stmt.where(Transaction.is_excluded.is_(False))
    if search is not None:
        # Lets the user find a transaction from any period by keyword (e.g. an
        # item bought months ago) without knowing which month to look in first.
        # Ищет по описанию и по продавцу. Поля «заметка» больше нет: оно
        # описывало ровно то же, что описание, вторым способом, и не было
        # заполнено ни в одной операции.
        pattern = f"%{search.strip()}%"
        search_clause = or_(
            Transaction.description.ilike(pattern),
            Transaction.merchant.ilike(pattern),
        )
        stmt = stmt.where(search_clause)
        count_stmt = count_stmt.where(search_clause)

    total = (await session.execute(count_stmt)).scalar_one()

    # id as a tiebreaker keeps pagination stable when many rows share a date/amount.
    if sort == "amount_desc":
        stmt = stmt.order_by(Transaction.amount.desc(), Transaction.id.desc())
    elif sort == "amount_asc":
        stmt = stmt.order_by(Transaction.amount.asc(), Transaction.id.desc())
    else:
        # Новое сверху. day_order участвует в сортировке наравне с датой —
        # иначе баланс в строке перестанет соответствовать её месту на
        # экране, ведь считается он ровно в этом порядке.
        stmt = stmt.order_by(Transaction.date.desc(), Transaction.day_order.desc(), Transaction.id.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)

    result = await session.execute(stmt)
    items = list(result.scalars().all())

    # Баланс счёта после каждой операции считается по всей его истории, а не
    # по этой странице: иначе он менялся бы от включённого фильтра и
    # перестал бы быть балансом (см. services/transaction_service.py).
    # При фильтре по счёту баланс считается для него: иначе у строки
    # перевода в выписке получателя стоял бы остаток отправителя.
    balances = await running_balances(session, [item.id for item in items], account_id)
    rows = [
        TransactionRead.model_validate(item, from_attributes=True).model_copy(
            update={"balance_after": balances.get(item.id)}
        )
        for item in items
    ]

    return TransactionPage(items=rows, total=total, page=page, page_size=page_size)


@router.get("/years", response_model=list[int])
async def list_transaction_years(session: AsyncSession = Depends(get_session)) -> list[int]:
    """Full range of years to offer in the year picker — from the earliest
    transaction through the current year, so a gap year with no activity
    still shows up (as zero) instead of silently disappearing from the UI."""
    bounds = await session.execute(select(func.min(Transaction.date), func.max(Transaction.date)))
    min_date, max_date = bounds.one()
    current_year = date_.today().year
    if min_date is None:
        return [current_year]
    return list(range(min_date.year, max(max_date.year, current_year) + 1))


async def _apply_currency(session: AsyncSession, transaction: Transaction, explicit_currency: str | None) -> None:
    """Заполняет валюту, курс и сумму в базовой валюте перед сохранением.

    Одна точка на все места создания и изменения транзакции: сумма в базовой
    валюте — не то, что вводит человек, а производное от суммы, валюты и
    даты, и считаться она должна одинаково везде (см.
    services/currency_service.py).

    Валюта не указана — берётся со счёта: операция по долларовой карте по
    умолчанию в долларах, и заставлять выбирать это в каждой форме незачем."""
    if explicit_currency:
        transaction.currency = explicit_currency.upper()
    else:
        account = await session.get(Account, transaction.account_id)
        transaction.currency = account.currency if account is not None else await get_base_currency(session)

    rate, amount_base = await to_base(session, transaction.amount, transaction.currency, transaction.date)
    transaction.exchange_rate = rate
    transaction.amount_base = amount_base


@router.get("/similar", response_model=list[SimilarTransaction])
async def read_similar_transactions(
    date: date_ = Query(...),
    type: TransactionType = Query(...),
    amount: Decimal = Query(..., gt=0),
    description: str = Query(default=""),
    session: AsyncSession = Depends(get_session),
) -> list[SimilarTransaction]:
    """Есть ли уже такая операция в этом дне.

    Отдельным запросом перед записью, а не отказом при самой записи:
    отказывать пришлось бы и импорту таблицы, и проведению регулярных
    платежей, и любому скрипту через API, — а повторы там законны и
    ожидаемы. Спрашивать имеет смысл ровно у того, кто вводит руками.

    Объявлен до маршрутов с {transaction_id}: иначе «similar» разбиралось
    бы как номер операции.
    """
    found = await find_similar_transactions(
        session,
        on_date=date,
        transaction_type=type,
        amount=amount,
        description=description,
    )
    return [
        SimilarTransaction(
            id=item.id,
            date=item.date,
            description=item.description,
            amount=item.amount,
            currency=item.currency,
            account_name=item.account.name if item.account else "—",
            category_name=item.category.name if item.category else None,
            day_order=item.day_order,
        )
        for item in found
    ]


@router.post("", response_model=TransactionRead, status_code=201)
async def create_transaction(payload: TransactionCreate, session: AsyncSession = Depends(get_session)) -> Transaction:
    await _ensure_category_matches_type(session, payload.category_id, payload.type)
    fields = payload.model_dump(exclude={"tag_ids", "splits", "items", "currency"})
    transaction = Transaction(**fields)
    # Порядок внутри дня проставляется сам, по времени ввода: человеку не за
    # чем его набирать, а без него операции одного дня раскладываются
    # произвольно и баланс на графике проваливается ниже нуля там, где
    # этого не было (см. services/transaction_service.py).
    transaction.day_order = await next_day_order(session, transaction.date)
    await _apply_currency(session, transaction, payload.currency)
    transaction.tags = await _resolve_tags(session, payload.tag_ids)
    if payload.splits:
        transaction.splits = await _build_splits(session, payload.splits, payload.type)
    if payload.items:
        transaction.items = await _build_items(session, payload.items)
    session.add(transaction)
    await session.commit()
    refreshed = await session.execute(
        select(Transaction).options(*_EAGER).where(Transaction.id == transaction.id)
    )
    return refreshed.scalar_one()


@router.post("/bulk", response_model=TransactionBulkCreateResult, status_code=201)
async def bulk_create_transactions(
    payload: TransactionBulkCreate, session: AsyncSession = Depends(get_session)
) -> TransactionBulkCreateResult:
    """CSV import lands here — see schemas.TransactionBulkCreate. All rows
    are validated before any is added, so a bad row 400s the whole request
    instead of leaving a half-imported statement behind."""
    for item in payload.items:
        await _ensure_category_matches_type(session, item.category_id, item.type)

    transactions = []
    for item in payload.items:
        transaction = Transaction(**item.model_dump(exclude={"tag_ids", "splits", "items", "currency"}))
        transaction.day_order = await next_day_order(session, transaction.date)
        await _apply_currency(session, transaction, item.currency)
        transaction.tags = await _resolve_tags(session, item.tag_ids)
        if item.splits:
            transaction.splits = await _build_splits(session, item.splits, item.type)
        transactions.append(transaction)

    session.add_all(transactions)
    await session.commit()
    return TransactionBulkCreateResult(created=len(transactions))


@router.patch("/{transaction_id}", response_model=TransactionRead)
async def update_transaction(
    transaction_id: int, payload: TransactionUpdate, session: AsyncSession = Depends(get_session)
) -> Transaction:
    # Eager-loads tags and splits — assigning transaction.tags/splits below
    # would otherwise lazy-load the current collection first to diff
    # against, which async SQLAlchemy can't do outside an explicit await
    # (MissingGreenlet).
    transaction = await session.get(
        Transaction,
        transaction_id,
        options=[
            selectinload(Transaction.tags),
            selectinload(Transaction.splits),
            selectinload(Transaction.items),
        ],
    )
    if transaction is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    updates = payload.model_dump(exclude_unset=True, exclude={"tag_ids", "splits", "items", "currency"})
    # Checks run against the row as it would look after the patch, not just
    # the fields sent: switching type alone can invalidate fields left
    # untouched.
    effective_type = updates.get("type", transaction.type)
    effective_category_id = updates.get("category_id", transaction.category_id)
    effective_account_id = updates.get("account_id", transaction.account_id)
    effective_transfer_account_id = updates.get("transfer_account_id", transaction.transfer_account_id)
    effective_amount = updates.get("amount", transaction.amount)
    await _ensure_category_matches_type(session, effective_category_id, effective_type)
    violation = transfer_rule_violation(
        type=effective_type,
        account_id=effective_account_id,
        transfer_account_id=effective_transfer_account_id,
        category_id=effective_category_id,
    )
    if violation:
        raise HTTPException(status_code=400, detail=violation)

    if payload.splits is not None:
        split_count = len(payload.splits)
        split_total = sum((s.amount for s in payload.splits), Decimal("0")) if payload.splits else None
    else:
        # Splits weren't touched by this patch — check the existing rows as
        # they stand. Reading straight off the ORM objects here (not
        # rebuilding TransactionSplitInput) on purpose: an existing split's
        # category_id can be None if that category was since deleted, and
        # the sum check below needs none of that — only tags/category
        # values that were actually just fetched from the caller could ever
        # need to be re-validated, and those go through payload.splits above.
        split_count = len(transaction.splits)
        split_total = sum((s.amount for s in transaction.splits), Decimal("0")) if transaction.splits else None
    split_violation = split_rule_violation(
        type=effective_type,
        amount=effective_amount,
        category_id=effective_category_id,
        split_count=split_count,
        split_total=split_total,
    )
    if split_violation:
        raise HTTPException(status_code=400, detail=split_violation)

    for field, value in updates.items():
        setattr(transaction, field, value)
    # Пересчёт нужен, если поменялось хоть что-то из тройки "сумма, валюта,
    # дата": курс берётся на дату операции, поэтому сдвиг даты меняет и его.
    if {"amount", "date", "account_id"} & updates.keys() or payload.currency is not None:
        await _apply_currency(session, transaction, payload.currency)
    if payload.tag_ids is not None:
        transaction.tags = await _resolve_tags(session, payload.tag_ids)
    if payload.splits is not None:
        transaction.splits = await _build_splits(session, payload.splits, effective_type)
    if payload.items is not None:
        # Список заменяет состав чека целиком, включая пустой: правка чека —
        # это переписывание того, что в нём было, а не дописывание строк.
        transaction.items = await _build_items(session, payload.items)
    await session.commit()
    refreshed = await session.execute(
        select(Transaction).options(*_EAGER).where(Transaction.id == transaction_id)
    )
    return refreshed.scalar_one()


async def _move_within_day(session: AsyncSession, moved: list[Transaction], position: int) -> None:
    """Переставляет операции внутри их дня, сохраняя порядок внутри блока.

    Между днями записи не переносятся намеренно: дату меняют
    редактированием даты, а не движением мыши — случайное перетаскивание
    строки не должно менять день операции.

    Внутри дня переставляется всё, независимо от счёта. Раньше порядок был
    внутри счёта, и покупку наличными нельзя было поднять выше карточной
    того же дня: в списке счета идут вперемешку, а нумерация у них была
    своя (см. services/transaction_service.py, next_day_order). Балансу это
    безразлично — он считается с разбиением по счёту, и относительный
    порядок внутри счёта пересчёт сохраняет.

    Порядок пересчитывается сплошным рядом 0, 1, 2… у всех операций этого
    дня. Это дороже точечной правки, но избавляет от дыр и дубликатов в
    нумерации, которые иначе накапливаются и однажды ломают сортировку.

    Позиция зажимается к краю: бросок мимо списка — это «в начало» или «в
    конец», а не ошибка.
    """
    siblings = list(
        (
            await session.execute(
                select(Transaction)
                .where(Transaction.date == moved[0].date)
                .order_by(Transaction.day_order, Transaction.id)
            )
        )
        .scalars()
        .all()
    )

    moved_ids = {row.id for row in moved}
    rest = [row for row in siblings if row.id not in moved_ids]
    at = max(0, min(position, len(rest)))
    for index, row in enumerate(rest[:at] + moved + rest[at:]):
        row.day_order = index

    await session.commit()


@router.post("/reorder-block", status_code=204)
async def reorder_transaction_block(
    payload: TransactionBlockReorder, session: AsyncSession = Depends(get_session)
) -> None:
    """Переставляет несколько операций одного дня как одно целое.

    Так двигается свёрнутая группа: на экране это одна строка, в базе —
    несколько записей, и переставлять их по очереди нельзя. После первой же
    перестановки нумерация меняется, и остальные уезжают не туда.

    Все операции блока обязаны быть одного дня — иначе непонятно, внутри
    чего их переставлять. Счёт при этом любой: порядок дня сквозной.
    """
    rows = (
        (await session.execute(select(Transaction).where(Transaction.id.in_(payload.ids)))).scalars().all()
    )
    by_id = {row.id: row for row in rows}
    if len(by_id) != len(set(payload.ids)):
        raise HTTPException(status_code=404, detail="Transaction not found")
    moved = [by_id[transaction_id] for transaction_id in dict.fromkeys(payload.ids)]
    if len({row.date for row in moved}) > 1:
        raise HTTPException(status_code=400, detail="All transactions in a block must share one date")
    await _move_within_day(session, moved, payload.position)


@router.post("/{transaction_id}/reorder", response_model=TransactionRead)
async def reorder_transaction(
    transaction_id: int, payload: TransactionReorder, session: AsyncSession = Depends(get_session)
) -> Transaction:
    """Переставляет одну операцию внутри её дня. Частный случай блока из
    одной записи — сама перестановка живёт в _move_within_day."""
    transaction = await session.get(Transaction, transaction_id)
    if transaction is None:
        raise HTTPException(status_code=404, detail="Transaction not found")

    await _move_within_day(session, [transaction], payload.position)
    refreshed = await session.execute(select(Transaction).options(*_EAGER).where(Transaction.id == transaction_id))
    return refreshed.scalar_one()


@router.delete("/{transaction_id}", status_code=204)
async def delete_transaction(transaction_id: int, session: AsyncSession = Depends(get_session)) -> None:
    transaction = await session.get(Transaction, transaction_id)
    if transaction is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    await session.delete(transaction)
    await session.commit()
