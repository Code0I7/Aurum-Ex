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
from app.schemas.transaction import (
    TransactionBulkCreate,
    TransactionBulkCreateResult,
    TransactionCreate,
    TransactionPage,
    TransactionRead,
    TransactionReorder,
    TransactionSplitInput,
    TransactionUpdate,
    split_rule_violation,
    transfer_rule_violation,
)
from app.models.product import Product
from app.schemas.product import TransactionItemInput
from app.services.category_tree import load_category_tree
from app.services.currency_service import get_base_currency, to_base
from app.services.product_service import resolve_item_category
from app.services.transaction_service import next_day_order, running_balances

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
    selectinload(Transaction.items).selectinload(TransactionItem.category),
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


async def _build_items(
    session: AsyncSession, items: list[TransactionItemInput]
) -> list[TransactionItem]:
    """Позиции чека — «что лежало в пакете».

    Сходиться с суммой транзакции они не обязаны и намеренно: помнить, что
    купили хлеб и молоко, не помня цен, обычное дело, а сумма транзакции
    остаётся источником истины. Нераспределённый остаток интерфейс
    показывает, а не подгоняет.

    Категория позиции проверяется на существование, но НЕ на совпадение с
    видом операции: позиция расхода не может быть доходной по построению, а
    лишняя проверка мешала бы разложить чек по подкатегориям свободно.
    """
    built: list[TransactionItem] = []
    for position, item in enumerate(items):
        await resolve_item_category(session, item.category_id)
        if item.product_id is not None and await session.get(Product, item.product_id) is None:
            raise HTTPException(status_code=400, detail="Product not found")
        built.append(
            TransactionItem(
                product_id=item.product_id,
                name=item.name,
                category_id=item.category_id,
                quantity=item.quantity,
                unit_id=item.unit_id,
                price=item.price,
                # Сумма позиции: если не задана, но известны цена и
                # количество, считается сама — заставлять человека
                # перемножать два числа, которые он уже ввёл, незачем.
                amount=item.amount
                if item.amount is not None
                else (item.price * item.quantity if item.price is not None and item.quantity is not None else None),
                note=item.note,
                position=position,
            )
        )
    return built


async def _build_splits(
    session: AsyncSession, splits: list[TransactionSplitInput], transaction_type: TransactionType
) -> list[TransactionSplit]:
    """A split's whole point is dividing one purchase's total across the
    *subcategories of one parent* (a hypermarket receipt: part groceries ->
    Sweets, part -> Alcohol) — not across unrelated top-level categories, or
    the numbers would roll up into two different parents and the "spent X on
    Groceries, split between Sweets/Alcohol" picture the feature exists for
    falls apart. Each split may point at that parent category itself (an
    unspecified-subcategory line) or at any one of its direct children —
    enforced by requiring every split's own top-level ancestor
    (parent_id, or its own id if it has none) to agree.
    """
    # Корень ветки, а не родитель на один шаг: с произвольной вложенностью
    # у «Продукты → Молочное → Сыр» родитель — молочное, и разбивка чека
    # между сыром и хлебом отклонялась бы как «разные ветки».
    tree = await load_category_tree(session)
    top_level_ids: set[int] = set()
    for split in splits:
        category = await _ensure_category_matches_type(session, split.category_id, transaction_type)
        assert category is not None  # split.category_id is required (not Optional) on the schema
        top_level_ids.add(tree.top_level_of(category.id))
    if len(top_level_ids) > 1:
        raise HTTPException(
            status_code=400,
            detail="All split categories must be the same parent category or its direct subcategories",
        )
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
        category_filter = or_(
            Transaction.category_id == category_id, Transaction.splits.any(TransactionSplit.category_id == category_id)
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
        stmt = stmt.where(Transaction.counterparty_id == counterparty_id)
        count_stmt = count_stmt.where(Transaction.counterparty_id == counterparty_id)
    if not include_excluded:
        stmt = stmt.where(Transaction.is_excluded.is_(False))
        count_stmt = count_stmt.where(Transaction.is_excluded.is_(False))
    if search is not None:
        # Lets the user find a transaction from any period by keyword (e.g. an
        # item bought months ago) without knowing which month to look in first —
        # matches description, merchant, and notes so any of those fields can surface it.
        pattern = f"%{search.strip()}%"
        search_clause = or_(
            Transaction.description.ilike(pattern),
            Transaction.merchant.ilike(pattern),
            Transaction.notes.ilike(pattern),
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


@router.post("", response_model=TransactionRead, status_code=201)
async def create_transaction(payload: TransactionCreate, session: AsyncSession = Depends(get_session)) -> Transaction:
    await _ensure_category_matches_type(session, payload.category_id, payload.type)
    fields = payload.model_dump(exclude={"tag_ids", "splits", "items", "currency"})
    transaction = Transaction(**fields)
    # Порядок внутри дня проставляется сам, по времени ввода: человеку не за
    # чем его набирать, а без него операции одного дня раскладываются
    # произвольно и баланс на графике проваливается ниже нуля там, где
    # этого не было (см. services/transaction_service.py).
    transaction.day_order = await next_day_order(session, transaction.account_id, transaction.date)
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
        transaction.day_order = await next_day_order(session, transaction.account_id, transaction.date)
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


@router.post("/{transaction_id}/reorder", response_model=TransactionRead)
async def reorder_transaction(
    transaction_id: int, payload: TransactionReorder, session: AsyncSession = Depends(get_session)
) -> Transaction:
    """Переставляет операцию внутри её дня.

    Между днями запись не переносится намеренно: дату меняют
    редактированием даты, а не движением мыши — случайное перетаскивание
    строки не должно менять день операции.

    Порядок пересчитывается сплошным рядом 0, 1, 2… у всех операций этого
    счёта за этот день. Это дороже точечной правки, но избавляет от дыр и
    дубликатов в нумерации, которые иначе накапливаются и однажды ломают
    сортировку.
    """
    transaction = await session.get(Transaction, transaction_id)
    if transaction is None:
        raise HTTPException(status_code=404, detail="Transaction not found")

    siblings = list(
        (
            await session.execute(
                select(Transaction)
                .where(
                    Transaction.account_id == transaction.account_id,
                    Transaction.date == transaction.date,
                )
                .order_by(Transaction.day_order, Transaction.id)
            )
        )
        .scalars()
        .all()
    )

    siblings = [row for row in siblings if row.id != transaction_id]
    position = max(0, min(payload.position, len(siblings)))
    siblings.insert(position, transaction)
    for index, row in enumerate(siblings):
        row.day_order = index

    await session.commit()
    refreshed = await session.execute(select(Transaction).options(*_EAGER).where(Transaction.id == transaction_id))
    return refreshed.scalar_one()


@router.delete("/{transaction_id}", status_code=204)
async def delete_transaction(transaction_id: int, session: AsyncSession = Depends(get_session)) -> None:
    transaction = await session.get(Transaction, transaction_id)
    if transaction is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    await session.delete(transaction)
    await session.commit()
