from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.models.category import Category
from app.models.enums import CategoryKind
from app.models.transaction import Transaction, TransactionSplit
from app.schemas.category import CategoryCreate, CategoryRead, CategoryUpdate
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
    for field, value in updates.items():
        setattr(category, field, value)
    await session.commit()
    await session.refresh(category)
    return category


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
