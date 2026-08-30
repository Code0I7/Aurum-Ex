"""Spend/income per top-level category, split-aware — shared by
dashboard_service's breakdown and reports_service's category ranking, the
two places that both roll a subcategory's amount up into its parent
(coalesce(parent_id, id)) and now also need a category's share of a split
transaction counted the same way a plain transaction's is.

A split transaction has Transaction.category_id=NULL (see
models/transaction.py's TransactionSplit) — a query that only joins on that
column would silently drop its spending from every category it actually
touches. This walks both sources (a transaction's own category_id, and its
splits' category_ids) and combines them before rolling up, so a category
funded partly by plain transactions and partly by split lines still shows
one correct total.
"""
from collections import defaultdict
from dataclasses import dataclass
from datetime import date as date_
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.models.enums import TransactionType
from app.models.transaction import Transaction, TransactionSplit


@dataclass
class CategoryRollupItem:
    category_id: int
    name: str
    color: str
    icon: str | None
    sort_order: int
    amount: Decimal
    # Distinct transactions contributing to this category — a split
    # transaction counts once per top-level category it touches, same as a
    # plain one counts once for its own category.
    transaction_count: int


async def _raw_category_contributions(
    session: AsyncSession,
    *,
    transaction_type: TransactionType,
    start_date: date_ | None,
    end_date: date_ | None,
) -> list[tuple[int, int, Decimal]]:
    """(transaction_id, category_id, amount) for every category a
    transaction of this type/date-range contributed to. A plain transaction
    contributes one row (its own category); a split one contributes one row
    per split line — never both for the same transaction, since a
    transaction is either plain (category_id set, no splits) or split
    (category_id NULL, 2+ splits), enforced at write time."""
    plain_stmt = select(Transaction.id, Transaction.category_id, Transaction.amount).where(
        Transaction.type == transaction_type, Transaction.category_id.is_not(None)
    )
    split_stmt = (
        select(TransactionSplit.transaction_id, TransactionSplit.category_id, TransactionSplit.amount)
        .join(Transaction, Transaction.id == TransactionSplit.transaction_id)
        .where(Transaction.type == transaction_type, TransactionSplit.category_id.is_not(None))
    )
    if start_date is not None:
        plain_stmt = plain_stmt.where(Transaction.date >= start_date)
        split_stmt = split_stmt.where(Transaction.date >= start_date)
    if end_date is not None:
        plain_stmt = plain_stmt.where(Transaction.date <= end_date)
        split_stmt = split_stmt.where(Transaction.date <= end_date)

    plain_rows = (await session.execute(plain_stmt)).all()
    split_rows = (await session.execute(split_stmt)).all()
    return [(r[0], r[1], r[2]) for r in plain_rows] + [(r[0], r[1], r[2]) for r in split_rows]


async def rollup_spending_by_top_level_category(
    session: AsyncSession,
    *,
    transaction_type: TransactionType,
    start_date: date_ | None = None,
    end_date: date_ | None = None,
) -> list[CategoryRollupItem]:
    """Every top-level category's total for the period, sorted by amount
    desc (category sort_order as tiebreak — same order the SQL-only version
    used to produce)."""
    contributions = await _raw_category_contributions(
        session, transaction_type=transaction_type, start_date=start_date, end_date=end_date
    )
    if not contributions:
        return []

    categories_by_id = {c.id: c for c in (await session.execute(select(Category))).scalars().all()}

    amount_by_effective: dict[int, Decimal] = defaultdict(Decimal)
    txn_ids_by_effective: dict[int, set[int]] = defaultdict(set)
    for transaction_id, category_id, amount in contributions:
        category = categories_by_id.get(category_id)
        effective_id = category.parent_id if category and category.parent_id is not None else category_id
        amount_by_effective[effective_id] += amount
        txn_ids_by_effective[effective_id].add(transaction_id)

    items: list[CategoryRollupItem] = []
    for effective_id, amount in amount_by_effective.items():
        category = categories_by_id.get(effective_id)
        items.append(
            CategoryRollupItem(
                category_id=effective_id,
                name=category.name if category else "?",
                color=category.color if category else "#898781",
                icon=category.icon if category else None,
                sort_order=category.sort_order if category else 0,
                amount=amount,
                transaction_count=len(txn_ids_by_effective[effective_id]),
            )
        )
    items.sort(key=lambda item: (-item.amount, item.sort_order))
    return items
