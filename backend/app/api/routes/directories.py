"""Справочники, на которые ссылается транзакция: банки, участники,
магазины, контрагенты.

Собраны в один роутер, потому что устроены одинаково — список, создание,
правка, архивирование — и разносить четыре копии одного CRUD по четырём
файлам значило бы четырежды чинить одну и ту же ошибку. Товары и единицы
измерения живут отдельно: у них есть своя логика приведения к базовой мере
и подстановки категории.

Все четыре справочника заполняются по ходу ввода, а не заранее: в форме
транзакции достаточно набрать новое имя. Заранее заполненный список — то,
на чём сгорела исходная таблица, где 43 подкатегории из 166 не
использовались ни разу.

Есть и архивирование, и удаление, и это разные действия. Архив убирает
запись из выпадающих списков, оставляя её в прошлых операциях, — так
поступают с магазином, куда перестали ходить. Удаление стирает запись
совсем, а ссылки на неё обнуляются: операции остаются, поле у них пустеет.
Так поступают с записью, заведённой по ошибке.

Чтобы выбор был осознанным, каждая запись отдаёт `usage` — сколько
операций на неё ссылается. Без этого числа удаление вслепую: «Магазин у дома»
и «Магазин у дома ` (опечатка) в списке выглядят одинаково, а стоят за ними
триста покупок и ноль.
"""
from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import case, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.models.account import Bank
from app.models.counterparty import Counterparty
from app.models.enums import TransactionType, UnitKind
from app.models.participant import Participant
from app.models.store import Store
from app.models.transaction import Transaction
from app.models.unit import Unit
from app.schemas.account import BankCreate, BankRead, BankUpdate
from app.schemas.directories import (
    CounterpartyCreate,
    CounterpartyRead,
    CounterpartyUpdate,
    ParticipantCreate,
    ParticipantRead,
    ParticipantUpdate,
    StoreCreate,
    StoreRead,
    StoreUpdate,
)
from app.services.transaction_service import converted_only, counted_only

router = APIRouter(tags=["directories"])


async def _get_or_404(session: AsyncSession, model, item_id: int):
    item = await session.get(model, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"{model.__name__} not found")
    return item


async def _create(session: AsyncSession, model, payload):
    item = model(**payload.model_dump())
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return item


async def _update(session: AsyncSession, model, item_id: int, payload):
    item = await _get_or_404(session, model, item_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    await session.commit()
    await session.refresh(item)
    return item


async def _delete(session: AsyncSession, model, item_id: int) -> None:
    """Удаляет запись. Ссылки на неё обнуляются самой базой (SET NULL на
    внешнем ключе), поэтому операции остаются на месте — у них лишь
    пустеет соответствующее поле."""
    item = await _get_or_404(session, model, item_id)
    await session.delete(item)
    await session.commit()


async def _usage_counts(session: AsyncSession, column) -> dict[int, int]:
    """Сколько операций ссылается на каждую запись справочника.

    Одним запросом на весь список: пятьдесят магазинов — это пятьдесят
    лишних обращений к базе ради числа в скобках.
    """
    rows = (
        await session.execute(
            select(column, func.count()).where(column.is_not(None)).group_by(column)
        )
    ).all()
    return {item_id: count for item_id, count in rows}


async def _spend_by_store(session: AsyncSession) -> dict[int, tuple[Decimal, Decimal]]:
    """Сколько потрачено в каждом магазине: за всё время и за скользящий год.

    Скользящий год, а не календарный — как и в товарах: в январе
    календарный показывал бы траты за две недели и выглядел бы падением
    там, где его нет.

    Считаются только расходы: перевод на карту магазина деньгами в нём не
    является, а возврат уменьшать сумму не должен — покупка всё равно была.
    """
    year_ago = date.today() - timedelta(days=365)
    rows = (
        await session.execute(
            select(
                Transaction.store_id,
                # В валюте установки: в одном магазине платят с разных карт.
                func.sum(Transaction.amount_base),
                func.sum(case((Transaction.date >= year_ago, Transaction.amount_base), else_=0)),
            )
            .where(
                Transaction.store_id.is_not(None),
                Transaction.type == TransactionType.EXPENSE,
                counted_only(),
                converted_only(),
            )
            .group_by(Transaction.store_id)
        )
    ).all()
    return {store_id: (Decimal(total or 0), Decimal(year or 0)) for store_id, total, year in rows}


def _with_usage(items, usage: dict[int, int], schema, extra: dict[int, dict] | None = None):
    # model_validate, а не распаковка __dict__: у объекта модели там лежит
    # ещё и служебное состояние SQLAlchemy, на котором конструктор схемы
    # спотыкается.
    return [
        schema.model_validate(item).model_copy(
            update={"usage": usage.get(item.id, 0), **((extra or {}).get(item.id) or {})}
        )
        for item in items
    ]


# --- Банки ---


@router.get("/banks", response_model=list[BankRead])
async def list_banks(session: AsyncSession = Depends(get_session)) -> list[Bank]:
    result = await session.execute(select(Bank).order_by(Bank.sort_order, Bank.name))
    return list(result.scalars().all())


@router.post("/banks", response_model=BankRead, status_code=201)
async def create_bank(payload: BankCreate, session: AsyncSession = Depends(get_session)) -> Bank:
    return await _create(session, Bank, payload)


@router.patch("/banks/{bank_id}", response_model=BankRead)
async def update_bank(bank_id: int, payload: BankUpdate, session: AsyncSession = Depends(get_session)) -> Bank:
    return await _update(session, Bank, bank_id, payload)


# --- Участники ---


@router.get("/participants", response_model=list[ParticipantRead])
async def list_participants(
    include_archived: bool = False, session: AsyncSession = Depends(get_session)
) -> list[Participant]:
    stmt = select(Participant).order_by(Participant.kind, Participant.name)
    if not include_archived:
        stmt = stmt.where(Participant.is_archived.is_(False))
    items = list((await session.execute(stmt)).scalars().all())
    return _with_usage(items, await _usage_counts(session, Transaction.participant_id), ParticipantRead)


@router.post("/participants", response_model=ParticipantRead, status_code=201)
async def create_participant(
    payload: ParticipantCreate, session: AsyncSession = Depends(get_session)
) -> Participant:
    return await _create(session, Participant, payload)


@router.patch("/participants/{participant_id}", response_model=ParticipantRead)
async def update_participant(
    participant_id: int, payload: ParticipantUpdate, session: AsyncSession = Depends(get_session)
) -> Participant:
    return await _update(session, Participant, participant_id, payload)


@router.delete("/participants/{participant_id}", status_code=204)
async def delete_participant(participant_id: int, session: AsyncSession = Depends(get_session)) -> None:
    await _delete(session, Participant, participant_id)


# --- Магазины ---


@router.get("/stores", response_model=list[StoreRead])
async def list_stores(include_archived: bool = False, session: AsyncSession = Depends(get_session)) -> list[Store]:
    stmt = select(Store).order_by(Store.name)
    if not include_archived:
        stmt = stmt.where(Store.is_archived.is_(False))
    items = list((await session.execute(stmt)).scalars().all())
    spend = await _spend_by_store(session)
    return _with_usage(
        items,
        await _usage_counts(session, Transaction.store_id),
        StoreRead,
        {store_id: {"spent_total": total, "spent_year": year} for store_id, (total, year) in spend.items()},
    )


@router.post("/stores", response_model=StoreRead, status_code=201)
async def create_store(payload: StoreCreate, session: AsyncSession = Depends(get_session)) -> Store:
    return await _create(session, Store, payload)


@router.patch("/stores/{store_id}", response_model=StoreRead)
async def update_store(store_id: int, payload: StoreUpdate, session: AsyncSession = Depends(get_session)) -> Store:
    return await _update(session, Store, store_id, payload)


@router.delete("/stores/{store_id}", status_code=204)
async def delete_store(store_id: int, session: AsyncSession = Depends(get_session)) -> None:
    await _delete(session, Store, store_id)


# --- Контрагенты ---


@router.get("/counterparties", response_model=list[CounterpartyRead])
async def list_counterparties(
    include_archived: bool = False, session: AsyncSession = Depends(get_session)
) -> list[Counterparty]:
    stmt = select(Counterparty).order_by(Counterparty.name)
    if not include_archived:
        stmt = stmt.where(Counterparty.is_archived.is_(False))
    items = list((await session.execute(stmt)).scalars().all())
    return _with_usage(items, await _usage_counts(session, Transaction.counterparty_id), CounterpartyRead)


@router.post("/counterparties", response_model=CounterpartyRead, status_code=201)
async def create_counterparty(
    payload: CounterpartyCreate, session: AsyncSession = Depends(get_session)
) -> Counterparty:
    return await _create(session, Counterparty, payload)


@router.patch("/counterparties/{counterparty_id}", response_model=CounterpartyRead)
async def update_counterparty(
    counterparty_id: int, payload: CounterpartyUpdate, session: AsyncSession = Depends(get_session)
) -> Counterparty:
    return await _update(session, Counterparty, counterparty_id, payload)


@router.delete("/counterparties/{counterparty_id}", status_code=204)
async def delete_counterparty(counterparty_id: int, session: AsyncSession = Depends(get_session)) -> None:
    await _delete(session, Counterparty, counterparty_id)


# --- Единицы измерения ---


class UnitRead(BaseModel):
    """Единица с её коэффициентом к базовой.

    Коэффициент отдаётся наружу не для красоты: интерфейс показывает цену за
    базовую единицу рядом с введённой ценой, и без него пришлось бы ходить
    на сервер за каждым пересчётом в поле ввода.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    kind: UnitKind
    factor: Decimal
    is_base: bool
    sort_order: int


class UnitCreate(BaseModel):
    """Своя единица измерения.

    Коэффициент придумать нельзя — его надо знать: «банка» сама по себе не
    сравнима ни с чем, а «банка = 400 г» встаёт в один ряд с килограммами
    и пачками. Поэтому он обязателен и должен быть больше нуля: ноль
    превратил бы цену за базовую единицу в деление на ноль.
    """

    name: str = Field(min_length=1, max_length=20)
    kind: UnitKind
    factor: Decimal = Field(gt=0, max_digits=18, decimal_places=6)
    sort_order: int = 0


class UnitUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=20)
    kind: UnitKind | None = None
    factor: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=6)
    sort_order: int | None = None
    # Базовая мера — та, в которой человек сравнивает цены: килограмм, а не
    # грамм. Меняется, потому что «удобно сравнивать» — вопрос привычки, а
    # не физики: кто-то считает бензин литрами, кто-то заправками.
    is_base: bool | None = None


@router.get("/units", response_model=list[UnitRead])
async def list_units(session: AsyncSession = Depends(get_session)) -> list[Unit]:
    """Единицы измерения с коэффициентом к базовой мере своего вида."""
    stmt = select(Unit).order_by(Unit.kind, Unit.sort_order, Unit.name)
    return list((await session.execute(stmt)).scalars().all())


@router.post("/units", response_model=UnitRead, status_code=201)
async def create_unit(payload: UnitCreate, session: AsyncSession = Depends(get_session)) -> Unit:
    """Своя единица. Базовой она стать не может: базовая у каждого вида
    ровно одна, и вторая сделала бы приведение неоднозначным."""
    return await _create(session, Unit, payload)


@router.patch("/units/{unit_id}", response_model=UnitRead)
async def update_unit(unit_id: int, payload: UnitUpdate, session: AsyncSession = Depends(get_session)) -> Unit:
    """Правка единицы. Назначение базовой снимает признак с прежней:
    двух базовых в одном виде быть не может — приведение стало бы
    неоднозначным, и цена за «базовую» перестала бы что-либо значить."""
    unit = await _get_or_404(session, Unit, unit_id)
    if payload.is_base:
        kind = payload.kind or unit.kind
        await session.execute(
            update(Unit).where(Unit.kind == kind, Unit.id != unit_id).values(is_base=False)
        )
    return await _update(session, Unit, unit_id, payload)


@router.delete("/units/{unit_id}", status_code=204)
async def delete_unit(unit_id: int, session: AsyncSession = Depends(get_session)) -> None:
    """Удалить можно любую, включая базовую.

    Запрет на удаление базовой был лишним: цена за базовую меру считается
    из коэффициента самой единицы, а признак `is_base` — только подпись,
    в каких единицах эта цена выражена. Вид, оставшийся без базовой,
    теряет подпись, а не расчёт; вид, оставшийся без единиц вовсе, просто
    перестаёт участвовать в сравнении цен.

    Позиции чеков, где единица была указана, остаются: ссылка обнуляется,
    и у них перестаёт считаться цена за базовую меру.
    """
    await _delete(session, Unit, unit_id)
