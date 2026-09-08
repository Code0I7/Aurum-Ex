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

Удаления нет — только архивирование. Удалить магазин, на который ссылаются
сто покупок, значит потерять смысл этих ста строк; заархивированный
перестаёт предлагаться в новых операциях, но старые продолжают его
показывать.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.models.account import Bank
from app.models.counterparty import Counterparty
from app.models.participant import Participant
from app.models.store import Store
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
    return list((await session.execute(stmt)).scalars().all())


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


# --- Магазины ---


@router.get("/stores", response_model=list[StoreRead])
async def list_stores(include_archived: bool = False, session: AsyncSession = Depends(get_session)) -> list[Store]:
    stmt = select(Store).order_by(Store.name)
    if not include_archived:
        stmt = stmt.where(Store.is_archived.is_(False))
    return list((await session.execute(stmt)).scalars().all())


@router.post("/stores", response_model=StoreRead, status_code=201)
async def create_store(payload: StoreCreate, session: AsyncSession = Depends(get_session)) -> Store:
    return await _create(session, Store, payload)


@router.patch("/stores/{store_id}", response_model=StoreRead)
async def update_store(store_id: int, payload: StoreUpdate, session: AsyncSession = Depends(get_session)) -> Store:
    return await _update(session, Store, store_id, payload)


# --- Контрагенты ---


@router.get("/counterparties", response_model=list[CounterpartyRead])
async def list_counterparties(
    include_archived: bool = False, session: AsyncSession = Depends(get_session)
) -> list[Counterparty]:
    stmt = select(Counterparty).order_by(Counterparty.name)
    if not include_archived:
        stmt = stmt.where(Counterparty.is_archived.is_(False))
    return list((await session.execute(stmt)).scalars().all())


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
