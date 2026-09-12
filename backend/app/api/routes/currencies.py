"""Валюты и курсы: справочник, загрузка с сайта ЦБ, сводка по капиталу.

Курсы подтягиваются по запросу, а не по расписанию. Причина простая:
приложение одно на одного человека, оно может неделями не открываться, и
фоновая задача, которая всё это время ходит на сайт ЦБ, никому не нужна.
Загрузка запускается, когда её результат кому-то понадобился.
"""
from datetime import date as date_, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.models.currency import Currency, ExchangeRate
from app.services.cbr_service import CbrUnavailable, sync_rates_for_date
from app.services.currency_service import get_base_currency, get_current_rates

router = APIRouter(prefix="/currencies", tags=["currencies"])

# Сколько дней назад имеет смысл искать курс, если на сегодня его ещё нет.
# Длинные новогодние праздники — самый долгий перерыв в публикации; десяти
# дней хватает с запасом.
MAX_LOOKBACK_DAYS = 10


class CurrencyRead(BaseModel):
    code: str
    symbol: str | None
    name: str | None
    is_active: bool
    # Текущий курс к базовой валюте. У самой базовой всегда 1.
    rate: str | None = None
    rate_date: date_ | None = None


class RateSyncResult(BaseModel):
    saved: int
    rate_date: date_
    message: str


@router.get("", response_model=list[CurrencyRead])
async def list_currencies(session: AsyncSession = Depends(get_session)) -> list[CurrencyRead]:
    base = (await get_base_currency(session)).upper()
    currencies = (await session.execute(select(Currency).order_by(Currency.code))).scalars().all()

    # Дата последнего известного курса — по ней видно, насколько свежи
    # цифры, и стоит ли жать «обновить».
    dates = dict(
        (
            await session.execute(
                select(ExchangeRate.code, ExchangeRate.rate_date).order_by(
                    ExchangeRate.code, ExchangeRate.rate_date.desc()
                )
            )
        ).all()
    )
    rates = await get_current_rates(session)

    return [
        CurrencyRead(
            code=currency.code,
            symbol=currency.symbol,
            name=currency.name,
            is_active=currency.is_active,
            rate=str(rates.get(currency.code.upper())) if currency.code.upper() in rates else None,
            rate_date=None if currency.code.upper() == base else dates.get(currency.code),
        )
        for currency in currencies
    ]


@router.post("/rates/sync", response_model=RateSyncResult)
async def sync_rates(
    on_date: date_ | None = Query(default=None, description="Дата курсов; по умолчанию сегодня"),
    session: AsyncSession = Depends(get_session),
) -> RateSyncResult:
    """Загружает курсы с сайта ЦБ.

    Если на запрошенную дату курсов нет — а по выходным и праздникам их не
    публикуют, — отступаем назад по дням до последнего рабочего. Это не
    обходной путь, а нормальный порядок: в выходные и действует курс
    последнего рабочего дня.
    """
    target = on_date or date_.today()

    last_error: str | None = None
    for offset in range(MAX_LOOKBACK_DAYS):
        attempt = target - timedelta(days=offset)
        try:
            saved = await sync_rates_for_date(session, attempt)
        except CbrUnavailable as error:
            last_error = str(error)
            break
        if saved:
            return RateSyncResult(saved=saved, rate_date=attempt, message="ok")

    if last_error:
        # 502, а не 500: сломалась внешняя система, а не приложение.
        raise HTTPException(status_code=502, detail=last_error)

    return RateSyncResult(saved=0, rate_date=target, message="Курсы уже загружены или валют для обновления нет")
