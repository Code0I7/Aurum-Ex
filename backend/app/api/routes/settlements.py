"""Расчёты с людьми: обороты и остатки долгов.

Отдельный раздел, а не вкладка внутри счетов, потому что это принципиально
другие деньги: они не ваши. Контрагент с большим отрицательным оборотом —
не дыра в бюджете, а человек, который много вам передавал.
"""
from datetime import date as date_

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.services.currency_service import quantize_money
from app.services.settlement_service import (
    get_settlements,
    get_transit_by_person,
    get_settlement_summary,
    get_transit_summary,
)


def _money(amount) -> str:
    """Деньги наружу всегда с двумя знаками. Ноль, записанный как «0», и
    ноль, записанный как «0.00», — одно и то же число, но интерфейс,
    выравнивающий колонку по запятой, на первом сломается."""
    return str(quantize_money(amount))

router = APIRouter(prefix="/settlements", tags=["settlements"])


class SettlementRead(BaseModel):
    counterparty_id: int
    name: str
    # Оборот: сколько всего прошло в обе стороны.
    received: str
    given: str
    # Долговая часть: сколько ещё не вернули.
    owed_to_me: str
    owed_by_me: str
    # Остаток: плюс — должны вам, минус — должны вы.
    balance: str
    operations: int
    last_date: date_ | None


class SettlementSummary(BaseModel):
    """Две суммы для карточки капитала. Рядом с капиталом, но не внутри
    него: обещание вернуть не актив, пока его не вернули."""

    owed_to_me: str
    owed_by_me: str


class TransitSummary(BaseModel):
    """Деньги, прошедшие через счёт насквозь. В расчёты с людьми не входят
    (см. services/settlement_service.py), но чужое, лежащее на карте прямо
    сейчас, человек должен видеть."""

    passed_through: str
    # Может быть отрицательным: передал вперёд, ещё не получив.
    held: str



class TransitPersonRead(BaseModel):
    """Транзит по одному человеку — по тому, ДЛЯ КОГО шли деньги.

    Источник, передавший на покупки для кого-то другого, сюда не попадает:
    он не сторона расчёта. См. services/settlement_service.py.
    """

    counterparty_id: int
    name: str
    # Передано на него и потрачено на него.
    received: str
    spent: str
    # Плюс — его деньги ещё у вас, минус — вы вложили свои. Не долг.
    balance: str
    operations: int


@router.get("", response_model=list[SettlementRead])
async def list_settlements(session: AsyncSession = Depends(get_session)) -> list[SettlementRead]:
    return [
        SettlementRead(
            counterparty_id=item.counterparty.id,
            name=item.counterparty.name,
            received=_money(item.received),
            given=_money(item.given),
            owed_to_me=_money(max(item.balance, 0)),
            owed_by_me=_money(-min(item.balance, 0)),
            balance=_money(item.balance),
            operations=item.operations,
            last_date=item.last_date,
        )
        for item in await get_settlements(session)
    ]


@router.get("/transit", response_model=TransitSummary)
async def read_transit_summary(session: AsyncSession = Depends(get_session)) -> TransitSummary:
    totals = await get_transit_summary(session)
    return TransitSummary(
        passed_through=_money(totals["passed_through"]), held=_money(totals["held"])
    )



@router.get("/transit-by-person", response_model=list[TransitPersonRead])
async def read_transit_by_person(
    year: int | None = Query(default=None, ge=1970, le=2200),
    month: int | None = Query(default=None, ge=1, le=12),
    session: AsyncSession = Depends(get_session),
) -> list[TransitPersonRead]:
    """Разложенный по людям транзит за период.

    Период необязателен: без него отвечает на вопрос «с кем не сошлось
    вообще», с ним — «что происходило в этом месяце». Оба вопроса реальные,
    и заставлять выбирать месяц ради первого незачем.
    """
    return [
        TransitPersonRead(
            counterparty_id=item.counterparty.id,
            name=item.counterparty.name,
            received=_money(item.received),
            spent=_money(item.spent),
            balance=_money(item.balance),
            operations=item.operations,
        )
        for item in await get_transit_by_person(session, year, month)
    ]

@router.get("/summary", response_model=SettlementSummary)
async def read_settlement_summary(session: AsyncSession = Depends(get_session)) -> SettlementSummary:
    totals = await get_settlement_summary(session)
    return SettlementSummary(
        owed_to_me=_money(totals["owed_to_me"]),
        owed_by_me=_money(totals["owed_by_me"]),
    )
