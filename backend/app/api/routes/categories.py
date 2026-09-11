from collections import defaultdict
from datetime import date as date_
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.models.category import Category
from app.models.enums import CategoryKind, TransactionType
from app.models.transaction import Transaction, TransactionSplit
from app.schemas.category import CategoryCreate, CategoryRead, CategoryUpdate, CategoryUsage
from app.services.category_rollup import monthly_amounts_by_category
from app.services.category_tree import MAX_DEPTH, load_category_tree

router = APIRouter(prefix="/categories", tags=["categories"])


async def _validate_parent(session: AsyncSession, parent_id: int, kind: CategoryKind, category_id: int | None) -> None:
    """Проверяет, что категорию можно подвесить под этого родителя.

    Вложенность произвольной глубины: «Продукты → Молочное → Сыр» законны, и
    ветку с детьми можно целиком перенести под другую. Запрещено только то,
    что делает дерево невозможным или бессмысленным:

      * категория не может стать потомком самой себя — получился бы цикл, а
        ветка, подвешенная сама к себе, исчезла бы из всех отчётов;
      * доход не вкладывается в расход и наоборот — иначе одна ветка
        оказалась бы наполовину доходной, и подъём суммы к корню менял бы
        знак;
      * глубже MAX_DEPTH не пускаем: категория седьмого уровня не помещается
        ни в один список и не находится в выпадающем меню.
    """
    if parent_id == category_id:
        raise HTTPException(status_code=400, detail="A category cannot be its own parent")
    parent = await session.get(Category, parent_id)
    if parent is None:
        raise HTTPException(status_code=400, detail="Parent category not found")
    if parent.kind != kind:
        raise HTTPException(status_code=400, detail="A subcategory must have the same kind as its parent")

    tree = await load_category_tree(session)

    if category_id is not None and category_id in tree.ancestors_of(parent_id):
        # Перенос ветки внутрь самой себя. Без этой проверки обе части
        # оторвались бы от корня и пропали из отчётов молча.
        raise HTTPException(
            status_code=400, detail="A category cannot be moved inside its own subtree"
        )

    # Глубина считается по итогу перемещения: место родителя плюс высота
    # переносимой ветки. Ветку из трёх уровней нельзя подвесить так, чтобы
    # её низ вышел за предел.
    branch_height = tree.depth_below(category_id) if category_id is not None else 1
    if tree.depth_of(parent_id) + branch_height > MAX_DEPTH:
        raise HTTPException(
            status_code=400, detail=f"Categories cannot nest deeper than {MAX_DEPTH} levels"
        )


@router.get("", response_model=list[CategoryRead])
async def list_categories(
    kind: CategoryKind | None = None, session: AsyncSession = Depends(get_session)
) -> list[Category]:
    # Доходы идут первыми: список читают сверху вниз, а разговор о деньгах
    # начинается с того, откуда они берутся. В перечислении INCOME объявлен
    # раньше EXPENSE, поэтому сортировки по самому полю достаточно.
    stmt = select(Category).order_by(Category.kind, Category.sort_order, Category.name)
    if kind is not None:
        stmt = stmt.where(Category.kind == kind)
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.post("", response_model=CategoryRead, status_code=201)
async def create_category(payload: CategoryCreate, session: AsyncSession = Depends(get_session)) -> Category:
    if payload.parent_id is not None:
        await _validate_parent(session, payload.parent_id, payload.kind, category_id=None)
    category = Category(**payload.model_dump(), is_default=False)
    session.add(category)
    await session.commit()
    await session.refresh(category)
    return category


@router.patch("/{category_id}", response_model=CategoryRead)
async def update_category(
    category_id: int, payload: CategoryUpdate, session: AsyncSession = Depends(get_session)
) -> Category:
    category = await session.get(Category, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")
    updates = payload.model_dump(exclude_unset=True)
    if "parent_id" in updates and updates["parent_id"] is not None:
        # Ветка с детьми переезжает целиком — это и есть «нормальная
        # вложенность»: человек раскладывает накопившиеся категории, не
        # разбирая их по одной.
        await _validate_parent(session, updates["parent_id"], category.kind, category_id=category_id)
    apply_to_children = updates.pop("apply_style_to_children", False)
    for field, value in updates.items():
        setattr(category, field, value)

    if apply_to_children and ("color" in updates or "icon" in updates):
        # Вся ветка вниз, а не только прямые дети: перекрасить «Продукты» и
        # оставить «Сыр» разноцветным под перекрашенным «Молочным» — половина
        # работы, за которой всё равно придётся возвращаться.
        tree = await load_category_tree(session)
        descendants = tree.descendants_of(category_id)
        if descendants:
            children = (
                (await session.execute(select(Category).where(Category.id.in_(descendants))))
                .scalars()
                .all()
            )
            for child in children:
                if "color" in updates:
                    child.color = category.color
                if "icon" in updates:
                    child.icon = category.icon

    await session.commit()
    await session.refresh(category)
    return category


@router.get("/{category_id}/usage", response_model=CategoryUsage)
async def read_category_usage(category_id: int, session: AsyncSession = Depends(get_session)) -> CategoryUsage:
    """Что зацепит удаление категории.

    Отдельный запрос, а не поле в списке: спрашивают об этом ровно один раз
    за жизнь категории, а список категорий грузится на каждой странице с
    выбором.

    Считается перед показом вопроса, потому что вопрос без чисел ничего не
    решает: «её транзакции останутся без категории» звучит одинаково и для
    пустой категории, и для той, в которой лежит год истории.
    """
    category = await session.get(Category, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")

    tree = await load_category_tree(session)
    descendants = tree.descendants_of(category_id)

    async def _transactions_in(category_ids: list[int]) -> int:
        """Разные операции, а не ссылки на категорию.

        Сплит-операция может указывать на одну категорию двумя строками —
        это одна операция. distinct обязателен, иначе число в вопросе
        оказалось бы больше, чем на самом деле.
        """
        if not category_ids:
            return 0
        stmt = select(func.count(func.distinct(Transaction.id))).where(
            or_(
                Transaction.category_id.in_(category_ids),
                Transaction.splits.any(TransactionSplit.category_id.in_(category_ids)),
            )
        )
        return int((await session.execute(stmt)).scalar_one())

    return CategoryUsage(
        transactions=await _transactions_in([category_id]),
        children=len(tree.children.get(category_id, [])),
        descendants=len(descendants),
        descendant_transactions=await _transactions_in(descendants),
    )


@router.delete("/{category_id}", status_code=204)
async def delete_category(category_id: int, session: AsyncSession = Depends(get_session)) -> None:
    category = await session.get(Category, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")
    if category.is_default:
        # A default (seeded) category can be removed once it's unused — but
        # never while transactions still point at it, or a whole year's
        # worth of history would silently lose its category (the FK is
        # ON DELETE SET NULL, so nothing would error, it would just vanish
        # from every report). A custom category has no such guard: the user
        # created it and can freely delete it, same as before.
        has_transaction = (
            await session.execute(select(Transaction.id).where(Transaction.category_id == category_id).limit(1))
        ).first()
        has_split = (
            await session.execute(select(TransactionSplit.id).where(TransactionSplit.category_id == category_id).limit(1))
        ).first()
        if has_transaction is not None or has_split is not None:
            raise HTTPException(
                status_code=400, detail="Default categories can only be deleted once they have no transactions"
            )
    await session.delete(category)
    await session.commit()


class CategoryTotal(BaseModel):
    """Сколько прошло через категорию за период.

    Два числа, а не одно. `own` — то, что записано прямо в эту категорию;
    `total` — она вместе со всей веткой под ней. У листа они совпадают, у
    ветки различаются, и именно разница отвечает на вопрос «сколько тут
    неразобранного»: крупный own у категории с подкатегориями означает, что
    траты сваливают в корень, не выбирая подкатегорию.
    """

    category_id: int
    own: Decimal
    total: Decimal
    transactions: int


@router.get("/totals", response_model=list[CategoryTotal])
async def read_category_totals(
    start_date: date_ | None = Query(default=None),
    end_date: date_ | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> list[CategoryTotal]:
    """Суммы по каждой категории — чтобы дерево показывало не только имена.

    Без периода считается за всё время: список категорий открывают, чтобы
    разобраться в накопившемся, а не чтобы посмотреть текущий месяц.
    """
    own_amounts: dict[int, Decimal] = defaultdict(Decimal)
    counts: dict[int, int] = defaultdict(int)
    for transaction_type in (TransactionType.INCOME, TransactionType.EXPENSE):
        monthly = await monthly_amounts_by_category(
            session,
            transaction_type=transaction_type,
            start_date=start_date or date_.min,
            end_date=end_date or date_.max,
        )
        for (_year, _month, category_id), amount in monthly.items():
            own_amounts[category_id] += amount
            counts[category_id] += 1

    tree = await load_category_tree(session)
    return [
        CategoryTotal(
            category_id=category_id,
            own=own_amounts.get(category_id, Decimal("0")),
            # Ветка целиком: план или бюджет ставят на ветку, и «Продукты»
            # обязаны показывать сыр, лежащий двумя уровнями ниже.
            total=sum(
                (own_amounts.get(node, Decimal("0")) for node in tree.subtree_of(category_id)),
                Decimal("0"),
            ),
            transactions=counts.get(category_id, 0),
        )
        for category_id in tree.parents
    ]
